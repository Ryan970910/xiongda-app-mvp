import hashlib
import io
import json
import os
import secrets
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form as FieldValue, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml.ns import qn
from sqlalchemy import select

from .auth import Actor, DB, Form, fail, ok, record
from .db import DATA, Department, Entry, FileObject, History, Member, Order, Project, Task
from .workflow import (business_snapshot, checked_revision, file_info, object_info, projects_query,
                       require_writer, visible_task)
from pydantic import Field
from typing import Literal

router=APIRouter()
CATALOG=json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
TEMPLATES={t["id"]:t for t in CATALOG}
FORMATS={".pdf":b"%PDF-",".png":b"\x89PNG\r\n\x1a\n",".jpg":b"\xff\xd8\xff",".jpeg":b"\xff\xd8\xff",
         ".docx":b"PK\x03\x04",".xlsx":b"PK\x03\x04"}
LIMIT=20*1024*1024

def project_for(db,t,pid):
    if pid is None:return None
    p=db.get(Project,pid)
    if not p or p.order_id!=t.order_id:fail(422,"项目须来自本订单通过内审的立项清单")
    return p

def office_valid(stream,ext):
    if ext not in (".docx",".xlsx"):return True
    try:
        with zipfile.ZipFile(stream) as z:
            names=set(z.namelist())
            return "[Content_Types].xml" in names and ("word/document.xml" if ext==".docx" else "xl/workbook.xml") in names
    except (zipfile.BadZipFile,OSError):
        return False
    finally:stream.seek(0)

def store_client():
    import boto3
    return boto3.client("s3",endpoint_url=os.getenv("S3_ENDPOINT") or None)

def store_blob(key,stream):
    if os.getenv("S3_BUCKET"):
        store_client().upload_fileobj(stream,os.environ["S3_BUCKET"],key)
    else:
        dest=DATA/"objects"/key
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open("xb") as out:
            while chunk:=stream.read(65536):out.write(chunk)

def drop_blob(key):
    if os.getenv("S3_BUCKET"):store_client().delete_object(Bucket=os.environ["S3_BUCKET"],Key=key)
    else:(DATA/"objects"/key).unlink(missing_ok=True)

def read_blob(f):
    if os.getenv("S3_BUCKET"):
        stream=store_client().get_object(Bucket=os.environ["S3_BUCKET"],Key=f.storage)["Body"]
        try:data=stream.read(LIMIT+1)
        finally:stream.close()
    else:
        with (DATA/"objects"/f.storage).open("rb") as stream:data=stream.read(LIMIT+1)
    if len(data)!=f.size or hashlib.sha256(data).hexdigest()!=f.digest:fail(409,"文件完整性校验失败")
    return data

def deliver(data,name,media):
    return Response(data,media_type=media,headers={"Content-Disposition":"attachment; filename*=UTF-8''"+quote(name,safe=""),"Cache-Control":"no-store"})

@router.post("/materials/upload")
def upload(request:Request,db:DB,u:Actor,task:int=FieldValue(...),category:str=FieldValue(...,min_length=1,max_length=64),
           file:UploadFile=File(...),project:int|None=FieldValue(None),previous:int|None=FieldValue(None)):
    t=visible_task(db,u,task,True);require_writer(db,u,t);project_for(db,t,project)
    if project is None and t.kind!="立项":fail(422,"请选择材料对应的项目")
    if previous:
        old=db.get(FileObject,previous)
        if not old or old.task!=task or old.project!=project or old.category!=category:fail(422,"上一版本不属于此材料")
    name=(file.filename or "").replace("\\","/").split("/")[-1].strip()
    ext=Path(name).suffix.lower()
    if not name or len(name)>150 or any(ord(c)<32 for c in name) or ext not in FORMATS:fail(422,"支持 PDF、PNG、JPEG、DOCX、XLSX")
    key=secrets.token_hex(24)
    hashed=hashlib.sha256();size=0
    with tempfile.SpooledTemporaryFile(max_size=1024*1024,dir=DATA) as stream:
        while part:=file.file.read(65536):
            size+=len(part)
            if size>LIMIT:fail(422,"单文件超过20MB")
            stream.write(part);hashed.update(part)
        stream.seek(0)
        if not stream.read(8).startswith(FORMATS[ext]):fail(422,"文件类型与扩展名不符")
        stream.seek(0)
        if not office_valid(stream,ext):fail(422,"Office 文件结构无效")
        store_blob(key,stream)
    try:
        f=FileObject(task=task,project=project,category=category,name=name,storage=key,digest=hashed.hexdigest(),size=size,previous=previous,actor=u.id)
        db.add(f);t.revision+=1;db.flush()
        record(db,request,u,"file.upload",f.id,{"sha256":f.digest,"bytes":size})
        db.commit()
    except Exception:
        drop_blob(key)
        raise
    return ok(file_info(f))

