from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from pydantic import Field, model_validator
from sqlalchemy import and_, false, or_, select, true

from .auth import Actor, DB, Form, fail, ok, public, record, require, roles
from .db import Contract, Customer, Department, Entry, FileObject, History, Member, Order, Project, Task, User, now

router=APIRouter()
STATUS={"assigned":"待接件","working":"办理中","revision":"修改中","suspended":"已挂起",
        "unassigned":"待重新派单","leader":"待主管审核","manager":"待经理复审","director":"待总监终审",
        "customer":"待客户确认","complete":"已完成","archived":"已归档"}
LINES={"research":"科研","finance":"财务"}
MONEY=Decimal("0.01")
def fields(row,*names):
    return {k:getattr(row,k) for k in names}

def access_tasks(db,u):
    grant=roles(u)
    scope=[Task.owner==u.id,Task.id.in_(select(Member.task).where(Member.user==u.id))]
    if "leader" in grant: scope.append(and_(Task.department==u.department,Task.team==u.team))
    if "manager" in grant: scope.extend([Task.department==u.department,Task.dispatcher==u.id])
    if "director" in grant:
        line=db.get(Department,u.department).line
        scope.append(Task.line==line)
    if "admin" in grant: return Task.status=="complete" if not grant-{"admin"} else false()
    return or_(*scope)

def access_customers(db,u):
    grant=roles(u)
    scopes=[Customer.id.in_(select(Task.customer).where(access_tasks(db,u)))]
    if grant.intersection({"manager","director"}):
        scopes.extend([Customer.manager==u.id,Customer.department==u.department])
    if "director" in grant:
        line=db.get(Department,u.department).line
        scopes.append(Customer.department.in_(select(Department.id).where(Department.line==line)))
    return or_(*scopes)

def visible_task(db,u,id,lock=False):
    q=select(Task).where(Task.id==id,access_tasks(db,u))
    t=db.scalar(q.with_for_update() if lock else q)
    if not t: fail(404,"任务不存在或不在本人数据范围内")
    return t

def visible_customer(db,u,id):
    c=db.scalar(select(Customer).where(Customer.id==id,Customer.deleted.is_(False),access_customers(db,u)))
    if not c: fail(404,"客户不存在或不在本人数据范围内")
    return c

def manage_customer(db,u,id):
    c=visible_customer(db,u,id)
    require(u,"manager","director")
    if c.department!=u.department and c.manager!=u.id:
        fail(403,"本客户不在业务管理范围内")
    return c

def projects_query(db,u):
    tasks=select(Task.id).where(access_tasks(db,u))
    orders=select(Task.order_id).where(access_tasks(db,u))
    return select(Project).where(Project.order_id.in_(orders)|Project.task.in_(tasks))

def commercial_scope(db,u,cls):
    if roles(u).intersection({"manager","director"}):
        return cls.customer.in_(select(Customer.id).where(access_customers(db,u),Customer.deleted.is_(False)))
    assigned=select(Task.order_id).where(access_tasks(db,u))
    if cls==Order:return Order.id.in_(assigned)
    return Contract.id.in_(select(Order.contract).where(Order.id.in_(assigned)))

def require_writer(db,u,t):
    require(u,"staff","leader")
    if t.status not in {"working","revision"}: fail(409,"仅办理中或修改中的任务可编辑")
    if t.owner!=u.id and not db.get(Member,(t.id,u.id)): fail(403,"仅本任务承办或协办人可编辑")

def checked_revision(obj,revision):
    if obj.revision!=revision: fail(409,"记录已由其他人更新，请刷新后重试")

class ClientData(Form):
    name:str=Field(min_length=1,max_length=128)
    code:str=Field(pattern=r"^[0-9A-Z]{18}$")
    industry_code:str=Field(default="",max_length=16)
    industry:str=Field(default="",max_length=64)
    address:str=Field(default="",max_length=160)
    taxpayer:str=Field(default="",max_length=40)
    assessment:str=Field(default="",max_length=40)
    hightech:bool=False
    sme:bool=False
    level:Literal["重点","一般","潜在"]="一般"
    source:str=Field(default="",max_length=80)
    contact:str=Field(default="",max_length=64)
    phone:str=Field(default="",max_length=32)
    invoice:str=Field(default="",max_length=200)
    remark:str=Field(default="",max_length=500)
    revision:int=0

