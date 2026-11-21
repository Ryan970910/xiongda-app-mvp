from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import ForeignKey, String, Column, JSON, select

from .auth import Actor, DB, Form, fail, ok, record, require
from .db import Base, ID, Contract, Entry, FileObject, History, Project, Task, User
from .finance import WorkBase, save, write_xlsx
from .materials import deliver, project_for
from .workflow import (ProjectData, access_tasks, manage_customer, object_info,
                       require_writer, visible_customer, visible_task)

router=APIRouter()

class Receipt(Base):
    __tablename__="biz_receipt"
    id=Column(ID,primary_key=True)
    contract=Column(ID,ForeignKey("biz_contract.id"),nullable=False)
    reference=Column(String(100),unique=True,nullable=False)
    payload=Column(JSON,nullable=False)
    actor=Column(ID,ForeignKey("sys_user.id"),nullable=False)

class Policy(Base):
    __tablename__="policy_version"
    id=Column(ID,primary_key=True)
    payload=Column(JSON,nullable=False)
    actor=Column(ID,ForeignKey("sys_user.id"),nullable=False)

class Payment(Form):
    contract:int
    reference:str=Field(min_length=1,max_length=100)
    day:date
    amount:Decimal=Field(gt=0,decimal_places=2,max_digits=18)
    note:str=Field(default="",max_length=300)

@router.post("/receipts")
def receive(form:Payment,request:Request,db:DB,u:Actor):
    c=db.get(Contract,form.contract)
    if not c:fail(404,"合同不存在")
    manage_customer(db,u,c.customer)
    if c.status!="approved":fail(409,"待合同审核后登记收款")
    rows=db.scalars(select(Receipt).where(Receipt.contract==c.id))
    if sum(Decimal(r.payload["amount"]) for r in rows)+form.amount>c.amount:fail(422,"累计收款超过合同金额")
    item=Receipt(contract=c.id,reference=form.reference,payload=form.model_dump(mode="json"),actor=u.id)
    db.add(item);c.revision+=1;db.flush();record(db,request,u,"contract.payment",item.id);db.commit()
    return ok(object_info(item))

@router.get("/receipts")
def payments(customer:int,db:DB,u:Actor):
    manage_customer(db,u,customer)
    return ok([object_info(r) for r in db.scalars(select(Receipt).join(Contract,Contract.id==Receipt.contract).where(Contract.customer==customer))])

class Achievement(WorkBase):
    project:int
    name:str=Field(min_length=1,max_length=128)
    category:Literal["专利","软件著作权","商标","论文","样品样机","其他"]
    day:date
    registration:str=Field(min_length=1,max_length=120)
    holder:str=Field(min_length=1,max_length=120)
    evidence:int
    conversion:str=Field(default="",max_length=1000)

class Adjustment(WorkBase):
    project:int
    after:ProjectData
    reason:str=Field(min_length=1,max_length=1000)
    impact:str=Field(min_length=1,max_length=1500)

class Note(WorkBase):
    project:int|None=None
    category:Literal["前置会商","立项资料","考勤工资","领料凭证","发票","检测报告","验收材料","风险整改","后续服务"]
    state:Literal["未提供","待补充","已提供","已记录","已整改"]
    note:str=Field(min_length=1,max_length=1500)
    evidence:int|None=None

def linked_file(db,t,pid,fid):
    f=db.get(FileObject,fid)
    if not f or f.task!=t.id or (pid is not None and f.project!=pid):fail(422,"证明文件须与当前任务、项目匹配")

def working(db,u,form):
    t=visible_task(db,u,form.task,True);require_writer(db,u,t)
    p=project_for(db,t,form.project)
    return t,p

def saved(db,request,u,e):
    record(db,request,u,e.kind+".save",e.id);db.commit();return ok(object_info(e))

@router.post("/achievements")
def achievement(form:Achievement,request:Request,db:DB,u:Actor):
    t,p=working(db,u,form);linked_file(db,t,p.id,form.evidence)
    return saved(db,request,u,save(db,u,t,"achievement",form,p.id))

