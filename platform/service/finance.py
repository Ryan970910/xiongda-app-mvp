from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from openpyxl import Workbook
from pydantic import Field, model_validator
from sqlalchemy import select

from .auth import DB, Actor, Form, fail, ok, record, require, roles
from .db import Entry, Project, Task
from .materials import deliver, project_for
from .workflow import access_tasks, object_info, require_writer, visible_customer, visible_task

router=APIRouter()
Money=Annotated[Decimal,Field(ge=0,max_digits=18,decimal_places=2)]
Positive=Annotated[Decimal,Field(gt=0,max_digits=16,decimal_places=2)]
CATEGORIES=["人员人工","直接投入","折旧","无形资产摊销","设计试验","其他相关","境内委托","境外机构委托","境外个人委托"]
CENT=Decimal(".01")
def cent(d): return d.quantize(CENT,rounding=ROUND_HALF_UP)
def amounts(e,key):return Decimal(str(e.payload.get(key,"0")))
def distribute(total,weights):
    if not weights or not sum(weights.values()):return {k:Decimal(0) for k in weights}
    whole=sum(weights.values())
    exact={k:total*v/whole for k,v in weights.items()}
    shares={k:v.quantize(CENT,rounding=ROUND_DOWN) for k,v in exact.items()}
    remainder=int((total-sum(shares.values()))*100)
    for k in sorted(weights,key=lambda k:(shares[k]-exact[k],str(k)))[:remainder]:shares[k]+=CENT
    return shares

class WorkBase(Form):
    task:int=Field(gt=0)
    key:str=Field(min_length=1,max_length=100)

class Attendance(WorkBase):
    person:str=Field(min_length=1,max_length=64)
    month:str=Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    hours:Positive
    salary:Money
    insurance:Money
    external:Money=Decimal(0)
    agreement:str=Field(default="",max_length=100)
    voucher:str=Field(min_length=1,max_length=100)
    direct:bool=True
    tech:bool=True

class Hours(WorkBase):
    person:str=Field(min_length=1,max_length=64)
    project:int|None=Field(default=None,gt=0)
    day:date
    hours:Decimal=Field(gt=0,le=24,decimal_places=2)
    activity:Literal["rd","nonrd"]
    @model_validator(mode="after")
    def allocation(self):
        if (self.activity=="rd")!=(self.project is not None):raise ValueError("研发工时须选项目，非研发工时单独登记")
        return self

class Trial(WorkBase):
    project:int=Field(gt=0)
    purpose:str=Field(min_length=1,max_length=1000)
    plan:str=Field(min_length=1,max_length=1000)
    demand:str=Field(min_length=1,max_length=1000)
    output:str=Field(min_length=1,max_length=1000)

class Pick(WorkBase):
    project:int=Field(gt=0)
    trial:int=Field(gt=0)
    material:str=Field(min_length=1,max_length=100)
    batch:str=Field(min_length=1,max_length=80)
    unit:str=Field(min_length=1,max_length=30)
    qty:Positive
    price:Money
    stock:Positive
    day:date
    @model_validator(mode="after")
    def available(self):
        if self.qty>self.stock:raise ValueError("领料数量超过登记的可用库存")
        return self

class Flow(WorkBase):
    pick:int=Field(gt=0)
    qty:Positive
    destination:Literal["transfer","consume","return","sample","disposal"]
    location:str=Field(min_length=1,max_length=128)
    day:date
    income:Money=Decimal(0)

class Fee(WorkBase):
    project:int=Field(gt=0)
    day:date
    voucher:str=Field(min_length=1,max_length=100)
    subject:str=Field(min_length=1,max_length=80)
    category:Literal["人员人工","直接投入","折旧","无形资产摊销","设计试验","其他相关","境内委托","境外机构委托","境外个人委托"]
    amount:Money
    treatment:Literal["费用化","资本化"]="费用化"
    note:str=Field(min_length=1,max_length=400)
    type:Literal["一般","房屋折旧租赁","长期待摊","共用","试运行销售","产品材料冲减","特殊收入","不征税补助"]="一般"
    basis:str=Field(default="",max_length=300)
    positive:bool=True
    hightech:bool=True
    tax_line:int|None=Field(default=None,ge=4,le=33)
    @model_validator(mode="after")
    def proper_line(self):
        allowed={"人员人工":range(4,7),"直接投入":range(8,16),"折旧":range(17,19),"无形资产摊销":range(20,23),"设计试验":range(24,28),"其他相关":range(29,34)}
        if self.tax_line and self.tax_line not in allowed.get(self.category,()):raise ValueError("申报明细行与费用类别不符")
        return self

def business_task(db,u,tid):
    t=visible_task(db,u,tid,True);require_writer(db,u,t)
    return t