class Period(Form):
    start:date
    end:date
    @model_validator(mode="after")
    def dates(self):
        if self.end<self.start:raise ValueError("截至日期须晚于或等于开始日期")
        return self

class ContractData(Period):
    customer:int=Field(gt=0)
    code:str=Field(min_length=1,max_length=64)
    name:str=Field(min_length=1,max_length=128)
    amount:Decimal=Field(ge=0,max_digits=18,decimal_places=2)
    scope:str=Field(min_length=1,max_length=500)
    payment_terms:str=Field(default="",max_length=500)
    signed:date|None=None
    revision:int=0

class OrderData(Period):
    contract:int=Field(gt=0)
    code:str=Field(min_length=1,max_length=64)
    name:str=Field(min_length=1,max_length=128)
    service:str=Field(min_length=1,max_length=64)
    priority:Literal["normal","high","low"]="normal"
    standards:str=Field(min_length=1,max_length=1000)
    line:Literal["finance","research"]
    revision:int=0

class TaskData(Form):
    order_id:int=Field(gt=0)
    title:str=Field(min_length=1,max_length=128)
    owner:int=Field(gt=0)
    assistants:list[int]=Field(default_factory=list,max_length=32)
    line:Literal["finance","research"]
    kind:Literal["立项","跟进","调整","结题","费用归集","辅助账","专项申报","高企认定"]
    major:bool=False
    deadline:date
    brief:str=Field(min_length=1,max_length=1000)

class ProjectData(Period):
    code:str=Field(min_length=1,max_length=64)
    name:str=Field(min_length=1,max_length=128)
    leader:str=Field(min_length=1,max_length=64)
    budget:Decimal=Field(ge=0,max_digits=18,decimal_places=2)
    category:Literal["自主","委托","合作","集中"]="自主"
    treatment:Literal["费用化","资本化"]="费用化"
    objective:str=Field(min_length=1,max_length=1000)
    innovation:str=Field(min_length=1,max_length=1000)
    uncertainty:str=Field(min_length=1,max_length=1000)

class Draft(Form):
    revision:int=Field(gt=0)
    summary:str=Field(min_length=1,max_length=6000)
    projects:list[ProjectData]=Field(default_factory=list,max_length=250)

class Decision(Form):
    revision:int=Field(gt=0)
    version:int=Field(ge=0,default=0)
    opinion:str=Field(default="",max_length=3000)
    result:Literal["pass","return"]="pass"
    owner:int|None=Field(default=None,gt=0)

def object_info(row):
    out={c.name:getattr(row,c.name) for c in row.__table__.columns}
    return jsonable_encoder(out)

def page_out(db,stmt,page,size):
    from sqlalchemy import func
    if page<1 or not 1<=size<=200:fail(422,"分页范围错误")
    total=db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows=db.scalars(stmt.limit(size).offset((page-1)*size))
    return ok({"items":[object_info(r) for r in rows],"total":total,"page":page,"page_size":size})

@router.get("/customers")
def customers(db:DB,u:Actor,q:str="",page:int=1,page_size:int=50):
    return page_out(db,select(Customer).where(access_customers(db,u),Customer.deleted.is_(False),
        Customer.name.contains(q,autoescape=True)|Customer.code.contains(q,autoescape=True)).order_by(Customer.id.desc()),page,page_size)

def save_client(db,u,request,form,c):
    c.name=form.name;c.code=form.code
    c.details=form.model_dump(exclude={"name","code","revision"})
    c.details["negative_hint"]=form.industry_code.startswith(("16","51","52","61","62","70","71","72","90"))
    db.add(c);db.flush();record(db,request,u,"customer.save",c.id);db.commit()
    return ok(object_info(c))

@router.post("/customers")
def new_client(form:ClientData,request:Request,db:DB,u:Actor):
    require(u,"manager","director")
    return save_client(db,u,request,form,Customer(manager=u.id,department=u.department))

@router.put("/customers/{cid}")
def edit_client(cid:int,form:ClientData,request:Request,db:DB,u:Actor):
    c=manage_customer(db,u,cid);checked_revision(c,form.revision)
    return save_client(db,u,request,form,c)