@router.get("/achievements")
def achievements(db:DB,u:Actor):
    return ok([object_info(e) for e in db.scalars(select(Entry).where(Entry.kind=="achievement",Entry.task.in_(select(Task.id).where(access_tasks(db,u)))))])

@router.post("/adjustments")
def adjust(form:Adjustment,request:Request,db:DB,u:Actor):
    t,p=working(db,u,form)
    if t.kind!="调整" or form.after.code!=p.code:fail(422,"请从调整任务选择原项目并保留原编号")
    fees=db.scalars(select(Entry).where(Entry.project==p.id,Entry.kind=="fee"))
    if form.after.budget<sum(Decimal(e.payload["amount"]) for e in fees):fail(422,"预算不能低于已登记费用")
    e=db.scalar(select(Entry).where(Entry.task==t.id,Entry.kind=="adjustment",Entry.project==p.id))
    if e:
        if e.state=="applied":fail(409,"已生效的变更需另发调整任务")
        t.revision+=1;e.payload=form.model_dump(mode="json")
    else:e=save(db,u,t,"adjustment",form,p.id)
    e.payload={**e.payload,"before":p.details}
    return saved(db,request,u,e)

def apply_changes(db,t):
    for e in db.scalars(select(Entry).where(Entry.task==t.id,Entry.kind=="adjustment",Entry.state=="draft")):
        p=db.scalar(select(Project).where(Project.id==e.project).with_for_update())
        if p.details!=e.payload["before"]:fail(409,"项目基线已更新，请退回重新核对")
        after=e.payload["after"];p.name=after["name"];p.budget=Decimal(after["budget"]);p.details=after;e.state="applied"

@router.post("/collections")
def collection(form:Note,request:Request,db:DB,u:Actor):
    t,p=working(db,u,form)
    if form.evidence:linked_file(db,t,form.project,form.evidence)
    if form.state=="已提供" and not form.evidence:fail(422,"收件登记须选择证明文件")
    e=db.scalar(select(Entry).where(Entry.task==t.id,Entry.kind=="collection",Entry.key==form.key))
    if e:
        if e.project!=form.project:fail(422,"原登记所关联项目不可变更")
        record(db,request,u,"collection.previous",e.id,e.payload)
        e.payload=form.model_dump(mode="json");e.state=form.state;t.revision+=1
    else:e=save(db,u,t,"collection",form,form.project,form.state)
    return saved(db,request,u,e)

@router.get("/risks")
def risks(db:DB,u:Actor):
    items=[]
    for t in db.scalars(select(Task).where(access_tasks(db,u))):
        es=list(db.scalars(select(Entry).where(Entry.task==t.id)))
        def add(key,severity,description):
            fixes=[e.payload["note"] for e in es if e.kind=="collection" and e.key==key and e.state=="已整改"]
            items.append({"task":t.id,"title":t.title,"key":key,"severity":severity,"description":description,"resolution":"；".join(fixes)})
        if not db.scalar(select(FileObject.id).where(FileObject.task==t.id).limit(1)):add("material","警告","任务尚未上传证明材料")
        if t.deadline<date.today().isoformat() and t.status not in {"complete","archived","suspended"}:add("deadline","提示","已过办理期限")
        from .db import Customer
        from .finance import pick_balance
        if db.get(Customer,t.customer).details.get("negative_hint"):add("industry","警告","请复核企业主营业务是否涉及负面清单")
        for project in t.draft.get("projects",[]):
            if not project.get("milestones"):add("milestone-"+project["code"],"提示",project["code"]+" 尚未登记量化里程碑")
        ratios={}
        for e in es:
            if e.kind=="collection" and e.state in {"未提供","待补充"}:add("missing-"+str(e.id),"警告",e.payload["category"]+"仍"+e.state)
            if e.kind=="issue" and e.state!="closed":add("issue-"+str(e.id),"阻断",e.payload["question"])
            if e.kind=="fee" and (not e.payload.get("positive",True) or (e.payload["type"]=="共用" and not e.payload["basis"])):add("fee-"+str(e.id),"警告",e.payload["voucher"]+"需核对加计资格与分摊依据")
            if e.kind=="pick" and pick_balance(db,e)[0]>0 and (date.today()-date.fromisoformat(e.payload["day"])).days>30:add("stock-"+str(e.id),"警告",e.key+" 领料超过30天仍有结存，请核对去向")
            if e.kind=="attendance":
                p=e.payload;total=Decimal(p["hours"]);rd=sum(Decimal(h.payload["hours"]) for h in es if h.kind=="hours" and h.state=="approved" and h.payload["activity"]=="rd" and h.payload["person"]==p["person"] and h.payload["day"].startswith(p["month"]))
                if rd==total:add("fulltime-"+str(e.id),"提示",p["person"]+" 全月工时均登记为研发，请核对实际考勤")
                if rd>0:ratios.setdefault((p["month"],rd/total),[]).append(p["person"])
            if e.kind=="fee" and e.project:
                project=db.get(Project,e.project)
                if e.payload["treatment"]!=project.details["treatment"]:add("treatment-"+str(e.id),"警告",e.key+" 费用化与项目基线处理方式不同，请核实")
        for (month,ratio),people in ratios.items():
            if len(people)>1:add("ratio-"+month+"-"+str(ratio),"提示",month+" 多人研发工时比例相同："+", ".join(people))
    return ok(items)