def save(db,u,t,kind,form,project=None,state="draft"):
    e=Entry(task=t.id,kind=kind,key=form.key,project=project,state=state,payload=form.model_dump(mode="json"),actor=u.id)
    db.add(e);t.revision+=1;db.flush()
    return e

def finish(db,u,request,e):
    record(db,request,u,e.kind+".create",e.id);db.commit();return ok(object_info(e))

def workrows(db,u,kind):
    return list(db.scalars(select(Entry).where(Entry.kind==kind,Entry.task.in_(select(Task.id).where(access_tasks(db,u)))).order_by(Entry.id)))

@router.post("/attendance")
def attendance(form:Attendance,request:Request,db:DB,u:Actor):
    t=business_task(db,u,form.task)
    if t.line!="finance":fail(403,"工资信息由财务任务登记")
    if form.external and not form.agreement:fail(422,"外聘劳务需要协议和发票索引")
    form.key=form.month+"/"+form.person
    return finish(db,u,request,save(db,u,t,"attendance",form))

@router.post("/workhours")
def workhours(form:Hours,request:Request,db:DB,u:Actor):
    t=business_task(db,u,form.task);p=project_for(db,t,form.project)
    if p and not p.details["start"]<=form.day.isoformat()<=p.details["end"]:fail(422,"工时超出项目周期")
    rows=db.scalars(select(Entry).where(Entry.kind=="hours",Entry.task==t.id))
    existing=sum(amounts(e,"hours") for e in rows if e.payload["person"]==form.person and e.payload["day"]==form.day.isoformat())
    if existing+form.hours>24:fail(422,"该人员当天工时超过24小时")
    return finish(db,u,request,save(db,u,t,"hours",form,form.project))

class Review(Form):
    id:int=Field(gt=0)
    pass_review:bool=True
    opinion:str=Field(default="",max_length=500)

def review_entry(expected,form,request,db,u):
    e=db.get(Entry,form.id)
    if not e or e.kind!=expected:fail(404,"记录不存在")
    t=visible_task(db,u,e.task,True);require(u,"leader","manager","director")
    if t.status not in {"working","revision"} or e.state!="draft":fail(409,"此记录不能再审核")
    if e.actor==u.id:fail(403,"经办人不可自审")
    if not form.pass_review and not form.opinion:fail(422,"退回须填写原因")
    e.state="approved" if form.pass_review else "returned"
    e.payload={**e.payload,"reviewer":u.id,"opinion":form.opinion};t.revision+=1
    record(db,request,u,expected+".review",e.id,{"result":e.state});db.commit();return ok(object_info(e))

@router.post("/workhours/audit")
def review_hours(form:Review,request:Request,db:DB,u:Actor):return review_entry("hours",form,request,db,u)

@router.post("/trials")
def trial(form:Trial,request:Request,db:DB,u:Actor):
    t=business_task(db,u,form.task);project_for(db,t,form.project)
    return finish(db,u,request,save(db,u,t,"trial",form,form.project))

@router.post("/trials/audit")
def review_trial(form:Review,request:Request,db:DB,u:Actor):return review_entry("trial",form,request,db,u)

@router.post("/picks")
def pick(form:Pick,request:Request,db:DB,u:Actor):
    t=business_task(db,u,form.task);p=project_for(db,t,form.project)
    trial=db.get(Entry,form.trial)
    if not trial or trial.kind!="trial" or trial.task!=t.id or trial.project!=p.id or trial.state!="approved":
        fail(422,"须关联本项目审核通过的试制申请")
    if form.qty*form.price>p.budget:fail(422,"本次领料金额超过项目预算")
    return finish(db,u,request,save(db,u,t,"pick",form,p.id,"issued"))

def pick_balance(db,pick):
    rows=db.scalars(select(Entry).where(Entry.task==pick.task,Entry.kind=="flow"))
    moved=defaultdict(Decimal)
    for e in rows:
        if e.payload["pick"]==pick.id:moved[e.payload["destination"]]+=amounts(e,"qty")
    return amounts(pick,"qty")-sum(v for k,v in moved.items() if k!="transfer"),dict(moved)