@router.delete("/customers/{cid}")
def delete_client(cid:int,request:Request,db:DB,u:Actor):
    c=manage_customer(db,u,cid)
    if db.scalar(select(Contract.id).where(Contract.customer==cid).limit(1)):fail(409,"客户已关联合同，请保留历史档案")
    c.deleted=True;record(db,request,u,"customer.archive",cid);db.commit()
    return ok()

@router.get("/customers/{cid}")
def overview(cid:int,db:DB,u:Actor):
    c=visible_customer(db,u,cid)
    return ok({"customer":object_info(c),
        "contracts":[object_info(i) for i in db.scalars(select(Contract).where(Contract.customer==cid,commercial_scope(db,u,Contract)))],
        "orders":[object_info(i) for i in db.scalars(select(Order).where(Order.customer==cid,commercial_scope(db,u,Order)))],
        "tasks":[object_info(i) for i in db.scalars(select(Task).where(Task.customer==cid,access_tasks(db,u)))],
        "projects":[object_info(i) for i in db.scalars(projects_query(db,u).where(Project.customer==cid))]})

@router.get("/contracts")
def contracts(db:DB,u:Actor,page:int=1,page_size:int=50):
    return page_out(db,select(Contract).where(commercial_scope(db,u,Contract)).order_by(Contract.id.desc()),page,page_size)

def save_contract(c,form,db,u,request):
    previous=object_info(c) if c.id else None
    c.customer=form.customer;c.code=form.code;c.name=form.name;c.amount=form.amount
    c.details=form.model_dump(mode="json",exclude={"customer","code","name","amount","revision"})
    c.status="draft"
    db.add(c);db.flush();record(db,request,u,"contract.save",c.id,{"previous":previous});db.commit()
    return ok(object_info(c))

@router.post("/contracts")
def add_contract(form:ContractData,request:Request,db:DB,u:Actor):
    manage_customer(db,u,form.customer)
    return save_contract(Contract(),form,db,u,request)

@router.put("/contracts/{cid}")
def edit_contract(cid:int,form:ContractData,request:Request,db:DB,u:Actor):
    c=db.get(Contract,cid)
    if not c:fail(404,"找不到合同")
    manage_customer(db,u,c.customer);checked_revision(c,form.revision)
    if form.customer!=c.customer:fail(422,"合同不可变更所属客户")
    return save_contract(c,form,db,u,request)

@router.post("/contracts/{cid}/approve")
def approve_contract(cid:int,form:Decision,request:Request,db:DB,u:Actor):
    require(u,"director")
    c=db.get(Contract,cid)
    if not c:fail(404,"找不到合同")
    client=visible_customer(db,u,c.customer);checked_revision(c,form.revision)
    if client.manager==u.id:fail(403,"客户负责人不得自审合同")
    if c.status!="draft":fail(409,"合同已审核")
    c.status="approved";record(db,request,u,"contract.approve",cid);db.commit();return ok(object_info(c))

@router.get("/orders")
def orders(db:DB,u:Actor,page:int=1,page_size:int=50):
    return page_out(db,select(Order).where(commercial_scope(db,u,Order)).order_by(Order.id.desc()),page,page_size)

def save_order(o,form,db,u,request):
    c=db.get(Contract,form.contract)
    if not c:fail(404,"合同不存在")
    manage_customer(db,u,c.customer)
    if c.status!="approved":fail(409,"请先完成合同审批")
    if o.id and o.contract!=c.id:fail(422,"不可变更既有订单的合同")
    o.contract=c.id;o.customer=c.customer;o.name=form.name;o.code=form.code
    o.details=form.model_dump(mode="json",exclude={"contract","name","code","revision"})
    db.add(o);db.flush();record(db,request,u,"order.save",o.id);db.commit();return ok(object_info(o))

@router.post("/orders")
def add_order(form:OrderData,request:Request,db:DB,u:Actor):
    return save_order(Order(),form,db,u,request)

@router.put("/orders/{oid}")
def edit_order(oid:int,form:OrderData,request:Request,db:DB,u:Actor):
    o=db.get(Order,oid)
    if not o:fail(404,"订单不存在")
    checked_revision(o,form.revision)
    return save_order(o,form,db,u,request)

def event(db,t,u,action,note="",snapshot=None):
    db.add(History(task=t.id,actor=u.id,action=action,version=t.version,note=note,snapshot=snapshot))

