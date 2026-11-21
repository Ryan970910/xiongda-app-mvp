"""Exercise the normal HTTP contracts against a fresh private test database."""
import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import zipfile
from datetime import date, timedelta

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
tmp=tempfile.TemporaryDirectory(prefix="rd-acceptance-",dir=os.environ.get("TMP") or root)
os.environ["WORKSPACE_DATA"]=tmp.name
os.environ["ACCEPTANCE_TICKET"]=secrets.token_hex(40)
for name in ("DATABASE_URL","S3_BUCKET","OFFICE_MODE"):os.environ.pop(name,None)
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from service.main import app
from service.db import engine
from service.local import ACCOUNTS
from service.finance import distribute
from decimal import Decimal

def run(client):
    headers={}
    pwd="Test9"+secrets.token_urlsafe(16)
    def call(role,method,path,body=None,expected=200,**kwargs):
        res=client.request(method,"/api/v1"+path,json=body,headers=headers.get(role,{}),**kwargs)
        assert res.status_code==expected,(method,path,res.status_code,res.text[:300])
        if "application/json" in res.headers.get("content-type",""):return res.json()["data"]
        return res.content
    def login(n,password=pwd):
        s=call(None,"POST","/auth/login",{"username":n,"password":password})
        headers[n]={"Authorization":"Bearer "+s["access_token"]};return s
    def current(n,tid):return call(n,"GET",f"/tasks/{tid}")["task"]
    def act(n,tid,action,result="pass",opinion="本机测试已核对",expected=200):
        t=current(n,tid)
        return call(n,"POST",f"/tasks/{tid}/{action}",{"revision":t["revision"],"version":t["version"],"result":result,"opinion":opinion},expected)
    def edit(n,tid,summary,projects=[]):
        return call(n,"PUT",f"/tasks/{tid}/draft",{"revision":current(n,tid)["revision"],"summary":summary,"projects":projects})
    assert call(None,"GET","/local/status")["setup"]
    call(None,"POST","/local/setup",{"ticket":os.environ["ACCEPTANCE_TICKET"],"password":pwd})
    for n,_,_,_ in ACCOUNTS:login(n)
    people={p["name"]:p["id"] for p in call("dispatch","GET","/directory")}
    a=call("admin","POST","/system/users",{"username":"independent","name":"另一位承办","employee_no":"T-10","department":2,"team":"独立组","roles":[{"role":"staff"}],"new_password":pwd})
    login("independent");call("independent","GET","/tasks",expected=403)
    new_pwd="Z9"+secrets.token_urlsafe(16)
    call("independent","PUT","/auth/password",{"old_password":pwd,"new_password":new_pwd});login("independent",new_pwd)
    assert call("independent","GET","/tasks")["total"]==0
    call("independent","GET","/system/users",expected=403)
    assert call("admin","GET","/system/login-logs")
    research=call("research","GET","/tasks")["items"];rid=next(t["id"] for t in research if t["kind"]=="立项")
    fid=call("finance","GET","/tasks")["items"][0]["id"];c=current("dispatch",rid)["customer"]
    act("research",rid,"accept");act("finance",fid,"accept");edit("finance",fid,"本期由工资与材料组成")
    act("finance",fid,"submit",expected=409)
    day=date.today();year=day.year
    project={"code":"RD-01","name":"温控研发","leader":"李工","budget":"10000","start":str(date(year,1,1)),"end":str(date(year,12,31)),"objective":"温控","innovation":"温差反馈","uncertainty":"稳定性"}
    edit("research",rid,"第一次提交",[project])
    templates=call("research","GET","/templates");assert len(templates)>=55
    t=templates[0];doc=call("research","POST","/documents",{"task":rid,"template":t["id"],"title":"测试决议","values":{f:"测试文本" for f in t["fields"]}})
    word=call("research","GET",f"/documents/{doc['id']}/word");assert "word/document.xml" in zipfile.ZipFile(io.BytesIO(word)).namelist()
    blob=client.post("/api/v1/materials/upload",data={"task":rid,"category":"立项决议"},files={"file":("决议.docx",word)},headers=headers["research"])
    assert blob.status_code==200,blob.text
    act("research",rid,"submit");act("lead",rid,"audit","return","补充试验数据")
    edit("research",rid,"第二版补足数据",[project]);act("research",rid,"submit");act("lead",rid,"audit")
    act("dispatch",rid,"audit",expected=403);act("review",rid,"audit")
    pid=call("finance","GET","/projects")["items"][0]["id"]
    from openpyxl import Workbook
    book=Workbook();ws=book.active;ws.append(["单号","项目编号","日期","凭证号","科目","费用类别","金额","摘要","申报明细行"])
    ws.append(["B1","RD-01",str(day),"材0","材料","直接投入",0,"进口样本",8])
    ws.append(["B2","未建项目",str(day),"材1","材料","直接投入",1,"故意用错项目",8])
    def upload_workbook():
        output=io.BytesIO();book.save(output)
        return client.post("/api/v1/imports/fees",data={"task":fid},files={"file":("费用.xlsx",output.getvalue())},headers=headers["finance"])
    assert upload_workbook().status_code==422
    assert not call("finance","GET","/fee-collections")
    ws.delete_rows(3);assert upload_workbook().status_code==200
    assert upload_workbook().status_code==422
    act("dispatch",rid,"confirm");act("admin",rid,"archive")
    archive=zipfile.ZipFile(io.BytesIO(call("admin","GET",f"/tasks/{rid}/archive.zip")))
    manifest=json.loads(archive.read("manifest.json"));assert [h["snapshot"]["draft"]["summary"] for h in manifest["history"] if h["action"]=="submit"]==["第一次提交","第二版补足数据"]
    issue=call("finance","POST","/issues",{"task":fid,"project":pid,"question":"补充工资依据"})
    act("finance",fid,"submit",expected=409)
    call("research","POST",f"/issues/{issue['id']}/reply",{"note":"已提供"});call("finance","POST",f"/issues/{issue['id']}/close",{"note":"已核对"})
    add=lambda path,**values:call("finance","POST",path,{"task":fid,"key":secrets.token_hex(5),**values})
    a=add("/attendance",person="小周",month=day.strftime("%Y-%m"),hours="8",salary="720",insurance="80",voucher="工01")
    for activity,p,hours in [("rd",pid,"6"),("nonrd",None,"2")]:
        h=add("/workhours",person="小周",project=p,day=str(day),hours=hours,activity=activity)
        call("finlead","POST","/workhours/audit",{"id":h["id"]})
    alloc=call("finance","POST","/attendance/allocate",{"task":fid,"attendance":a["id"]})
    assert Decimal(alloc["allocations"][str(pid)])==600 and Decimal(alloc["allocations"]["非研发"])==200
    trial=add("/trials",project=pid,purpose="试作",plan="试制",demand="铜片",output="样机")
    call("finlead","POST","/trials/audit",{"id":trial["id"]})
    pick=add("/picks",project=pid,trial=trial["id"],material="铜片",batch="A1",unit="片",qty="5",stock="10",price="6",day=str(day))
    add("/flows",pick=pick["id"],qty="2",destination="return",location="仓库",day=str(day))
    assert Decimal(call("finance","GET","/material-ledger")[0]["balance"])==3
    act("finance",fid,"submit",expected=409)
    for n in ("research","finance"):call(n,"POST",f"/tasks/{fid}/joint-sign",{"note":"凭证、工时与项目核对一致"})
    act("finance",fid,"submit");act("finlead",fid,"audit");act("finreview",fid,"audit")
    for edition in ["2015","2021"]:
        r=call("dispatch","POST","/subsidiary/generate",{"year":year,"customer":c,"edition":edition})
        assert Decimal(r["projects"][0]["deduction"])==600
        wb=load_workbook(io.BytesIO(call("dispatch","GET",f"/subsidiary?year={year}&customer={c}&edition={edition}")))
        assert len(wb.sheetnames)>=3
        frozen=call("dispatch","GET",f"/subsidiary?year={year}&customer={c}&edition={edition}&snapshot={r['snapshot_id']}&filing=true")
        assert load_workbook(io.BytesIO(frozen))["A107012行次核对"]["C52"].value==600
    order=current("dispatch",fid)["order_id"]
    def newtask(kind,title):
        return call("dispatch","POST","/tasks",{"order_id":order,"owner":people["科研承办"],"assistants":[people["财务承办"]],"kind":kind,"line":"research","deadline":str(day+timedelta(days=5)),"title":title,"brief":"联办"})
    close=newtask("结题","联签验收")["id"];act("research",close,"accept");edit("research",close,"结题")
    upload=client.post("/api/v1/materials/upload",data={"task":close,"project":pid,"category":"验收证据"},files={"file":("验收.docx",word)},headers=headers["research"]).json()["data"]
    call("research","POST","/settlements",{"task":close,"project":pid,"key":"close","amount":"600","evidence":upload["id"],"indicators":"温差","results":"达到目标","experts":"验收组","conclusion":"验收通过","reconciliation":"已对凭证"})
    for n in ("research","finance"):call(n,"POST",f"/tasks/{close}/joint-sign",{"note":"指标核对"})
    edit("research",close,"结题更新");act("research",close,"submit",expected=409)
    for n in ("research","finance"):call(n,"POST",f"/tasks/{close}/joint-sign",{"note":"复核更新"})
    act("research",close,"submit")
    adjust=newtask("调整","负责人调整")["id"];act("research",adjust,"accept");edit("research",adjust,"负责人调整")
    call("research","POST","/adjustments",{"task":adjust,"key":"BG1","project":pid,"after":{**project,"leader":"陈工"},"reason":"接替","impact":"预算不变"})
    act("research",adjust,"submit");act("lead",adjust,"audit");act("review",adjust,"audit")
    assert call("finance","GET","/projects")["items"][0]["details"]["leader"]=="陈工"
    store=call("admin","POST","/system/template-versions",{"code":"sample-note","category":"work","name":"试办记录","scenario":"试用","columns":"项目\n过程","reason":"联合验收"})
    assert any(x["id"]=="sample-note" for x in call("research","GET","/templates"))
    invalid={"amount":"300000","kinds":["专项申报","高企认定"],"reason":"测试条件"}
    call("admin","POST","/system/routing-rules",invalid)
    assert call("review","GET","/system/routing-rules")["amount"]=="300000"
    assert call("research","GET","/notices") and call("review","GET","/management/stats")
    assert call("dispatch","GET",f"/customers/{c}/service-file.xlsx").startswith(b"PK")
    os.environ["OFFICE_MODE"]="1"
    try:
        call(None,"POST","/auth/login",{"username":"research","password":pwd},401)
        call("research","GET","/tasks",expected=403)
        login("independent",new_pwd)
        assert not call("independent","GET","/tasks")["items"]
    finally:os.environ.pop("OFFICE_MODE")
    assert sum(distribute(Decimal("1"),{1:1,2:1,3:1}).values())==1
    print("PASS accounts, scope, real files, returns, dual line, archive, payroll, inventory, annual workbooks, joint approval, adjustments",flush=True)

if __name__=="__main__":
    try:
        with TestClient(app,client=("127.0.0.1",50001)) as client:run(client)
    finally:
        engine.dispose();tmp.cleanup()