@router.get("/materials")
def materials(task:int,db:DB,u:Actor):
    visible_task(db,u,task)
    fs=list(db.scalars(select(FileObject).where(FileObject.task==task).order_by(FileObject.id)))
    return ok([file_info(f) for f in fs])

@router.get("/materials/{fid}/download")
def download(fid:int,request:Request,db:DB,u:Actor):
    f=db.get(FileObject,fid)
    if not f:fail(404,"文件不存在")
    visible_task(db,u,f.task)
    data=read_blob(f);record(db,request,u,"file.read",fid);db.commit()
    return deliver(data,f.name,"application/octet-stream")

class DocumentForm(Form):
    task:int=Field(gt=0)
    project:int|None=Field(default=None,gt=0)
    template:str=Field(max_length=50)
    title:str=Field(min_length=1,max_length=128)
    values:dict[str,str]=Field(max_length=40)
    revision:int|None=Field(default=None,gt=0)

@router.get("/templates")
def templates(u:Actor):
    return ok(CATALOG)

@router.get("/templates/{category}")
def category_templates(category:str,u:Actor):
    return ok([t for t in CATALOG if t["category"]==category])

def save_document(form,request,db,u,entry=None):
    t=visible_task(db,u,form.task,True);require_writer(db,u,t);project_for(db,t,form.project)
    if entry and (entry.task!=t.id or entry.kind!="document"):fail(404,"文书不存在")
    template=TEMPLATES.get(form.template)
    if not template:fail(422,"模板不存在")
    if set(form.values)!=set(template["fields"]) or any(not s.strip() or len(s)>10000 for s in form.values.values()):
        fail(422,"请完整填写所选模板的各个栏目")
    if entry:
        checked_revision(entry,form.revision)
    else:
        entry=Entry(task=t.id,kind="document",key=secrets.token_hex(10),actor=u.id)
    entry.project=form.project
    entry.payload=form.model_dump(exclude={"task","project","revision"})
    db.add(entry);t.revision+=1;db.flush()
    record(db,request,u,"document.save",entry.id,{"template":form.template,"revision":entry.revision})
    db.commit();return ok(object_info(entry))

@router.post("/documents")
def create_document(form:DocumentForm,request:Request,db:DB,u:Actor):
    return save_document(form,request,db,u)

@router.put("/documents/{eid}")
def edit_document(eid:int,form:DocumentForm,request:Request,db:DB,u:Actor):
    entry=db.get(Entry,eid)
    if not entry:fail(404,"文书不存在")
    return save_document(form,request,db,u,entry)

def word_bytes(payload,record_no):
    t=TEMPLATES[payload["template"]]
    d=Document();section=d.sections[0]
    section.page_width=Cm(21);section.page_height=Cm(29.7)
    section.top_margin=Cm(3.7);section.left_margin=Cm(2.8);section.right_margin=Cm(2.6)
    base=d.styles["Normal"];base.font.name="仿宋";base.font.size=Pt(16);base._element.rPr.rFonts.set(qn("w:eastAsia"),"仿宋")
    if t["category"]=="resolution":
        p=d.add_paragraph();p.alignment=1
        r=p.add_run(payload["values"].get("发文单位","")+"文件");r.font.color.rgb=RGBColor(200,0,0);r.bold=True;r.font.size=Pt(28)
    p=d.add_paragraph();p.alignment=1;p.add_run(payload["title"]).bold=True
    d.add_paragraph(record_no+"　·　"+t["name"])
    for key in t["fields"]:
        p=d.add_paragraph();p.add_run(key).bold=True
        d.add_paragraph(payload["values"][key])
    stream=io.BytesIO();d.save(stream);return stream.getvalue()

