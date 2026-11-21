"""Transactional, validated business imports. Row numbers refer to the user's sheet."""
import csv
import io
import zipfile
from datetime import date,datetime
from typing import Literal

from fastapi import APIRouter,File,Form as Body,Request,UploadFile,HTTPException
from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy import select

from .auth import Actor,DB,fail,ok,record
from .db import Entry
from .finance import Attendance,Fee,Hours,amounts,business_task,save,write_xlsx
from .materials import deliver,project_for

router=APIRouter()
MODELS={"fees":("fee",Fee),"attendance":("attendance",Attendance),"hours":("hours",Hours)}
LABELS={"key":"单号","project":"项目编号","day":"日期","voucher":"凭证号","subject":"科目","category":"费用类别","amount":"金额","treatment":"会计处理","note":"摘要","type":"特殊事项","basis":"分摊依据","positive":"符合加计","hightech":"符合高企","person":"人员","month":"月份","hours":"工时","salary":"工资","insurance":"五险一金","external":"外聘劳务","agreement":"外聘协议索引","direct":"直接研发人员","tech":"科技人员","activity":"活动类型","tax_line":"申报明细行"}
REVERSE={v:k for k,v in LABELS.items()}

@router.get("/imports/{kind}/template")
def template(kind:Literal["fees","attendance","hours"],u:Actor):
    _,model=MODELS[kind]
    headers=[LABELS.get(k,k) for k in model.model_fields if k!="task"]
    return deliver(write_xlsx([("导入", [headers]),("填写说明",[["栏目","说明"],["项目编号","填写内部审核通过的项目编号"],["活动类型","rd 或 nonrd"],["日期","YYYY-MM-DD"],["布尔值","是或否"],["单号","每行唯一；重复单号整批退回"]])]),
        kind+"-导入模板.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.post("/imports/{kind}")
def ingest(kind:Literal["fees","attendance","hours"],request:Request,db:DB,u:Actor,task:int=Body(...),file:UploadFile=File(...)):
    t=business_task(db,u,task)
    if t.line!="finance":fail(422,"请从财务任务导入")
    data=file.file.read(8*1024*1024+1)
    if len(data)>8*1024*1024:fail(422,"单次导入最多8MB")
    try:
        if (file.filename or "").lower().endswith(".csv"):
            rows=csv.reader(io.StringIO(data.decode("utf-8-sig")))
        else:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if sum(f.file_size for f in z.infolist())>50*1024*1024:fail(422,"工作簿解压体积超过限制")
            wb=load_workbook(io.BytesIO(data),read_only=True,data_only=False)
            rows=wb.worksheets[0].values
        header=[REVERSE.get(str(x).strip(),str(x).strip()) for x in next(iter(rows))]
    except HTTPException:raise
    except Exception:fail(422,"请使用模板工作簿或 UTF-8 CSV 文件")
    entry_kind,model=MODELS[kind]
    if len(set(header))!=len(header) or any(k not in model.model_fields or k=="task" for k in header):fail(422,"表头重复或包含未知栏目")
    from .db import Project
    projects={p.code:p for p in db.scalars(select(Project).where(Project.order_id==t.order_id))}
    existing=list(db.scalars(select(Entry).where(Entry.task==task,Entry.kind==entry_kind)))
    keys={e.key for e in existing};daily={}
    if kind=="hours":
        for e in existing:
            if e.state!="returned":
                k=(e.payload["person"],e.payload["day"]);daily[k]=daily.get(k,0)+amounts(e,"hours")
    added=0;errors=[]
    for num,values in enumerate(rows,2):
        if num>10001:fail(422,"一次最多导入一万行")
        if not any(v not in (None,"") for v in values):continue
        try:
            raw={k:(v.isoformat()[:10] if isinstance(v,(date,datetime)) else v) for k,v in zip(header,values) if v not in (None,"")}
            for k,v in list(raw.items()):
                if v in ("是","否"):raw[k]=v=="是"
            p=projects.get(str(raw["project"])) if raw.get("project") else None
            if raw.get("project") and not p:raise ValueError("项目编号未出现在该订单已审核项目中")
            if p:raw["project"]=p.id
            f=model.model_validate({"task":task,**raw})
            if kind=="attendance":
                f.key=f.month+"/"+f.person
                if f.external and not f.agreement:raise ValueError("外聘工资需填协议索引")
            if f.key in keys:raise ValueError("单号或人员月份重复")
            if kind=="hours":
                if p and not p.details["start"]<=f.day.isoformat()<=p.details["end"]:raise ValueError("工时超出项目周期")
                k=(f.person,f.day.isoformat());daily[k]=daily.get(k,0)+f.hours
                if daily[k]>24:raise ValueError("当日累计工时超过24")
            keys.add(f.key)
            db.add(Entry(task=t.id,project=p.id if p else None,key=f.key,kind=entry_kind,state="posted" if kind=="fees" else "draft",payload=f.model_dump(mode="json"),actor=u.id))
            added+=1
        except (ValidationError,ValueError) as exc:
            msg="；".join(".".join(map(str,e["loc"]))+" "+e["msg"] for e in exc.errors()) if isinstance(exc,ValidationError) else str(exc)
            errors.append(f"第{num}行：{msg}")
            if len(errors)>=20:break
    if errors:db.rollback();fail(422,"整批未保存。"+"；".join(errors))
    if not added:fail(422,"表中没有数据行")
    t.revision+=1;record(db,request,u,"import."+kind,task,{"rows":added});db.commit()
    return ok({"count":added})
