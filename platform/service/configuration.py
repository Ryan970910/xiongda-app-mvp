from datetime import date
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter,Request
from pydantic import Field,model_validator
from sqlalchemy import Column,ForeignKey,JSON,String,select

from .auth import Actor,DB,Form,fail,ok,record,require
from .db import Base,ID,now

router=APIRouter()
class PublishedConfig(Base):
    __tablename__="sys_config_version"
    id=Column(ID,primary_key=True)
    kind=Column(String(32),nullable=False,index=True)
    key=Column(String(80),nullable=False,index=True)
    payload=Column(JSON,nullable=False)
    actor=Column(ID,ForeignKey("sys_user.id"),nullable=False)

class Rules(Form):
    leader_hours:int=Field(default=48,ge=1,le=720)
    manager_hours:int=Field(default=48,ge=1,le=720)
    director_hours:int=Field(default=48,ge=1,le=720)
    amount:Decimal=Field(ge=0,max_digits=18,decimal_places=2)
    kinds:list[Literal["立项","跟进","调整","结题","费用归集","辅助账","专项申报","高企认定"]]
    reason:str=Field(min_length=1,max_length=300)

class TemplateChange(Form):
    code:str=Field(pattern=r"^[A-Za-z0-9_-]{2,50}$")
    category:str=Field(min_length=1,max_length=40)
    name:str=Field(min_length=1,max_length=100)
    scenario:str=Field(min_length=1,max_length=400)
    columns:str=Field(min_length=1,max_length=1000)
    reason:str=Field(min_length=1,max_length=300)

def publish(db,request,u,kind,key,payload):
    item=PublishedConfig(kind=kind,key=key,payload={**payload,"published":now().isoformat()},actor=u.id)
    db.add(item);db.flush();record(db,request,u,"config."+kind,item.id,{"key":key});db.commit();return ok({"id":item.id})

def routing(db):
    item=db.scalar(select(PublishedConfig).where(PublishedConfig.kind=="routing").order_by(PublishedConfig.id.desc()).limit(1))
    return item.payload if item else {"amount":"0","kinds":["专项申报","高企认定"]}

@router.get("/system/routing-rules")
def current(db:DB,u:Actor):
    require(u,"admin","manager","director","leader");return ok(routing(db))

@router.post("/system/routing-rules")
def update(form:Rules,request:Request,db:DB,u:Actor):
    require(u,"admin");return publish(db,request,u,"routing","workflow",form.model_dump(mode="json"))

@router.post("/system/template-versions")
def template(form:TemplateChange,request:Request,db:DB,u:Actor):
    require(u,"admin")
    from .materials import CATALOG
    categories={x["category"]:x["kind"] for x in CATALOG}
    if form.category not in categories:fail(422,"请使用模板库中的文种编号")
    cols=[x.strip() for x in form.columns.splitlines() if x.strip()]
    if not 1<=len(cols)<=40 or len(cols)!=len(set(cols)):fail(422,"模板栏目需唯一，最多40项")
    payload={"id":form.code,"name":form.name,"kind":categories[form.category],"scenario":form.scenario,
             "category":form.category,"fields":cols,"reason":form.reason}
    return publish(db,request,u,"template",form.code,payload)

def catalog(db):
    from .materials import TEMPLATES
    out=dict(TEMPLATES)
    for v in db.scalars(select(PublishedConfig).where(PublishedConfig.kind=="template").order_by(PublishedConfig.id)):
        out[v.key]={**v.payload,"version":v.id}
    return out

class RiskRule(Form):
    code:str=Field(pattern=r"^[a-zA-Z0-9_-]{2,60}$")
    name:str=Field(min_length=1,max_length=100)
    applies:Literal["全部","research","finance"]="全部"
    condition:Literal["未上传证明材料","项目缺里程碑","凭证缺分摊依据","工时超过阈值","单笔费用超过阈值","补件未关闭"]
    threshold:Decimal=Field(default=0,ge=0,max_digits=18,decimal_places=2)
    severity:Literal["提示","警告","阻断"]
    reference:str=Field(min_length=1,max_length=180)
    effective:date
    enabled:bool=True
    reason:str=Field(min_length=1,max_length=300)

@router.post("/system/risk-rules")
def risk_rule(form:RiskRule,request:Request,db:DB,u:Actor):
    require(u,"admin")
    return publish(db,request,u,"risk",form.code,form.model_dump(mode="json"))

@router.get("/system/risk-rules")
def risk_versions(db:DB,u:Actor):
    require(u,"admin","leader","manager","director")
    rows=db.scalars(select(PublishedConfig).where(PublishedConfig.kind=="risk").order_by(PublishedConfig.id.desc()))
    return ok([{"id":r.id,**r.payload} for r in rows])

def effective_rules(db,day):
    result={}
    for item in db.scalars(select(PublishedConfig).where(PublishedConfig.kind=="risk").order_by(PublishedConfig.id)):
        rule=item.payload
        if rule["effective"]<=day and (item.key not in result or result[item.key]["effective"]<=rule["effective"]):
            result[item.key]={**rule,"id":item.id}
    return [r for r in result.values() if r["enabled"]]

def rule_hits(rules,t,entries,files):
    hits=[]
    for r in rules:
        if r["applies"] not in {"全部",t.line}:continue
        test=r["condition"];limit=Decimal(r["threshold"])
        match=(test=="未上传证明材料" and not files or test=="项目缺里程碑" and any(not p.get("milestones") for p in t.draft.get("projects",[]))
               or test=="补件未关闭" and any(e.kind=="issue" and e.state!="closed" for e in entries)
               or test=="凭证缺分摊依据" and any(e.kind=="fee" and e.payload["type"]=="共用" and not e.payload.get("basis") for e in entries)
               or test=="工时超过阈值" and any(e.kind=="hours" and Decimal(e.payload["hours"])>limit for e in entries)
               or test=="单笔费用超过阈值" and any(e.kind=="fee" and Decimal(e.payload["amount"])>limit for e in entries))
        if match:hits.append(r)
    return hits