class PolicyData(Form):
    title:str=Field(min_length=1,max_length=180)
    level:Literal["国家","省","市"]
    reference:str=Field(min_length=1,max_length=100)
    clause:str=Field(min_length=1,max_length=200)
    effective:date
    text:str=Field(min_length=1,max_length=12000)
    version:str=Field(min_length=1,max_length=60)
    link:str=Field(pattern=r"^https://",max_length=1000)

@router.post("/policies")
def policy(form:PolicyData,request:Request,db:DB,u:Actor):
    require(u,"admin");item=Policy(payload=form.model_dump(mode="json"),actor=u.id)
    db.add(item);db.flush();record(db,request,u,"policy.publish",item.id);db.commit();return ok(object_info(item))

@router.get("/policies")
def policies(db:DB,u:Actor,q:str="",as_of:date|None=None):
    return ok([object_info(i) for i in db.scalars(select(Policy).order_by(Policy.id.desc()))
               if q in " ".join(i.payload.values()) and (not as_of or i.payload["effective"]<=as_of.isoformat())])
class Settlement(WorkBase):
    project:int
    indicators:str=Field(min_length=1,max_length=3000)
    results:str=Field(min_length=1,max_length=3000)
    experts:str=Field(min_length=1,max_length=500)
    conclusion:Literal["验收通过","失败终止"]
    reason:str=Field(default="",max_length=1500)
    amount:Decimal=Field(ge=0,max_digits=18,decimal_places=2)
    evidence:int
    reconciliation:str=Field(min_length=1,max_length=1500)

def settled_cost(db,pid):
    result=Decimal(0)
    for e,status in db.execute(select(Entry,Task.status).join(Task,Task.id==Entry.task).where(Entry.project==pid,Entry.kind=="fee")):
        if status not in {"customer","complete","archived"}:fail(409,"项目有未完成内审的费用，请先完成财务复核")
        if e.payload["type"] not in {"特殊收入","产品材料冲减","试运行销售","不征税补助"}:
            result+=Decimal(e.payload["amount"])
    return result

@router.post("/settlements")
def settle(form:Settlement,request:Request,db:DB,u:Actor):
    t,p=working(db,u,form)
    if t.kind!="结题":fail(422,"请在结题任务中登记")
    linked_file(db,t,p.id,form.evidence)
    if form.conclusion=="失败终止" and not form.reason:fail(422,"失败项目请说明原因")
    if form.amount!=settled_cost(db,p.id):fail(422,"决算金额与已审核凭证账面合计不一致")
    key=str(p.id)
    e=db.scalar(select(Entry).where(Entry.task==t.id,Entry.kind=="settlement",Entry.key==key))
    if e:e.payload=form.model_dump(mode="json");t.revision+=1
    else:
        form.key=key;e=save(db,u,t,"settlement",form,p.id)
    return saved(db,request,u,e)

