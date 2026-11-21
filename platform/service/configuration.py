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