def assignable(db,u,uid,line):
    person=db.get(User,uid)
    if not person or not person.enabled or not roles(person).intersection({"staff","leader"}):fail(422,"承办人须为启用的承办岗位")
    if db.get(Department,person.department).line!=line:fail(422,"承办人业务线不符")
    if roles(u)=={"leader"} and (person.department!=u.department or person.team!=u.team):fail(403,"主管只能在本团队分派")
    if uid==u.id:fail(403,"派单与经办须由不同人员承担")
    return person

@router.post("/tasks")
def assign(form:TaskData,request:Request,db:DB,u:Actor):
    require(u,"manager","director","leader")
    o=db.scalar(select(Order).where(Order.id==form.order_id,commercial_scope(db,u,Order)))
    if not o:fail(404,"订单不存在或不在数据范围")
    owner=assignable(db,u,form.owner,form.line)
    if form.kind in {"立项","调整","结题"} and form.line!="research":fail(422,"请指派科研线")
    if form.kind in {"费用归集","辅助账"} and form.line!="finance":fail(422,"请指派财务线")
    t=Task(order_id=o.id,customer=o.customer,title=form.title,kind=form.kind,owner=owner.id,
           dispatcher=u.id,department=owner.department,team=owner.team,line=form.line,
           deadline=form.deadline.isoformat(),major=form.major or form.kind in {"专项申报","高企认定"},brief=form.brief)
    db.add(t);db.flush()
    for uid in set(form.assistants)-{owner.id}:
        person=db.get(User,uid)
        if not person or not person.enabled or uid==u.id or not roles(person).intersection({"staff","leader"}):fail(422,"协办岗位无效")
        if roles(u)=={"leader"} and (person.department!=u.department or person.team!=u.team):fail(403,"主管只可指定本团队协办人")
        db.add(Member(task=t.id,user=uid))
    event(db,t,u,"assign",form.brief);record(db,request,u,"task.assign",t.id);db.commit();return ok(object_info(t))

@router.get("/tasks")
def tasks(db:DB,u:Actor,page:int=1,page_size:int=50,status:str="",owner:int|None=None):
    q=select(Task).where(access_tasks(db,u))
    if status:q=q.where(Task.status==status)
    if owner:q=q.where(Task.owner==owner)
    return page_out(db,q.order_by(Task.id.desc()),page,page_size)

@router.get("/tasks/{tid}")
def task_detail(tid:int,db:DB,u:Actor):
    t=visible_task(db,u,tid)
    return ok({"task":object_info(t),"history":[object_info(i) for i in db.scalars(select(History).where(History.task==tid).order_by(History.id))],
        "entries":[object_info(i) for i in db.scalars(select(Entry).where(Entry.task==tid))],
        "files":[file_info(i) for i in db.scalars(select(FileObject).where(FileObject.task==tid))]})

def file_info(f):
    return fields(f,"id","task","project","category","name","digest","size","previous","actor","at")

@router.put("/tasks/{tid}/draft")
def draft(tid:int,form:Draft,request:Request,db:DB,u:Actor):
    t=visible_task(db,u,tid,True);require_writer(db,u,t);checked_revision(t,form.revision)
    if form.projects and t.kind!="立项":fail(422,"仅立项任务可创建项目清单")
    if len({p.code for p in form.projects})!=len(form.projects):fail(422,"项目编号重复")
    t.draft=form.model_dump(mode="json",exclude={"revision"})
    record(db,request,u,"draft.edit",tid);db.commit();return ok(object_info(t))

def business_snapshot(db,t):
    return {"draft":t.draft,"entries":[object_info(i) for i in db.scalars(select(Entry).where(Entry.task==t.id))],
            "files":[jsonable_encoder(file_info(i)) for i in db.scalars(select(FileObject).where(FileObject.task==t.id))],
            "projects":[object_info(i) for i in db.scalars(select(Project).where(Project.order_id==t.order_id))]}

def publish_projects(db,t):
    if t.kind!="立项":return
    submitted=t.draft.get("projects",[])
    existing=list(db.scalars(select(Project).where(Project.task==t.id)))
    if {p.code for p in existing}-{p["code"] for p in submitted}:fail(409,"已发布的项目不可移除，请办理项目调整")
    for p in submitted:
        obj=next((i for i in existing if i.code==p["code"]),None)
        if not obj:
            obj=Project(customer=t.customer,task=t.id,order_id=t.order_id,code=p["code"])
            db.add(obj)
        obj.name=p["name"];obj.budget=Decimal(p["budget"]);obj.details=p