def check_settlement(db,t):
    rows=list(db.scalars(select(Entry).where(Entry.task==t.id,Entry.kind=="settlement")))
    if not rows:fail(409,"请先登记项目验收指标、关联证明及经费决算")
    for e in rows:
        if Decimal(e.payload["amount"])!=settled_cost(db,e.project):fail(409,"已审核费用有变化，请重新核对决算")
class Team(Form):
    assistants:list[int]=Field(max_length=32)
    revision:int
    reason:str=Field(min_length=1,max_length=300)

@router.post("/tasks/{tid}/team")
def team(tid:int,form:Team,request:Request,db:DB,u:Actor):
    from sqlalchemy import delete
    from .workflow import checked_revision,event
    from .auth import roles
    from .db import Member
    t=visible_task(db,u,tid,True);require(u,"manager","director","leader");checked_revision(t,form.revision)
    if t.status not in {"assigned","working","revision","suspended","unassigned"}:fail(409,"该任务正在审批或已经交付")
    before=list(db.scalars(select(Member.user).where(Member.task==tid)))
    after=set(form.assistants)
    for uid in after:
        person=db.get(User,uid)
        if uid in {t.owner,t.dispatcher,u.id} or not person or not person.enabled or not roles(person)&{"staff","leader"}:fail(422,"协办岗位无效")
        if roles(u)=={"leader"} and (person.department!=u.department or person.team!=u.team):fail(403,"主管只能调整本团队成员")
    db.execute(delete(Member).where(Member.task==tid))
    db.add_all(Member(task=tid,user=uid) for uid in after)
    t.revision+=1;event(db,t,u,"team",form.reason,{"before":before,"after":sorted(after)})
    record(db,request,u,"team.change",tid);db.commit();return ok()
