"""First run of the loopback-only acceptance edition."""
import os
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import select

from .auth import DB, Form, fail, ok, set_password, record
from .db import Contract, Customer, Department, History, Order, Task, User

router=APIRouter()
ACCOUNTS=[
    ("dispatch","派单经理","research","manager"),("research","科研承办","research","staff"),
    ("lead","科研主管","research","leader"),("review","科研复审经理","research","manager"),
    ("director","科研总监","research","director"),("finance","财务承办","finance","staff"),
    ("finlead","财务主管","finance","leader"),("finreview","财务复审经理","finance","manager"),
    ("findirector","财务总监","finance","director"),("admin","系统管理员","function","admin")]

class Setup(Form):
    ticket:str=Field(max_length=160)
    password:str=Field(min_length=8,max_length=128)

@router.get("/local/status")
def status(db:DB):
    shared=os.getenv("RD_SHARED_TRIAL")=="1"
    local=bool(os.getenv("ACCEPTANCE_TICKET")) and not shared
    return ok({"setup":local and not db.scalar(select(User.id).limit(1)),
               "shared":shared,
               "accounts":[{"username":n,"name":label} for n,label,_,_ in ACCOUNTS] if local else []})

@router.post("/local/setup")
def setup(form:Setup,request:Request,db:DB):
    ticket=os.getenv("ACCEPTANCE_TICKET","")
    if os.getenv("RD_SHARED_TRIAL")=="1" or not ticket or not secrets.compare_digest(ticket,form.ticket) or request.client.host not in {"127.0.0.1","::1"}:fail(403,"请从本机启动窗口打开首次设置链接")
    if db.scalar(select(User.id).limit(1)):fail(409,"此工作台已完成初始化")
    people=seed_example(db,{name:form.password for name,_,_,_ in ACCOUNTS},shared=False)
    record(db,request,people["dispatch"],"local.initialize","fictional-workspace")
    db.commit();return ok()

def seed_example(db,passwords,*,shared):
    deps={d.line:d for d in db.scalars(select(Department))};people={}
    prefix="TRIAL-" if shared else "LOCAL-"
    for n,label,line,role in ACCOUNTS:
        u=User(username=n,employee_no=prefix+n,name=label,department=deps[line].id,team="验收一组",
               roles=[{"role":role,"expires":None}],enabled=True)
        set_password(u,passwords[n],shared);db.add(u);people[n]=u
    db.flush()
    manager=people["dispatch"];today=date.today();end=today+timedelta(days=90)
    c=Customer(name="青禾试验科技（虚构）",code="DEMO00000000000001",department=manager.department,manager=manager.id,details={"level":"一般","industry":"制造业"})
    db.add(c);db.flush()
    ct=Contract(code="HT-LOCAL-001",name="青禾研发服务试办合同",customer=c.id,amount=20000,status="approved",
        details={"start":str(today),"end":str(end),"scope":"研发立项与费用归集","payment_terms":"验收后收款"})
    db.add(ct);db.flush()
    o=Order(code="DD-LOCAL-001",name="青禾温控试验",customer=c.id,contract=ct.id,
        details={"start":str(today),"end":str(end),"service":"研发咨询","standards":"完成项目清单及费用底稿","line":"research","priority":"normal"})
    db.add(o);db.flush()
    from .db import Member
    for n,line,kind,title in [("research","research","立项","青禾温控试验 · 确认立项清单"),("finance","finance","费用归集","青禾温控试验 · 归集本期费用")]:
        owner=people[n]
        t=Task(order_id=o.id,customer=c.id,title=title,line=line,kind=kind,owner=owner.id,dispatcher=manager.id,
            department=owner.department,team=owner.team,deadline=str(end),brief="请根据虚构试验资料办理，并保留审核意见。")
        db.add(t);db.flush()
        db.add(History(task=t.id,actor=manager.id,action="assign",version=0,note="虚构验收案例派单"))
        if line=="finance":db.add(Member(task=t.id,user=people["research"].id))
    from .operations import Policy
    for title,reference,clause,when,text,url in [
        ("年度其他费用限额","税务总局公告2021年第28号","第三条","2021-01-01","年度内统算其他相关费用的允许金额，资本化项目在形成无形资产年度参与计算。","https://www.chinatax.gov.cn/chinatax/n810351/n810906/c5169537/content.html"),
        ("委托境外研发","财税〔2018〕64号","第一条","2018-01-01","境外机构委托研发按实际费用的八成计入，并适用境内符合条件研发费用三分之二的限额。","https://fgk.chinatax.gov.cn/zcfgk/c102416/c5202434/content.html"),
        ("研发费用纳税申报核对","税务总局公告2025年第1号","A107012","2025-01-01","年度复核时检查费用化与资本化、无形资产摊销、收入抵减及产品材料跨年度结转。","https://12366.chinatax.gov.cn/bzds/037/037.html")]:
        db.add(Policy(actor=people["admin"].id,payload={"title":title,"reference":reference,"clause":clause,"effective":when,"text":text,"link":url,"level":"国家","version":"内置验收参考"}))
    return people