@router.post("/tasks/{tid}/{action}")
def advance(tid:int,action:Literal["accept","reject","reassign","suspend","resume","submit","audit","confirm","archive"],form:Decision,request:Request,db:DB,u:Actor):
    t=visible_task(db,u,tid,True);checked_revision(t,form.revision)
    note=form.opinion
    if (action in {"reject","reassign","suspend","confirm"} or form.result=="return") and not note:fail(422,"请填写办理意见或凭据")
    before=t.status;snapshot=None
    if action in {"accept","reject"}:
        if t.status!="assigned" or t.owner!=u.id:fail(403,"仅待接件任务的主办人可处理")
        require(u,"staff","leader")
        t.status="working" if action=="accept" else "unassigned"
    elif action=="reassign":
        require(u,"leader","manager","director")
        if t.status not in {"unassigned","assigned"} or not form.owner:fail(409,"仅待派或待接件任务可指定新主办人")
        owner=assignable(db,u,form.owner,t.line)
        t.owner=owner.id;t.department=owner.department;t.team=owner.team;t.dispatcher=u.id;t.status="assigned"
    elif action=="suspend":
        require_writer(db,u,t);t.previous=t.status;t.status="suspended"
    elif action=="resume":
        if t.status!="suspended" or u.id not in {t.owner,t.dispatcher}:fail(403,"无法恢复此任务")
        t.status=t.previous;t.previous=None
    elif action=="submit":
        require_writer(db,u,t)
        if t.owner!=u.id or not t.draft.get("summary"):fail(422,"请由主办人填写底稿并提交")
        if t.kind=="立项" and not t.draft.get("projects"):fail(422,"请填写立项清单")
        if t.line=="finance" and not db.scalar(select(Project.id).where(Project.order_id==t.order_id).limit(1)):fail(409,"财务需等待同订单立项通过内部审核")
        pending=db.scalar(select(Entry.id).where(Entry.task==tid,Entry.kind=="issue",Entry.state!="closed").limit(1))
        if pending:fail(409,"请先关闭补件")
        if t.kind=="结题":
            signatures=set(db.scalars(select(Entry.key).where(Entry.task==tid,Entry.kind=="cosign",Entry.state=="signed")))
            if signatures!={"research","finance"}:fail(409,"结题需要两线联签")
        t.version+=1;t.status="leader";snapshot=business_snapshot(db,t)
    elif action=="audit":
        if t.status not in {"leader","manager","director"}:fail(409,"当前状态不能审核")
        require(u,t.status)
        if form.version!=t.version:fail(409,"请审核当前提交版本")
        acted=db.scalar(select(History.id).where(History.task==tid,History.actor==u.id,
            History.action.in_(["assign","reassign","submit","audit.pass"])).limit(1)) if t.version==1 else db.scalar(select(History.id).where(History.task==tid,History.actor==u.id,
            or_(History.action.in_(["assign","reassign","submit"]),and_(History.version==t.version,History.action=="audit.pass"))).limit(1))
        if u.id in {t.dispatcher,t.owner} or db.get(Member,(tid,u.id)) or acted:fail(403,"派单、经办和逐级审核须回避")
        if form.result=="return":t.status="revision"
        else:
            t.status={"leader":"manager","manager":"director" if t.major else "customer","director":"customer"}[t.status]
            if t.status=="customer":publish_projects(db,t)
    elif action=="confirm":
        require(u,"manager","director")
        if t.status!="customer":fail(409,"尚未进入客户确认")
        t.status="complete" if form.result=="pass" else "revision"
    elif action=="archive":
        require(u,"manager","director","admin")
        if t.status!="complete":fail(409,"仅客户确认后可归档")
        t.status="archived";snapshot=business_snapshot(db,t)
    event(db,t,u,action+("."+form.result if action in {"audit","confirm"} else ""),note,snapshot)
    record(db,request,u,"task."+action,tid,{"from":before,"to":t.status,"version":t.version})
    db.commit();return ok(object_info(t))

@router.get("/projects")
def projects(db:DB,u:Actor,page:int=1,page_size:int=50):
    return page_out(db,projects_query(db,u).order_by(Project.id),page,page_size)
