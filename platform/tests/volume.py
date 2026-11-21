"""Timed, isolated 100-project / 10,000-voucher local workload."""
import csv
import io
import os
from pathlib import Path
import secrets
import sys
import tempfile
from time import perf_counter
from datetime import date

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
tmp=tempfile.TemporaryDirectory(dir=os.environ.get("TMP") or root,prefix="rd-volume-")
os.environ.update(WORKSPACE_DATA=tmp.name,ACCEPTANCE_TICKET=secrets.token_urlsafe())
for key in ("DATABASE_URL","S3_BUCKET","OFFICE_MODE"):os.environ.pop(key,None)
from fastapi.testclient import TestClient
from sqlalchemy import select
from service.main import app
from service.db import Session,Task,Project,engine

def run(c):
    pwd="U9"+secrets.token_hex(14);api="/api/v1"
    assert c.post(api+"/local/setup",json={"ticket":os.environ["ACCEPTANCE_TICKET"],"password":pwd}).status_code==200
    def header(user):
        token=c.post(api+"/auth/login",json={"username":user,"password":pwd}).json()["data"]["access_token"]
        return {"Authorization":"Bearer "+token}
    finance=header("finance");manager=header("dispatch");year=date.today().year
    with Session.begin() as db:
        r=db.scalar(select(Task).where(Task.line=="research"));f=db.scalar(select(Task).where(Task.line=="finance"))
        fid=f.id;cid=f.customer;f.status="working"
        db.add_all(Project(order_id=r.order_id,customer=cid,task=r.id,code=f"P{i}",name=f"试验{i}",budget=50000,details={"category":"自主","treatment":"费用化"}) for i in range(100))
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(["单号","项目编号","日期","凭证号","科目","费用类别","金额","摘要","申报明细行"])
    for i in range(10000):writer.writerow([f"F{i}",f"P{i%100}",f"{year}-01-15",str(i),"研究材料","直接投入","1.01","试制样本",8])
    t=perf_counter();r=c.post(api+"/imports/fees",data={"task":fid},files={"file":("fees.csv",out.getvalue().encode("utf-8-sig"))},headers=finance)
    assert r.status_code==200 and r.json()["data"]["count"]==10000,r.text[:200]
    import_time=perf_counter()-t
    with Session.begin() as db:db.get(Task,fid).status="customer"
    t=perf_counter();r=c.post(api+"/subsidiary/generate",json={"customer":cid,"year":year},headers=manager)
    assert r.status_code==200,r.text[:200]
    v=r.json()["data"];assert len(v["projects"])==100 and float(v["mapping"]["51"])==10100
    gen_time=perf_counter()-t
    t=perf_counter();book=c.get(api+f"/subsidiary?customer={cid}&year={year}&edition=2021&snapshot={v['snapshot_id']}&filing=true",headers=manager)
    assert book.status_code==200 and book.content.startswith(b"PK"),book.text[:100]
    print(f"PASS 10000-row import {import_time:.2f}s, 100-project calculation {gen_time:.2f}s, XLSX export {perf_counter()-t:.2f}s",flush=True)
if __name__=="__main__":
    try:
        with TestClient(app,client=("127.0.0.1",50001)) as client:run(client)
    finally:engine.dispose();tmp.cleanup()