@router.get("/customers/{cid}/service-file.xlsx")
def client_file(cid:int,request:Request,db:DB,u:Actor):
    from .workflow import overview
    r=overview(cid,db,u)["data"]
    sheets=[("客户资料",[["名称","信用代码","分级","行业"],[r["customer"]["name"],r["customer"]["code"],r["customer"]["details"].get("level"),r["customer"]["details"].get("industry")]])]
    for title,key,columns in [("合同","contracts",["code","name","amount","status"]),("订单","orders",["code","name"]),("任务","tasks",["title","kind","status","deadline"]),("项目","projects",["code","name","budget"])]:
        sheets.append((title,[[{"code":"编号","name":"名称","amount":"金额","status":"状态","title":"标题","kind":"事项","deadline":"期限","budget":"预算"}[k] for k in columns]]+[[i[k] for k in columns] for i in r[key]]))
    rows=[["任务","版本","阶段","日期 UTC","意见"]]
    for task in r["tasks"]:
        for h in db.scalars(select(History).where(History.task==task["id"]).order_by(History.id)):
            rows.append([task["title"],h.version,h.action,h.at,h.note])
    sheets.append(("办理与交付记录",rows))
    record(db,request,u,"customer.export",cid);db.commit()
    return deliver(write_xlsx(sheets),r["customer"]["name"]+"-服务档案.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.get("/notices")
def notices(db:DB,u:Actor):
    from datetime import timedelta
    from .auth import roles
    from .workflow import STATUS
    due=(date.today()+timedelta(days=3)).isoformat()
    items=[]
    for t in db.scalars(select(Task).where(access_tasks(db,u)).order_by(Task.id.desc())):
        h=db.scalar(select(History).where(History.task==t.id).order_by(History.id.desc()).limit(1))
        if not h:continue
        overdue=t.deadline<=due and t.status not in {"archived","complete","suspended"}
        items.append({"id":h.id,"task":t.id,"name":t.title,"state":STATUS[t.status],"action":h.action,"day":h.at,
                      "note":h.note,"due":"已超期" if overdue and t.deadline<str(date.today()) else "临期" if overdue else ""})
    return ok(items)

@router.get("/management/stats")
def statistics(db:DB,u:Actor):
    from collections import defaultdict
    require(u,"leader","manager","director")
    totals=defaultdict(lambda:{"tasks":0,"complete":0,"on_time":0,"late":0})
    for t in db.scalars(select(Task).where(access_tasks(db,u))):
        group=totals[(t.team,t.owner)];group["tasks"]+=1
        if t.status in {"complete","archived"}:
            h=db.scalar(select(History).where(History.task==t.id,History.action=="confirm.pass").order_by(History.id.desc()).limit(1))
            group["complete"]+=1
            if h and h.at.date().isoformat()<=t.deadline:group["on_time"]+=1
        elif t.status!="suspended" and t.deadline<str(date.today()):group["late"]+=1
    return ok([{"team":team,"person":db.get(User,uid).name,**v,"rate":str(round(100*v["on_time"]/v["complete"],1))+"%" if v["complete"] else "—"} for (team,uid),v in totals.items()])
from fastapi import File,Form as UploadField,UploadFile
from sqlalchemy import Integer
from .db import now
from .auth import roles
from .materials import accept_blob,read_blob,drop_blob

class CustomerFile(Base):
    __tablename__="biz_customer_file"
    id=Column(ID,primary_key=True)
    customer=Column(ID,ForeignKey("biz_customer.id"),nullable=False,index=True)
    contract=Column(ID,ForeignKey("biz_contract.id"))
    category=Column(String(64),nullable=False)
    clearance=Column(String(24),nullable=False)
    name=Column(String(160),nullable=False)
    storage=Column(String(160),unique=True,nullable=False)
    digest=Column(String(64),nullable=False)
    size=Column(Integer,nullable=False)
    previous=Column(ID,ForeignKey("biz_customer_file.id"),unique=True)
    actor=Column(ID,ForeignKey("sys_user.id"),nullable=False)

def customer_documents(db,u,cid):
    from .workflow import commercial_scope
    visible_customer(db,u,cid)
    stmt=select(CustomerFile).where(CustomerFile.customer==cid)
    if not roles(u)&{"manager","director"}:stmt=stmt.where(CustomerFile.clearance=="任务可见")
    return stmt.where((CustomerFile.contract==None)|CustomerFile.contract.in_(select(Contract.id).where(commercial_scope(db,u,Contract))))

@router.get("/customers/{cid}/files")
def documents(cid:int,db:DB,u:Actor):
    return ok([{k:v for k,v in object_info(r).items() if k!="storage"} for r in db.scalars(customer_documents(db,u,cid))])

@router.post("/customers/{cid}/files")
def add_document(cid:int,request:Request,db:DB,u:Actor,file:UploadFile=File(...),category:str=UploadField(...,max_length=64),
                 clearance:Literal["管理岗可见","任务可见"]=UploadField("管理岗可见"),contract:int|None=UploadField(None),previous:int|None=UploadField(None)):
    manage_customer(db,u,cid)
    if contract:
        c=db.get(Contract,contract)
        if not c or c.customer!=cid:fail(422,"合同须属于本客户")
    if previous:
        old=db.get(CustomerFile,previous)
        if not old or old.customer!=cid or old.contract!=contract or old.category!=category:fail(422,"原文件不属于该客户及合同")
    name,key,digest,size=accept_blob(file)
    try:
        f=CustomerFile(customer=cid,contract=contract,category=category,clearance=clearance,name=name,storage=key,digest=digest,size=size,previous=previous,actor=u.id)
        db.add(f);db.flush();record(db,request,u,"customer-file.upload",f.id,{"sha256":digest});db.commit();return ok({"id":f.id})
    except Exception:
        drop_blob(key);raise

@router.get("/customers/{cid}/files/{fid}")
def customer_download(cid:int,fid:int,request:Request,db:DB,u:Actor):
    f=db.scalar(customer_documents(db,u,cid).where(CustomerFile.id==fid))
    if not f:fail(404,"资料不存在或不在可见范围")
    data=read_blob(f);record(db,request,u,"customer-file.download",f.id);db.commit()
    return deliver(data,f.name,"application/octet-stream")
