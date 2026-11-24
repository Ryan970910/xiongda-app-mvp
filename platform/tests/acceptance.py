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
    library = "/policies/library"
    template_bytes = b"%PDF-1.4\nshared template\n%%EOF"
    template_upload = {"file": ("填报说明.pdf", template_bytes, "application/pdf")}
    call(None, "GET", library, expected=401)
    call("research", "POST", library, expected=403, files=template_upload)
    call("admin", "POST", library, expected=422, files={"file": ("假文件.docx", b"invalid")})
    saved = call("admin", "POST", library, files=template_upload, data={"description": "年度填报"})
    assert call("research", "GET", library) == [
        {"id": saved["id"], "name": "填报说明.pdf", "description": "年度填报", "size": len(template_bytes)}]
    file_url = f"{library}/{saved['id']}/download"
    call(None, "GET", file_url, expected=401)
    assert call("research", "GET", file_url) == template_bytes
    people={p["name"]:p["id"] for p in call("dispatch","GET","/directory")}
    a=call("admin","POST","/system/users",{"username":"independent","name":"另一位承办","employee_no":"T-10","department":2,"team":"独立组","roles":[{"role":"staff"}],"new_password":pwd})
    login("independent");call("independent","GET","/tasks",expected=403)
    new_pwd="Z9"+secrets.token_urlsafe(16)
    call("independent","PUT","/auth/password",{"old_password":pwd,"new_password":new_pwd});login("independent",new_pwd)
    assert call("independent","GET","/tasks")["total"]==0
    call("independent","GET","/system/users",expected=403)
    assert call("admin","GET","/system/login-logs")
    for role_name in ("review","director"):
        logs=call(role_name,"GET","/system/login-logs")
        assert logs and not any(row["subject"]=="admin" for row in logs)
    call("research","GET","/system/login-logs",expected=403)
    register=load_workbook(io.BytesIO(call("admin","GET","/system/account-register.xlsx")))
    assert "密码" not in str(list(register.active.values)) and register.active.max_row>=11
    call("research","GET","/system/account-register.xlsx",expected=403)
    research=call("research","GET","/tasks")["items"];rid=next(t["id"] for t in research if t["kind"]=="立项")
    fid=call("finance","GET","/tasks")["items"][0]["id"];c=current("dispatch",rid)["customer"]
    meeting={"research_rep":people["科研承办"],"finance_rep":people["财务承办"],"qualifies":"符合","industry_check":"未发现负面清单情形","conclusion":"两线确认温控原型的研发边界"}
    call("dispatch","POST",f"/tasks/{rid}/preconsult",meeting)
    call("research","POST",f"/tasks/{rid}/preconsult",meeting,403)
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
    edit("research",rid,"第二版补足数据",[project]);act("research",rid,"submit")
    state=current("lead",rid)
    call("lead","POST",f"/tasks/{rid}/audit",{"revision":state["revision"],"version":state["version"],"result":"consult","consultant":people["财务主管"],"opinion":"请会核费用边界"})
    item=call("finlead","GET","/consultations/assigned")[0]
    assert item["question"]=="请会核费用边界" and call("lead","GET",f"/tasks/{rid}")["review_clock"]["hours"]==48
    act("lead",rid,"audit",expected=409)
    call("review","POST",f"/consultations/{item['id']}/reply",{"note":"无权代答"},404)
    call("finlead","POST",f"/consultations/{item['id']}/reply",{"note":"会核完成"})
    act("lead",rid,"audit")
    act("dispatch",rid,"audit",expected=403);act("review",rid,"audit")
    pid=call("finance","GET","/projects")["items"][0]["id"]
    writing = f"/projects/{pid}/writing"
    outline = next(t for t in templates if t["category"] == "technical")
    first_field = outline["fields"][0]
    initial = {"template": outline["id"], "title": "项目技术报告", "values": {first_field: "第一天的记录"}}
    desk = call("research", "GET", writing)
    assert desk["can_write"] and not desk["tasks"] and any(d["id"] == doc["id"] for d in desk["documents"])
    call("finance", "POST", writing+"/drafts", initial, 403)
    personal = call("research", "POST", writing+"/drafts", initial)
    draft_url = writing+"/drafts/"+str(personal["id"])
    assert call("research","GET",writing)["drafts"][0]["payload"]["values"][first_field] == "第一天的记录"
    assert not call("finance", "GET", writing)["drafts"]
    call("finance", "GET", draft_url+"/word", expected=404)
    assert "word/document.xml" in zipfile.ZipFile(io.BytesIO(call("research","GET",draft_url+"/word"))).namelist()
    call("research","PUT",draft_url,{**initial,"revision":999},409)
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
    delivery=load_workbook(io.BytesIO(call("dispatch","GET",f"/tasks/{rid}/delivery.xlsx")))
    assert any(r[2]=="测试决议" for r in list(delivery.active.values)[1:])
    act("dispatch",rid,"confirm");act("admin",rid,"archive")
    archive=zipfile.ZipFile(io.BytesIO(call("admin","GET",f"/tasks/{rid}/archive.zip")))
    assert "交付清单.xlsx" in archive.namelist()
    packet=zipfile.ZipFile(io.BytesIO(call("dispatch","GET",f"/projects/{pid}/evidence.zip")))
    assert "项目证据链.xlsx" in packet.namelist() and any(n.endswith(".docx") for n in packet.namelist())
    manifest=json.loads(archive.read("manifest.json"));assert [h["snapshot"]["draft"]["summary"] for h in manifest["history"] if h["action"]=="submit"]==["第一次提交","第二版补足数据"]
    issue=call("finance","POST","/issues",{"task":fid,"project":pid,"question":"补充工资依据"})
    assert issue["payload"]["due"]==str(date.today()+timedelta(days=3))
    act("finance",fid,"submit",expected=409)
    call("research","POST",f"/issues/{issue['id']}/reply",{"note":"已提供"});call("finance","POST",f"/issues/{issue['id']}/close",{"note":"已核对"})
    add=lambda path,**values:call("finance","POST",path,{"task":fid,"key":secrets.token_hex(5),**values})
    a=add("/attendance",person="小周",month=day.strftime("%Y-%m"),hours="8",salary="720",insurance="80",voucher="工01")
    call("finance","POST","/attendance",{"task":fid,"key":"badhrs","person":"反例","month":day.strftime("%Y-%m"),"hours":8,"scheduled_hours":7,"salary":720,"insurance":80,"voucher":"工02"},422)
    call("finance","POST","/attendance",{"task":fid,"key":"badins","person":"反例","month":day.strftime("%Y-%m"),"hours":8,"pension":20,"salary":720,"insurance":80,"voucher":"工03"},422)
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
    def csv_import(kind,contents,status=200):
        res=client.post("/api/v1/imports/"+kind,data={"task":fid},files={"file":("example.csv",contents.encode("utf-8-sig"))},headers=headers["finance"])
        assert res.status_code==status,(res.status_code,res.text[:200])
    head="单号,项目编号,试制单号,物料名称,批次,单位,数量,单价,可用库存,日期\n"
    row=f"PK-TEST,RD-01,{trial['key']},试纸,T,张,4,0,4,{day}\n"
    csv_import("picks",head+row+row,422);csv_import("picks",head+row)
    head="单号,原领料单号,数量,去向,收发位置,日期\n"
    csv_import("flows",head+"".join(f"F-{i},PK-TEST,1,{dest},科研室,{day}\n" for i,dest in enumerate(["流转","消耗","样品","处置","退料"])))
    assert any(Decimal(r["balance"])==0 and len(r["movements"])==5 for r in call("finance","GET","/material-ledger"))
    act("finance",fid,"submit",expected=409)
    for n in ("research","finance"):call(n,"POST",f"/tasks/{fid}/joint-sign",{"note":"凭证、工时与项目核对一致"})
    act("finance",fid,"submit");act("finlead",fid,"audit");act("finreview",fid,"audit")
    for edition in ["2015","2021"]:
        r=call("dispatch","POST","/subsidiary/generate",{"year":year,"customer":c,"edition":edition})
        assert Decimal(r["projects"][0]["deduction"])==600
        wb=load_workbook(io.BytesIO(call("dispatch","GET",f"/subsidiary?year={year}&customer={c}&edition={edition}")))
        assert len(wb.sheetnames)>=3
        for view,title in [("account","会计口径"),("hightech","高企口径"),("deduction","加计归集口径"),("differences","三口径差异调节")]:
            single=load_workbook(io.BytesIO(call("dispatch","GET",f"/subsidiary?year={year}&customer={c}&edition={edition}&snapshot={r['snapshot_id']}&view={view}")))
            assert single.sheetnames==[title] and single.active["C2"].value==600
        frozen=call("dispatch","GET",f"/subsidiary?year={year}&customer={c}&edition={edition}&snapshot={r['snapshot_id']}&filing=true")
        assert load_workbook(io.BytesIO(frozen))["A107012行次核对"]["C52"].value==600
    order=current("dispatch",fid)["order_id"]
    def newtask(kind,title):
        return call("dispatch","POST","/tasks",{"order_id":order,"owner":people["科研承办"],"assistants":[people["财务承办"]],"kind":kind,"line":"research","deadline":str(day+timedelta(days=5)),"title":title,"brief":"联办"})
    close=newtask("结题","联签验收")["id"];act("research",close,"accept");edit("research",close,"结题")
    def move_draft(target, rev, expected=200):
        return call("research","POST",draft_url+"/transfer",{"task":target,"revision":rev},expected)
    move_draft(fid, personal["revision"], 422)
    move_draft(close, personal["revision"], 422)
    assert call("research","GET",writing)["drafts"][0]["id"] == personal["id"]
    filled = {f:"科研记录 "+f for f in outline["fields"]}
    personal = call("research","PUT",draft_url,{**initial,"values":filled,"revision":personal["revision"]})
    transferred = move_draft(close, personal["revision"])
    assert transferred["project"] == pid and transferred["payload"]["values"] == filled
    desk = call("research","GET",writing)
    assert not desk["drafts"] and any(d["id"]==transferred["id"] for d in desk["documents"])
    move_draft(close, personal["revision"], 404)
    upload=client.post("/api/v1/materials/upload",data={"task":close,"project":pid,"category":"验收证据"},files={"file":("验收.docx",word)},headers=headers["research"]).json()["data"]
    evidence={"task":close,"project":pid,"file_id":upload["id"],"stage":"结题报告"}
    call("research","POST","/materials/link",{**evidence,"fee_id":999999},422)
    call("research","POST","/materials/link",evidence)
    assert call("research","GET",f"/tasks/{close}")["evidence_check"]["percent"]==100
    call("research","POST","/settlements",{"task":close,"project":pid,"key":"close","amount":"600","evidence":upload["id"],"indicators":"温差","results":"达到目标","experts":"验收组","conclusion":"验收通过","reconciliation":"已对凭证"})
    for n in ("research","finance"):call(n,"POST",f"/tasks/{close}/joint-sign",{"note":"指标核对"})
    edit("research",close,"结题更新");act("research",close,"submit",expected=409)
    for n in ("research","finance"):call(n,"POST",f"/tasks/{close}/joint-sign",{"note":"复核更新"})
    act("research",close,"submit")
    adjust=newtask("调整","负责人调整")["id"];act("research",adjust,"accept");edit("research",adjust,"负责人调整")
    call("research","POST","/adjustments",{"task":adjust,"key":"BG1","project":pid,"after":{**project,"leader":"陈工"},"reason":"接替","impact":"预算不变"})
    act("research",adjust,"submit");act("lead",adjust,"audit");act("review",adjust,"audit")
    assert call("finance","GET","/projects")["items"][0]["details"]["leader"]=="陈工"
    major=call("dispatch","POST","/tasks",{"order_id":order,"owner":people["科研承办"],"kind":"跟进","line":"research","deadline":str(day+timedelta(days=4)),"title":"套打与重大事项","brief":"逐套核验栏目","major":True})["id"]
    act("research",major,"accept");act("research",major,"suspend");act("research",major,"resume");edit("research",major,"重大事项验证")
    from docx import Document
    for template in templates:
        fields={f:"虚构："+f for f in template["fields"]}
        draft=call("research","POST","/documents",{"task":major,"template":template["id"],"title":template["name"],"values":fields})
        draft=call("research","PUT",f"/documents/{draft['id']}",{"revision":draft["revision"],"task":major,"template":template["id"],"title":"复核"+template["name"],"values":fields})
        docx=Document(io.BytesIO(call("research","GET",f"/documents/{draft['id']}/word")))
        assert all(f in "\n".join(p.text for p in docx.paragraphs) for f in fields)
        assert abs(docx.sections[0].page_width.cm-21)<0.01
    for attempt in range(2):
        act("research",major,"submit");act("lead",major,"audit");act("review",major,"audit");act("director",major,"audit")
        act("dispatch",major,"confirm","return" if attempt==0 else "pass")
    act("admin",major,"archive");act("research",major,"suspend",expected=409)
    other=newtask("立项","第二研发项目")["id"];act("research",other,"accept");edit("research",other,"分摊项目",[{**project,"code":"RD-02"}])
    act("research",other,"submit");act("lead",other,"audit");act("review",other,"audit")
    second=next(p["id"] for p in call("finance","GET","/projects")["items"] if p["code"]=="RD-02")
    f2=call("dispatch","POST","/tasks",{"order_id":order,"owner":people["财务承办"],"kind":"费用归集","line":"finance","deadline":str(day),"assistants":[people["科研承办"]],"brief":"复算共用材料","title":"跨项目共料"})["id"]
    act("finance",f2,"accept");edit("finance",f2,"分摊")
    item=call("finance","POST","/trials",{"task":f2,"project":pid,"key":"TR2","purpose":"试作","plan":"打样","demand":"铜片","output":"样片"})
    call("finlead","POST","/trials/audit",{"id":item["id"]})
    pick2=call("finance","POST","/picks",{"task":f2,"project":pid,"trial":item["id"],"key":"PK2","material":"铜片","batch":"B","unit":"个","qty":1,"stock":1,"price":"10.01","day":str(day)})
    flow={"task":f2,"key":"C1","pick":pick2["id"],"qty":1,"destination":"consume","day":str(day),"location":"试验室","shares":[{"project":pid,"weight":1},{"project":second,"weight":2}]}
    call("finance","POST","/flows",flow,422)
    result=call("finance","POST","/flows",{**flow,"basis":"实测消耗比例 1 比 2"})
    assert result["payload"]["allocations"]=={str(pid):"3.34",str(second):"6.67"}
    rule={"code":"material-limit","name":"单笔金额需复核","condition":"单笔费用超过阈值","threshold":"3","applies":"finance","severity":"阻断","reference":"虚构验收规则","effective":str(day),"reason":"验证阻断"}
    call("admin","POST","/system/risk-rules",rule)
    assert any("单笔金额需复核" in r["description"] for r in call("finance","GET","/risks"))
    act("finance",f2,"submit",expected=409)
    call("admin","POST","/system/risk-rules",{**rule,"enabled":False,"reason":"规则测试结束"})
    assert not any("单笔金额需复核" in r["description"] for r in call("finance","GET","/risks"))
    act("lead",close,"audit",expected=409);act("lead",close,"audit","return","基线已调整，请复核")
    act("research",close,"submit",expected=409)
    for name in ("research","finance"):call(name,"POST",f"/tasks/{f2}/joint-sign",{"note":"费用核对"})
    act("finance",f2,"submit");act("finlead",f2,"audit");act("finreview",f2,"audit")
    call("research","POST","/settlements",{"task":close,"project":pid,"key":"close","amount":"603.34","evidence":upload["id"],"indicators":"温差","results":"已达标","experts":"验收组","conclusion":"验收通过","reconciliation":"600元人工加3.34元材料"})
    for name in ("research","finance"):call(name,"POST",f"/tasks/{close}/joint-sign",{"note":"对新基线复核"})
    act("research",close,"submit");act("lead",close,"audit");act("review",close,"audit");act("dispatch",close,"confirm");act("admin",close,"archive")
    assert next(p for p in call("research","GET","/projects")["items"] if p["id"]==pid)["details"]["closed"]["task"]==close
    store=call("admin","POST","/system/template-versions",{"code":"sample-note","category":"work","name":"试办记录","scenario":"试用","columns":"项目\n过程","reason":"联合验收"})
    assert any(x["id"]=="sample-note" for x in call("research","GET","/templates"))
    invalid={"amount":"300000","kinds":["专项申报","高企认定"],"reason":"测试条件"}
    call("admin","POST","/system/routing-rules",invalid)
    assert call("review","GET","/system/routing-rules")["amount"]=="300000"
    assert call("research","GET","/notices") and call("review","GET","/management/stats")
    assert call("dispatch","GET",f"/customers/{c}/service-file.xlsx").startswith(b"PK")
    # A scoped second post never grants manager access from the primary staff post.
    account=next(p for p in call("admin","GET","/system/users") if p["username"]=="independent")
    base={k:account[k] for k in ("username","name","employee_no","department","team","contact","enabled")}
    call("admin","PUT",f"/system/users/{account['id']}",{**base,"roles":[{"role":"staff"},{"role":"manager","department":3}]})
    login("independent",new_pwd)
    call("independent","GET","/system/login-logs",expected=403)
    call("independent","POST","/auth/post",{"department":1},403)
    switched=call("independent","POST","/auth/post",{"department":3})
    assert switched["roles"]==["manager"] and switched["department"]==3 and 2 in switched["posts"]
    call("independent","GET","/system/login-logs")
    call("independent","POST","/auth/post",{"department":2})
    # Test the cloud-independent recovery procedure on a copy with real archived attachments.
    from backup_trial import backup
    import sqlite3
    with tempfile.TemporaryDirectory(dir=os.environ["TMP"]) as destination:
        restored=Path(destination)/"restored"
        backup(Path(tmp.name),restored)
        conn=sqlite3.connect(restored/"workspace.db")
        try:
            assert conn.execute("select count(*) from sys_session").fetchone()[0]==0
            assert conn.execute("select status from wf_task where id=?",(rid,)).fetchone()[0]=="archived"
            assert list((restored/"objects").iterdir())
            template_key = conn.execute("select storage from policy_template_file where id=?", (saved["id"],)).fetchone()[0]
            assert (restored/"objects"/template_key).read_bytes() == template_bytes
        finally:conn.close()
    os.environ["OFFICE_MODE"]="1"
    try:
        call(None,"POST","/auth/login",{"username":"research","password":pwd},401)
        call("research","GET","/tasks",expected=403)
        login("independent",new_pwd)
        assert not call("independent","GET","/tasks")["items"]
    finally:os.environ.pop("OFFICE_MODE")
    assert sum(distribute(Decimal("1"),{1:1,2:1,3:1}).values())==1
    print(f"PASS scoped roles, consultation, delivery and recovery, {len(templates)} DOCX templates, major review, returns, inventory import, evidence mapping, payroll and four independent exports",flush=True)

if __name__=="__main__":
    try:
        with TestClient(app,client=("127.0.0.1",50001)) as client:run(client)
    finally:
        engine.dispose();tmp.cleanup()
