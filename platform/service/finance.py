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
    return finish(db,u,request,save(db,u,t,"flow",form,p.project,"posted"))

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
    shares=distribute(total,hours)
    for pid,share in shares.items():
        if pid is None:continue
        project=db.get(Project,pid)
        f=Fee(task=t.id,key=f"PAY/{a.id}/{pid}",project=pid,day=p["month"]+"-01",voucher=p["voucher"],subject="人员薪酬",category="人员人工",
              amount=share,note=p["person"]+"工时分摊",type="共用",basis=f"考勤记录 {a.id}",positive=p["direct"],hightech=p["tech"],treatment=project.details["treatment"])
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
        for row in rows:
            ws.append(list(row))
            for c in ws[ws.max_row]:
                if c.data_type=="f":c.data_type="s"
                if isinstance(c.value,Decimal):c.number_format='#,##0.00'
        for cell in ws[1]:
            cell.font=Font(color="FFFFFF",bold=True);cell.fill=PatternFill("solid",fgColor="142648")
        ws.freeze_panes="A2"
        for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=min(48,max(14,max(len(str(c.value or "")) for c in col)*1.4))
    stream=BytesIO();book.save(stream);return stream.getvalue()

class Ledger(Form):
    customer:int=Field(gt=0)
    year:int=Field(ge=2015,le=2099)
    edition:Literal["2015","2021"]="2021"

def ledger(form,db,u):
    c=visible_customer(db,u,form.customer)
    require(u,"manager","director")
    if u.department!=c.department and u.id!=c.manager:fail(403,"完整企业汇总需要客户管理权限")
    projects=list(db.scalars(select(Project).where(Project.customer==c.id)))
    raw=list(db.scalars(select(Entry).join(Task,Task.id==Entry.task).where(Task.customer==c.id,Entry.kind=="fee")))
    pending=[e for e in raw if e.payload["day"].startswith(str(form.year)) and db.get(Task,e.task).status not in {"customer","complete","archived"}]
    if pending:fail(409,"年度内尚有费用任务未通过末级内审")
    rows=[e for e in raw if e.payload["day"].startswith(str(form.year))]
    buckets={p.id:[Decimal(0)]*len(CATEGORIES) for p in projects}
    account=defaultdict(Decimal);high=defaultdict(lambda:[Decimal(0)]*len(CATEGORIES));offset=defaultdict(Decimal)
    warnings=[];details=[]
    for e in rows:
        p=e.payload;v=amounts(e,"amount");i=CATEGORIES.index(p["category"]);pid=e.project
        details.append([pid,p["day"],p["voucher"],p["subject"],p["note"],p["category"],v,p["type"],p["basis"]])
        if p["treatment"]=="资本化":
            warnings.append("有资本化支出，须另核无形资产形成年度与摊销进度")
        if p["type"]=="试运行销售":
            warnings.append("试运行销售单列收入与成本，不纳入研发费用");continue
        if p["type"] in {"产品材料冲减","特殊收入","不征税补助"}:
            offset[pid]+=v;continue
        account[pid]+=v
        if p["hightech"]:high[pid][i]+=v*(Decimal(".8") if i>=6 else 1)
        if p["type"] in {"房屋折旧租赁","长期待摊"} or (p["type"]=="共用" and not p["basis"]) or not p["positive"] or i==8:
            warnings.append(f"{p['voucher']}：未纳入加计口径");continue
        buckets[pid][i]+=v
    first=sum(sum(b[:5]) for b in buckets.values())
    others={k:b[5] for k,b in buckets.items()}
    allowed_other=distribute(min(sum(others.values()),cent(Decimal(first)/9)),others)
    domestic={k:cent(v[6]*Decimal(".8")) for k,v in buckets.items()}
    foreign={k:b[7] for k,b in buckets.items()}
    limit=cent((first+sum(allowed_other.values())+sum(domestic.values()))*2/3)
    allowed_foreign=distribute(min(cent(sum(foreign.values())*Decimal(".8")),limit),foreign)
    result=[]
    for project in projects:
        k=project.id;b=buckets[k];h=high[k]
        high_other=min(h[5],cent((sum(h)-h[5])/4))
        allowed=max(Decimal(0),sum(b[:5])+allowed_other[k]+domestic[k]+allowed_foreign[k]-offset[k])
        if c.details.get("negative_hint"):warnings.append("客户行业需核实是否属于负面清单")
        result.append({"id":k,"code":project.code,"name":project.name,"category":project.details["category"],
            "account":str(cent(account[k])),"hightech":str(cent(sum(h)-h[5]+high_other)),"deduction":str(cent(allowed)),
            "first_five":str(sum(b[:5])),"other":str(b[5]),"other_allowed":str(allowed_other[k]),
            "domestic_allowed":str(domestic[k]),"foreign_allowed":str(allowed_foreign[k]),"offset":str(offset[k])})
    return {"customer":c.name,"year":form.year,"edition":form.edition,"projects":result,"warnings":sorted(set(warnings)),
        "details":details,"policy":"2021年第28号：其他费用年度统一限额、委托境外限额","status":"复核底稿"}

@router.post("/subsidiary/generate")
def generate(form:Ledger,request:Request,db:DB,u:Actor):
    result=ledger(form,db,u);record(db,request,u,"ledger.generate",form.customer,{"year":form.year,"edition":form.edition})
    db.commit();return ok(result)

@router.get("/subsidiary")
def ledger_export(customer:int,year:int,edition:Literal["2015","2021"],request:Request,db:DB,u:Actor):
    result=ledger(Ledger(customer=customer,year=year,edition=edition),db,u)
    summary=[["项目编号","项目名称","会计金额","高企金额","加计归集初算","其他费用允许额","委托境内允许额","委托境外允许额","冲减额"]]+[
        [p["code"],p["name"],*[Decimal(p[k]) for k in ("account","hightech","deduction","other_allowed","domestic_allowed","foreign_allowed","offset")]] for p in result["projects"]]
    head=["项目ID","凭证日期","凭证编号","科目","摘要","类别","凭证金额","事项","分摊依据"]
    sheets=[("复核汇总",summary)]
    if edition=="2015":
        for kind in ["自主","委托","合作","集中"]:
            ids={p["id"] for p in result["projects"] if p["category"]==kind}
            sheets.append((kind+"研发明细",[head]+[r for r in result["details"] if r[0] in ids]))
    else:sheets.append(("研发支出明细",[head]+result["details"]))
    sheets.append(("复核提示",[["说明"],[result["policy"]],["供内部复核；正式申报须按年度表样及资本化、跨年冲减记录另行勾稽。"]]+[[s] for s in result["warnings"]]))
    record(db,request,u,"ledger.download",customer,{"year":year,"edition":edition});db.commit()
    return deliver(write_xlsx(sheets),f"{year}-{edition}版费用复核底稿.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