@router.post("/flows")
def flow(form:Flow,request:Request,db:DB,u:Actor):
    t=business_task(db,u,form.task)
    p=db.get(Entry,form.pick)
    if not p or p.kind!="pick" or p.task!=t.id:fail(422,"请关联本任务原领料单")
    if form.day.isoformat()<p.payload["day"] or form.qty>pick_balance(db,p)[0]:fail(422,"流转日期或数量不符")
    if form.income and form.destination!="disposal":fail(422,"处置收入须关联处置记录")
    e=save(db,u,t,"flow",form,p.project,"posted")
    project=db.get(Project,p.project)
    if form.destination=="consume" or form.income:
        fee=Fee(task=t.id,key=f"MAT/{e.id}",project=p.project,day=form.day,voucher=form.key,subject="研发材料",
                category="直接投入",amount=cent(form.qty*amounts(p,"price")) if form.destination=="consume" else form.income,
                note=p.payload["material"]+" · "+form.location,type="一般" if form.destination=="consume" else "特殊收入",
                basis="领料单 "+p.key,tax_line=8,treatment=project.details["treatment"])
        save(db,u,t,"fee",fee,p.project,"posted")
    return finish(db,u,request,e)

@router.get("/material-ledger")
def material_ledger(db:DB,u:Actor):
    return ok([{**object_info(p),"balance":str(b),"movements":{k:str(v) for k,v in movements.items()}}
               for p in workrows(db,u,"pick") for b,movements in [pick_balance(db,p)]])

@router.post("/fee-collections")
def fee(form:Fee,request:Request,db:DB,u:Actor):
    t=business_task(db,u,form.task)
    if t.line!="finance":fail(403,"费用由财务任务登记")
    project_for(db,t,form.project)
    return finish(db,u,request,save(db,u,t,"fee",form,form.project,"posted"))

class Allocate(Form):
    task:int=Field(gt=0)
    attendance:int=Field(gt=0)

@router.post("/attendance/allocate")
def allocate(form:Allocate,request:Request,db:DB,u:Actor):
    t=business_task(db,u,form.task);a=db.get(Entry,form.attendance)
    if t.line!="finance" or not a or a.kind!="attendance" or a.task!=t.id or a.state=="allocated":fail(409,"考勤已归集或不属于当前财务任务")
    p=a.payload;hours=defaultdict(Decimal)
    for e in db.scalars(select(Entry).where(Entry.task==t.id,Entry.kind=="hours")):
        if e.payload["person"]==p["person"] and e.payload["day"].startswith(p["month"]) and e.state!="returned":
            if e.state!="approved":fail(409,"尚有待审核工时")
            hours[e.project]+=amounts(e,"hours")
    if sum(hours.values())!=amounts(a,"hours"):fail(422,"审核通过的研发及非研发总工时须等于实际出勤工时")
    total=sum(amounts(a,k) for k in ["salary","insurance","external"])
    shares=defaultdict(Decimal)
    for field,taxline,subject in [("salary",4,"工资"),("insurance",5,"五险一金"),("external",6,"外聘劳务")]:
        for pid,share in distribute(amounts(a,field),hours).items():
            shares[pid]+=share
            if pid is None or not share:continue
            project=db.get(Project,pid)
            f=Fee(task=t.id,key=f"PAY/{a.id}/{pid}/{field}",project=pid,day=p["month"]+"-01",voucher=p["voucher"],subject=subject,category="人员人工",
                  amount=share,note=p["person"]+"工时分摊",type="共用",basis=f"考勤记录 {a.id}",positive=p["direct"],hightech=p["tech"],
                  tax_line=taxline,treatment=project.details["treatment"])
            save(db,u,t,"fee",f,pid,"posted")
    a.state="allocated";a.payload={**a.payload,"allocations":{str(k or "非研发"):str(v) for k,v in shares.items()}}
    record(db,request,u,"payroll.allocate",a.id);db.commit();return ok(a.payload)

def list_kind(kind):
    def endpoint(db:DB,u:Actor):
        return ok([object_info(e) for e in workrows(db,u,kind)])
    return endpoint
for route,kind in [("attendance","attendance"),("workhours","hours"),("trials","trial"),("picks","pick"),("flows","flow"),("fee-collections","fee")]:
    router.add_api_route("/"+route,list_kind(kind),methods=["GET"],name="list_"+kind)

def write_xlsx(sheets):
    book=Workbook();book.remove(book.active)
    from openpyxl.styles import Font,PatternFill
    for title,rows in sheets:
        ws=book.create_sheet(title[:31])
        widths={}
        for number,row in enumerate(rows,1):
            ws.append(list(row))
            for i,value in enumerate(row,1):
                c=ws.cell(number,i)
                if c.data_type=="f":c.data_type="s"
                if isinstance(c.value,Decimal):c.number_format='#,##0.00'
                widths[c.column_letter]=max(widths.get(c.column_letter,14),min(48,len(str(value or ""))*1.4))
        for cell in ws[1]:
            cell.font=Font(color="FFFFFF",bold=True);cell.fill=PatternFill("solid",fgColor="142648")
        ws.freeze_panes="A2"
        for column,width in widths.items():ws.column_dimensions[column].width=width
    stream=BytesIO();book.save(stream);return stream.getvalue()
