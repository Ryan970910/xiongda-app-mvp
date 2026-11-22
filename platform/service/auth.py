import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from types import SimpleNamespace

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .db import Audit, Department, LoginSession, SessionPost, User, get_db, now, secret

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)
ROLE_NAMES = {"admin":"管理员","staff":"普通员工","leader":"主管","manager":"经理","director":"总监"}
SIGNING_KEY = secret()

class Form(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

class Tokens(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)

class Password(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)

class ChangePassword(Password):
    old_password: str = Field(max_length=256)

class Grant(Form):
    role: Literal["admin","staff","leader","manager","director"]
    expires: datetime | None = None
    department:int|None=Field(default=None,gt=0)

class Account(Form):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{2,64}$")
    name: str = Field(min_length=1,max_length=64)
    employee_no: str = Field(min_length=1,max_length=40)
    department: int = Field(gt=0)
    team: str = Field(min_length=1,max_length=64)
    roles: list[Grant] = Field(min_length=1,max_length=30)
    contact: str = Field(default="",max_length=160)
    enabled: bool = True

    @model_validator(mode="after")
    def compatible(self):
        roles = [g.role for g in self.roles]
        pairs={(g.role,g.department or self.department) for g in self.roles}
        if len(pairs)!=len(roles) or ("admin" in roles and (len(roles)>1 or self.roles[0].department not in (None,self.department))):
            raise ValueError("管理员与业务岗位须分离，岗位不可重复")
        if not any(dept==self.department for _,dept in pairs):raise ValueError("主部门须分配至少一个岗位")
        return self

class CreateAccount(Account, Password):
    pass

class Org(Form):
    name: str = Field(min_length=1,max_length=80)
    line: Literal["research","finance","function"]
    parent_id: int | None = Field(default=None,gt=0)

def fail(status, message):
    raise HTTPException(status,message)

def ok(data=None):
    return {"code":0,"message":"成功","data":data}

def roles(u):
    result=set()
    for grant in u.roles:
        exp=grant.get("expires")
        if not exp or datetime.fromisoformat(exp).replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
            result.add(grant["role"])
    return result

def require(u,*grants):
    if not roles(u).intersection(grants):
        fail(403,"当前岗位没有此项权限")

def public(u):
    return dict(id=u.id,username=u.username,name=u.name,employee_no=u.employee_no,
                department=u.department,team=u.team,roles=sorted(roles(u)),grants=u.roles,
                enabled=u.enabled,must_change=u.must_change,contact=u.contact,last_login=u.last_login,
                password_due=(now()-u.changed).days>=90)

def departments_for(u):
    return sorted({g.get("department") or u.department for g in u.roles if roles(SimpleNamespace(roles=[g]))})

def profile(u,dept):
    grants=[g for g in u.roles if (g.get("department") or u.department)==dept]
    return SimpleNamespace(**{k:getattr(u,k) for k in ("id","username","name","employee_no","team","enabled","must_change","contact","last_login","changed")},
                           department=dept,roles=grants)

def selected_profile(db,u,sid):
    post=db.get(SessionPost,sid)
    return profile(u,post.department if post else u.department)

def record(db,request,user,action,subject,details=None):
    db.add(Audit(user_id=user.id if user else None,action=action,subject=str(subject)[:160],
                 details=details or {},ip=request.client.host if request.client else "",
                 agent=request.headers.get("user-agent","")[:240]))

def hash_password(value):
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac("sha256",value.encode(),bytes.fromhex(salt),600000).hex()
    return f"pbkdf2-sha256:600000:{salt}:{digest}"

def matches(value,encoded):
    _,rounds,salt,digest=encoded.split(":")
    test=hashlib.pbkdf2_hmac("sha256",value.encode(),bytes.fromhex(salt),int(rounds)).hex()
    return hmac.compare_digest(digest,test)

def set_password(u,value,temporary):
    if (not re.search("[A-Za-z]",value) or not re.search("[0-9]",value) or
        len(value)<8 or len(value)>128 or value.casefold() in {"password123","12345678a","admin123","password1","qwerty123"} or
        value.casefold()==u.username.casefold()):
        fail(422,"密码须含字母和数字，长度8至128位，并避开弱口令")
    prior=([u.password_hash] if u.password_hash else [])+(u.history or [])
    if any(matches(value,digest) for digest in prior):
        fail(422,"不能重复使用历史密码")
    u.history=prior
    u.password_hash=hash_password(value)
    u.changed=now()
    u.must_change=temporary
    u.failures=0
    u.locked_until=None

def jwt_for(u,sess,kind,expires):
    return jwt.encode({"sub":str(u.id),"sid":sess.id,"typ":kind,"exp":expires.replace(tzinfo=timezone.utc),
                       "jti":secrets.token_hex(16)},SIGNING_KEY,algorithm="HS256")

def decode(token,kind):
    try:
        p=jwt.decode(token,SIGNING_KEY,algorithms=["HS256"],options={"require":["exp","sid","sub","typ","jti"]})
        if p["typ"]==kind:
            return p
    except jwt.InvalidTokenError:
        pass
    fail(401,"登录已失效")

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def pair(db,u,s):
    refresh=jwt_for(u,s,"refresh",s.expires)
    return {"access_token":jwt_for(u,s,"access",now()+timedelta(minutes=15)),
            "refresh_token":refresh,"token_type":"bearer","expires_in":900,"user":{**public(selected_profile(db,u,s.id)),"posts":departments_for(u)}}

def session_user(db,p):
    s=db.get(LoginSession,p["sid"])
    u=db.get(User,int(p["sub"]))
    if not u or not u.enabled or not s or s.user_id!=u.id or s.expires<=now() or now()-s.last_seen>timedelta(minutes=30):
        fail(401,"会话过期，请重新登录")
    if os.getenv("OFFICE_MODE")=="1" and u.employee_no.startswith("LOCAL-"):fail(403,"请使用本人办公室测试账号")
    return s,u

def authenticate(request:Request, db:DB, token:Annotated[HTTPAuthorizationCredentials|None,Depends(bearer)]):
    if not token:
        fail(401,"请先登录")
    s,u=session_user(db,decode(token.credentials,"access"))
    request.state.user=u.id
    request.state.session=s.id
    if (now()-s.last_seen).total_seconds()>30:
        s.last_seen=now()
        db.commit()
    return u

Identity=Annotated[User,Depends(authenticate)]

def active(u:Identity,request:Request,db:DB):
    if u.must_change or (now()-u.changed).days>=90:
        fail(403,"首次登录、密码重置或到期后请先修改密码")
    current=selected_profile(db,u,request.state.session)
    if not roles(current):fail(403,"当前部门岗位授权已到期，请切换至有效岗位")
    return current
Actor=Annotated[User,Depends(active)]
DUMMY=hash_password(secrets.token_urlsafe(24))

@router.post("/auth/login")
def login(form:Login,request:Request,db:DB):
    login_name=form.username.strip().lower()
    u=db.scalar(select(User).where(User.username==login_name).with_for_update())
    valid=matches(form.password,u.password_hash if u else DUMMY)
    locked=u and u.locked_until and u.locked_until>now()
    if u and os.getenv("OFFICE_MODE")=="1" and u.employee_no.startswith("LOCAL-"):
        record(db,request,u,"login.denied",login_name)
        db.commit();fail(401,"请使用管理员为本人开设的办公室测试账号")
    if not u or not u.enabled or locked or not valid:
        if u and u.enabled and not locked:
            if u.locked_until:
                u.failures=0
            u.failures+=1
            if u.failures>=5:
                u.locked_until=now()+timedelta(minutes=15)
                record(db,request,u,"login.locked",login_name,{"minutes":15})
        record(db,request,u,"login.denied",login_name)
        db.commit()
        fail(401,"账号或密码错误，或账号暂不可用")
    u.failures=0
    u.locked_until=None
    last=db.scalar(select(Audit).where(Audit.user_id==u.id,Audit.action=="login.success").order_by(Audit.id.desc()).limit(1))
    change=bool(last and (last.agent!=request.headers.get("user-agent","")[:240] or last.ip!=(request.client.host if request.client else "")))
    u.last_login=now()
    if os.getenv("SINGLE_SESSION","0")=="1":
        db.execute(delete(LoginSession).where(LoginSession.user_id==u.id))
    s=LoginSession(id=secrets.token_hex(24),user_id=u.id,expires=now()+timedelta(hours=12),last_seen=now())
    data=pair(db,u,s)
    if change:
        data["login_notice"]="本次登录设备或网络与上次不同，若有疑问请联系管理员检查登录日志。"
        record(db,request,u,"login.alert",u.username)
    s.refresh_hash=digest(data["refresh_token"])
    db.add(s)
    record(db,request,u,"login.success",u.username)
    db.commit()
    return ok(data)

@router.post("/auth/refresh")
def refresh(form:Tokens,db:DB):
    s,u=session_user(db,decode(form.refresh_token,"refresh"))
    data=pair(db,u,s)
    changed=db.execute(update(LoginSession).where(LoginSession.id==s.id,
        LoginSession.refresh_hash==digest(form.refresh_token)).values(refresh_hash=digest(data["refresh_token"]),last_seen=now()))
    if changed.rowcount!=1:
        fail(401,"刷新会话已失效")
    db.commit()
    return ok(data)

@router.get("/auth/me")
def me(u:Identity,request:Request,db:DB):
    return ok({**public(selected_profile(db,u,request.state.session)),"posts":departments_for(u)})

class SwitchPost(Form):
    department:int=Field(gt=0)

@router.post("/auth/post")
def switch_post(form:SwitchPost,u:Identity,request:Request,db:DB):
    if u.must_change or form.department not in departments_for(u):fail(403,"不能使用此岗位")
    db.merge(SessionPost(session_id=request.state.session,department=form.department))
    record(db,request,u,"post.switch",form.department);db.commit()
    return me(u,request,db)

@router.post("/auth/logout")
def logout(request:Request,db:DB,u:Identity):
    db.execute(delete(LoginSession).where(LoginSession.id==request.state.session))
    record(db,request,u,"logout",u.username)
    db.commit()
    return ok()

@router.put("/auth/password")
def password(form:ChangePassword,request:Request,db:DB,u:Identity):
    if not matches(form.old_password,u.password_hash):
        fail(403,"原密码错误")
    set_password(u,form.new_password,False)
    db.execute(delete(LoginSession).where(LoginSession.user_id==u.id))
    record(db,request,u,"password.change",u.username)
    db.commit()
    return ok()

@router.get("/system/roles")
def get_roles(u:Actor):
    return ok(ROLE_NAMES)

@router.get("/system/depts")
def depts(db:DB,u:Actor):
    return ok([{"id":d.id,"name":d.name,"line":d.line,"parent_id":d.parent_id} for d in db.scalars(select(Department))])

@router.post("/system/depts")
def create_dept(form:Org,request:Request,db:DB,u:Actor):
    require(u,"admin")
    if form.parent_id and not db.get(Department,form.parent_id):
        fail(422,"上级部门不存在")
    d=Department(**form.model_dump())
    db.add(d);db.flush()
    record(db,request,u,"department.add",d.id);db.commit()
    return ok({"id":d.id})

@router.get("/system/users")
def users(db:DB,u:Actor,q:str=""):
    require(u,"admin")
    rows=db.scalars(select(User).where(User.name.contains(q,autoescape=True)|User.username.contains(q,autoescape=True)).order_by(User.id))
    return ok([public(i) for i in rows])

@router.get("/directory")
def directory(db:DB,u:Actor):
    require(u,"admin","manager","director","leader")
    rows=db.scalars(select(User).where(User.enabled.is_(True)).order_by(User.id))
    return ok([{"id":i.id,"name":i.name,"department":i.department,"team":i.team,"roles":sorted(roles(i))} for i in rows])

@router.get("/system/account-register.xlsx")
def account_register(request:Request,db:DB,u:Actor):
    require(u,"admin")
    from .finance import write_xlsx
    from .materials import deliver
    depts={d.id:d.name for d in db.scalars(select(Department))}
    rows=[["工号","姓名","登录账号","主部门","授权部门","团队","岗位","有效期","启用"]]
    for person in db.scalars(select(User).order_by(User.id)):
        for grant in person.roles:
            rows.append([person.employee_no,person.name,person.username,depts[person.department],depts[grant.get("department") or person.department],
                         person.team,ROLE_NAMES[grant["role"]],grant.get("expires") or "长期","是" if person.enabled else "否"])
    record(db,request,u,"account.register.export","岗位台账");db.commit()
    return deliver(write_xlsx([("账号岗位",rows)]),"账号岗位台账.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def account_values(db,form):
    if not db.get(Department,form.department):
        fail(422,"部门不存在")
    values=form.model_dump(mode="json",exclude={"new_password"})
    values["username"]=values["username"].lower()
    for grant in values["roles"]:
        if grant.get("department") and not db.get(Department,grant["department"]):fail(422,"兼岗部门不存在")
        if grant["expires"]:
            d=datetime.fromisoformat(grant["expires"].replace("Z","+00:00"))
            grant["expires"]=d.astimezone(timezone.utc).isoformat() if d.tzinfo else d.replace(tzinfo=timezone.utc).isoformat()
    return values

@router.post("/system/users")
def add_user(form:CreateAccount,request:Request,db:DB,u:Actor):
    require(u,"admin")
    user=User(**account_values(db,form))
    set_password(user,form.new_password,True)
    db.add(user);db.flush(); record(db,request,u,"account.create",user.id);db.commit()
    return ok(public(user))

def admin_target(db,u,user_id):
    require(u,"admin")
    user=db.get(User,user_id)
    if not user: fail(404,"账号不存在")
    if user.id==u.id: fail(403,"请由另一位管理员调整本账号")
    return user

@router.put("/system/users/{user_id}")
def edit_user(user_id:int,form:Account,request:Request,db:DB,u:Actor):
    user=admin_target(db,u,user_id)
    before=public(user)
    for k,v in account_values(db,form).items(): setattr(user,k,v)
    db.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    record(db,request,u,"account.edit",user.id,{"oldRoles":before["grants"],"newRoles":user.roles,
        "oldDepartment":before["department"],"newDepartment":user.department})
    db.commit()
    return ok(public(user))

@router.delete("/system/users/{user_id}")
def disable(user_id:int,request:Request,db:DB,u:Actor):
    user=admin_target(db,u,user_id)
    user.enabled=False
    db.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    record(db,request,u,"account.disable",user.id);db.commit()
    return ok()

@router.post("/system/users/{user_id}/reset-password")
def reset(user_id:int,form:Password,request:Request,db:DB,u:Actor):
    user=admin_target(db,u,user_id)
    set_password(user,form.new_password,True)
    db.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    record(db,request,u,"account.reset",user.id);db.commit()
    return ok()

@router.get("/system/{category}-logs")
def logs(category:Literal["login","operation"],db:DB,u:Actor,page:int=1):
    require(u,"admin","manager","director")
    q=select(Audit)
    if "admin" not in roles(u):
        departments=select(Department.id).where(Department.line==db.get(Department,u.department).line) if "director" in roles(u) else [u.department]
        q=q.where(Audit.user_id.in_(select(User.id).where(User.department.in_(departments))))
    if category=="login": q=q.where(Audit.action.like("login.%"))
    rows=db.scalars(q.order_by(Audit.id.desc()).limit(100).offset(max(0,page-1)*100))
    return ok([dict(id=i.id,at=i.at,actor=i.user_id,action=i.action,subject=i.subject,ip=i.ip,agent=i.agent,details=i.details) for i in rows])