@router.get("/documents/{eid}/word")
def word(eid:int,request:Request,db:DB,u:Actor):
    doc=db.get(Entry,eid)
    if not doc or doc.kind!="document":fail(404,"文书不存在")
    task=visible_task(db,u,doc.task)
    label="审核通过稿" if task.status in {"customer","complete","archived"} else "草稿"
    data=word_bytes(doc.payload,f"{label} · 工作底稿 {doc.id} · 版本 {doc.revision}")
    record(db,request,u,"document.export",eid);db.commit()
    return deliver(data,doc.payload["title"]+".docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document")

class IssueForm(Form):
    task:int=Field(gt=0)
    project:int|None=Field(default=None,gt=0)
    question:str=Field(min_length=1,max_length=2000)
    due:str=Field(default="",max_length=10)

class Comment(Form):
    note:str=Field(min_length=1,max_length=2000)

@router.post("/issues")
def new_issue(form:IssueForm,request:Request,db:DB,u:Actor):
    t=visible_task(db,u,form.task,True);require_writer(db,u,t);project_for(db,t,form.project)
    if t.line!="finance":fail(422,"请从财务任务发起补件")
    e=Entry(task=t.id,project=form.project,kind="issue",key=secrets.token_hex(10),state="open",payload=form.model_dump(),actor=u.id)
    db.add(e);t.revision+=1;db.flush();record(db,request,u,"issue.open",e.id);db.commit();return ok(object_info(e))

@router.post("/issues/{eid}/{action}")
def issue_action(eid:int,action:Literal["reply","close"],form:Comment,request:Request,db:DB,u:Actor):
    e=db.get(Entry,eid)
    if not e or e.kind!="issue":fail(404,"补件不存在")
    t=visible_task(db,u,e.task,True);require_writer(db,u,t)
    if action=="reply" and (db.get(Department,u.department).line!="research" or e.state!="open"):fail(403,"请由科研协办人回复待补件问题")
    if action=="close" and (u.id!=e.actor or e.state!="replied"):fail(403,"由原发起人核对回复后关闭")
    e.state="replied" if action=="reply" else "closed"
    e.payload={**e.payload,action:form.note,action+"_by":u.id}
    t.revision+=1;record(db,request,u,"issue."+action,eid);db.commit();return ok(object_info(e))

@router.post("/tasks/{tid}/joint-sign")
def cosign(tid:int,form:Comment,request:Request,db:DB,u:Actor):
    t=visible_task(db,u,tid,True);require_writer(db,u,t)
    if t.kind!="结题":fail(409,"仅限结题任务")
    line=db.get(Department,u.department).line
    if line not in {"research","finance"}:fail(403,"仅业务线可联签")
    e=Entry(task=tid,kind="cosign",key=line,state="signed",payload={"opinion":form.note},actor=u.id)
    db.add(e);t.revision+=1;record(db,request,u,"joint-sign."+line,tid);db.commit();return ok()

@router.get("/tasks/{tid}/archive.zip")
def archive(tid:int,request:Request,db:DB,u:Actor):
    t=visible_task(db,u,tid)
    if t.status!="archived":fail(409,"请先完成归档")
    events=list(db.scalars(select(History).where(History.task==tid).order_by(History.id)))
    final=next(h.snapshot for h in reversed(events) if h.action=="archive")
    tmp=tempfile.TemporaryFile(dir=DATA)
    try:
        with zipfile.ZipFile(tmp,"w",compression=zipfile.ZIP_DEFLATED) as z:
            manifest={"task":object_info(t),"archive":final,"history":[object_info(h) for h in events]}
            z.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
            for meta in final["files"]:
                f=db.get(FileObject,meta["id"]);z.writestr(f"materials/{f.id}-{f.name}",read_blob(f))
            for e in final["entries"]:
                if e["kind"]=="document":
                    z.writestr(f"documents/{e['id']}.docx",word_bytes(e["payload"],f"归档底稿 {e['id']}"))
        tmp.seek(0);record(db,request,u,"archive.download",tid);db.commit()
    except Exception:
        tmp.close()
        raise
    def chunks():
        try:
            while block:=tmp.read(65536):yield block
        finally:tmp.close()
    return StreamingResponse(chunks(),media_type="application/zip",headers={"Content-Disposition":f'attachment; filename="task-{tid}.zip"'})
