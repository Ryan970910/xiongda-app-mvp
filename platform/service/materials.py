import hashlib
import io
import json
import os
import secrets
import tempfile
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form as FieldValue, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from sqlalchemy import select

from .auth import Actor, DB, Form, fail, ok, record
from .configuration import catalog
from .db import DATA, Department, Entry, FileObject, History, Member, Order, Project, Task
from .workflow import (business_snapshot, checked_revision, file_info, object_info, projects_query,
                       require_writer, visible_task, working_digest)
from pydantic import Field
from typing import Literal

router=APIRouter()
CATALOG=json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
TEMPLATES={t["id"]:t for t in CATALOG}
FORMATS={".pdf":b"%PDF-",".png":b"\x89PNG\r\n\x1a\n",".jpg":b"\xff\xd8\xff",".jpeg":b"\xff\xd8\xff",
         ".docx":b"PK\x03\x04",".xlsx":b"PK\x03\x04"}
LIMIT=20*1024*1024

MATERIALS_BY_STAGE={
    "立项":["立项决议","立项申请","研发任务书"],"调整":["调整申请","会商意见"],
    "结题":["结题报告","验收证据"],"费用归集":["考勤工资","费用凭证"],
    "辅助账":["费用凭证","辅助账"],"跟进":["实验记录"]}

class EvidenceLink(Form):
    task:int=Field(gt=0)
    file_id:int=Field(gt=0)
    project:int=Field(gt=0)
    stage:str=Field(min_length=1,max_length=64)
    fee_id:int|None=Field(default=None,gt=0)

@router.post("/materials/link")
def link_evidence(form:EvidenceLink,request:Request,db:DB,u:Actor):
    t=visible_task(db,u,form.task,True);require_writer(db,u,t);project_for(db,t,form.project)
    f=db.get(FileObject,form.file_id)
    if not f or f.task!=t.id or f.project not in (None,form.project):fail(422,"材料须属于当前任务和项目")
    if form.fee_id:
        fee=db.get(Entry,form.fee_id)
        if not fee or fee.kind!="fee" or fee.task!=t.id or fee.project!=form.project:fail(422,"凭证须与材料项目及任务一致")
    e=Entry(task=t.id,project=form.project,kind="evidence",key=f"{f.id}/{form.project}/{form.fee_id or 0}/{form.stage}",state="linked",
            payload=form.model_dump(),actor=u.id)
    db.add(e);t.revision+=1;db.flush();record(db,request,u,"material.link",f.id,form.model_dump());db.commit()
    return ok(object_info(e))

def evidence_check(t,files,entries):
    replaced={f["previous"] for f in files if f.get("previous")}
    current={f["id"]:f for f in files if f["id"] not in replaced}
    linked={e["payload"]["stage"] for e in entries if e["kind"]=="evidence" and e["payload"]["file_id"] in current}
    present=linked|{f["category"] for f in current.values()}
    present.update({"resolution":"立项决议","application":"立项申请","taskbook":"研发任务书","completion":"结题报告"}.get(
        e["payload"].get("layout",{}).get("category"),"") for e in entries if e["kind"]=="document")
    required=MATERIALS_BY_STAGE.get(t.kind,["证明材料"])
    missing=[label for label in required if label not in present]
    return {"required":required,"missing":missing,"percent":round(100*(len(required)-len(missing))/len(required))}

def project_evidence(t,files,entries,projects):
    rows=[]
    for p in projects:
        links=[e for e in entries if e.get("project")==p.id or (e["kind"]=="draft_material" and e["payload"]["code"]==p.code)]
        ids={e["payload"]["file_id"] for e in links if e["kind"] in {"evidence","draft_material"}}
        related=[f for f in files if f["project"]==p.id or f["id"] in ids]
        rows.append({"code":p.code,**evidence_check(t,related,links)})
    return rows

def delivery_rows(db,t,snapshot):
    order=db.get(Order,t.order_id)
    rows=[["订单编号","任务","交付物","数量","版本","校验信息"]]
    for e in snapshot["entries"]:
        if e["kind"]=="document":
            rows.append([order.code,t.title,e["payload"]["title"],1,e["revision"],e["payload"].get("issuance",{}).get("number","")])
    replaced={f.get("previous") for f in snapshot["files"]}
    for f in snapshot["files"]:
        if f["id"] not in replaced:
            rows.append([order.code,t.title,f["name"],1,f["id"],f["digest"]])
    if snapshot.get("draft",{}).get("summary"):rows.append([order.code,t.title,"作业底稿",1,t.version,"见提交快照"])
    return rows

@router.get("/tasks/{tid}/delivery.xlsx")
def delivery(tid:int,request:Request,db:DB,u:Actor):
    from .finance import write_xlsx
    t=visible_task(db,u,tid)
    if t.status not in {"customer","complete","archived"}:fail(409,"内审通过后可生成交付清单")
    approved=db.scalar(select(History).where(History.task==tid,History.version==t.version,History.action=="audit.pass").order_by(History.id.desc()).limit(1))
    snapshot=approved.snapshot if approved and approved.snapshot else business_snapshot(db,t)
    data=write_xlsx([("交付清单",delivery_rows(db,t,snapshot))])
    record(db,request,u,"delivery.list",tid);db.commit()
    return deliver(data,"交付清单.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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

@router.get("/projects/{pid}/evidence.zip")
def project_archive(pid:int,request:Request,db:DB,u:Actor):
    from .workflow import access_tasks
    from .finance import write_xlsx
    p=db.scalar(projects_query(db,u).where(Project.id==pid))
    if not p:fail(404,"项目不存在或不可见")
    tasks=db.scalars(select(Task).where(Task.order_id==p.order_id,Task.status=="archived",access_tasks(db,u)))
    index=[["项目编号","任务名称","材料或文书","档案路径","文件指纹或文书版本"]]
    checks=[["项目编号","归档任务","当前版本","关键材料齐备率","待补材料"]]
    tmp=tempfile.TemporaryFile(dir=DATA)
    try:
        with zipfile.ZipFile(tmp,"w",compression=zipfile.ZIP_DEFLATED) as package:
            for t in tasks:
                h=db.scalar(select(History).where(History.task==t.id,History.action=="archive").order_by(History.id.desc()).limit(1))
                if not h or not h.snapshot:continue
                snap=h.snapshot
                links=[e for e in snap["entries"] if e.get("project")==pid or (e["kind"]=="draft_material" and e["payload"]["code"]==p.code)]
                linked_ids={e["payload"]["file_id"] for e in links if e["kind"] in {"evidence","draft_material"}}
                one=t.id==p.task and [x["code"] for x in snap["draft"].get("projects",[])]==[p.code]
                files=[f for f in snap["files"] if f["project"]==pid or f["id"] in linked_ids or (one and f["project"] is None)]
                entries=[e for e in snap["entries"] if e in links or (one and e["kind"]=="document" and e.get("project") is None)]
                if not (files or entries or t.id==p.task):continue
                result=evidence_check(t,files,entries)
                checks.append([p.code,t.title,t.version,result["percent"],"、".join(result["missing"])])
                for f in files:
                    location=f"task-{t.id}/files/{f['id']}-{f['name']}"
                    package.writestr(location,read_blob(db.get(FileObject,f["id"])))
                    index.append([p.code,t.title,f["name"],location,f["digest"]])
                for e in entries:
                    if e["kind"]=="document":
                        location=f"task-{t.id}/documents/{e['id']}.docx"
                        package.writestr(location,word_bytes(e["payload"],e["key"]))
                        index.append([p.code,t.title,e["payload"]["title"],location,e["revision"]])
            if len(checks)==1:fail(409,"本项目尚无本人可见的归档任务")
            package.writestr("项目证据链.xlsx",write_xlsx([("材料索引",index),("完整度",checks)]))
        tmp.seek(0);record(db,request,u,"project.evidence.export",pid);db.commit()
    except Exception:
        tmp.close()
        raise
    return StreamingResponse(file_chunks(tmp),media_type="application/zip",headers={"Content-Disposition":f'attachment; filename="project-{pid}.zip"'})

def file_chunks(stream):
    try:
        while block:=stream.read(65536):yield block
    finally:stream.close()

def accept_blob(file):
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
    return name,key,hashed.hexdigest(),size

@router.post("/materials/upload")
def upload(request:Request,db:DB,u:Actor,task:int=FieldValue(...),category:str=FieldValue(...,min_length=1,max_length=64),
           file:UploadFile=File(...),project:int|None=FieldValue(None),previous:int|None=FieldValue(None),project_code:str=FieldValue("",max_length=64)):
    t=visible_task(db,u,task,True);require_writer(db,u,t);project_for(db,t,project)
    if project is None and t.kind!="立项":fail(422,"请选择材料对应的项目")
    codes=[p["code"] for p in t.draft.get("projects",[])]
    if project_code and (project or t.kind!="立项" or project_code not in codes):fail(422,"材料编号须匹配当前立项清单")
    if not project and len(codes)>1 and not project_code:fail(422,"请选择材料对应的立项编号")
    if not project and not project_code and len(codes)==1:project_code=codes[0]
    if previous:
        old=db.get(FileObject,previous)
        if not old or old.task!=task or old.project!=project or old.category!=category:fail(422,"上一版本不属于此材料")
    name,key,digest,size=accept_blob(file)
    try:
        f=FileObject(task=task,project=project,category=category,name=name,storage=key,digest=digest,size=size,previous=previous,actor=u.id)
        db.add(f);t.revision+=1;db.flush()
        if project_code:
            db.add(Entry(task=t.id,kind="draft_material",key=str(f.id),state="linked",actor=u.id,
                         payload={"code":project_code,"file_id":f.id}))
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
def templates(db:DB,u:Actor):
    return ok(list(catalog(db).values()))

@router.get("/templates/{category}")
def category_templates(category:str,db:DB,u:Actor):
    return ok([t for t in catalog(db).values() if t["category"]==category])

def save_document(form,request,db,u,entry=None):
    t=visible_task(db,u,form.task,True);require_writer(db,u,t);project_for(db,t,form.project)
    if entry and (entry.task!=t.id or entry.kind!="document"):fail(404,"文书不存在")
    template=catalog(db).get(form.template)
    if not template:fail(422,"模板不存在")
    if set(form.values)!=set(template["fields"]) or any(not s.strip() or len(s)>10000 for s in form.values.values()):
        fail(422,"请完整填写所选模板的各个栏目")
    if entry:
        checked_revision(entry,form.revision)
    else:
        entry=Entry(task=t.id,kind="document",key=secrets.token_hex(10),actor=u.id)
    entry.project=form.project
    entry.payload={**form.model_dump(exclude={"task","project","revision"}),"layout":template}
    db.add(entry);t.revision+=1;db.flush()
    record(db,request,u,"document.save",entry.id,{"template":form.template,"revision":entry.revision})
    db.commit();return ok(object_info(entry))

def issue_documents(db,task):
    rows=db.scalars(select(Entry).where(Entry.task==task.id,Entry.kind=="document"))
    for doc in rows:
        if (doc.payload.get("layout") or TEMPLATES[doc.payload["template"]])["category"]!="resolution":continue
        issue=Entry(task=task.id,kind="issuance",key=f"{doc.id}/{task.version}",actor=doc.actor,state="approved",payload={})
        db.add(issue);db.flush()
        projects=task.draft.get("projects",[])
        data={"number":f"研服〔{date.today().year}〕{issue.id}号","projects":projects,
              "budget":str(sum((Decimal(p["budget"]) for p in projects),Decimal(0))),"date":str(date.today())}
        issue.payload=data;doc.payload={**doc.payload,"issuance":data}

@router.post("/documents")
def create_document(form:DocumentForm,request:Request,db:DB,u:Actor):
    return save_document(form,request,db,u)

@router.put("/documents/{eid}")
def edit_document(eid:int,form:DocumentForm,request:Request,db:DB,u:Actor):
    entry=db.get(Entry,eid)
    if not entry:fail(404,"文书不存在")
    return save_document(form,request,db,u,entry)

def word_bytes(payload,record_no):
    t=payload.get("layout") or TEMPLATES[payload["template"]]
    d=Document();section=d.sections[0]
    section.page_width=Cm(21);section.page_height=Cm(29.7)
    section.top_margin=Cm(3.7);section.left_margin=Cm(2.8);section.right_margin=Cm(2.6);section.bottom_margin=Cm(3.5)
    base=d.styles["Normal"];base.font.name="仿宋";base.font.size=Pt(16);base._element.rPr.rFonts.set(qn("w:eastAsia"),"仿宋")
    if t["category"]=="resolution":
        p=d.add_paragraph();p.alignment=1
        r=p.add_run(payload["values"].get("发文单位","")+"文件");r.font.color.rgb=RGBColor(200,0,0);r.bold=True;r.font.size=Pt(28)
    issue=payload.get("issuance",{})
    if issue:d.add_paragraph(issue["number"]).alignment=1
    if t["category"]=="resolution":
        border=OxmlElement("w:pBdr");line=OxmlElement("w:bottom")
        for k,v in {"val":"single","sz":"12","color":"C80000","space":"4"}.items():line.set(qn("w:"+k),v)
        border.append(line);d.paragraphs[-1]._p.get_or_add_pPr().append(border)
    p=d.add_paragraph();p.alignment=1;p.add_run(payload["title"]).bold=True
    d.add_paragraph(record_no+"　·　"+t["name"])
    for key in t["fields"]:
        p=d.add_paragraph();p.add_run(key).bold=True
        value=payload["values"][key]
        if issue and key=="年度预算合计":value=issue["budget"]+" 元"
        if issue and key=="项目清单":value="详见附件《年度立项科研项目清单》"
        d.add_paragraph(value)
    if issue:
        d.add_page_break();d.add_heading("附件　年度立项科研项目清单",1)
        table=d.add_table(rows=0,cols=5);table.style="Table Grid"
        for row in [["项目编号","项目名称","负责人","实施周期","预算（元）"]]+[
            [p["code"],p["name"],p["leader"],p["start"]+" 至 "+p["end"],p["budget"]] for p in issue["projects"]]:
            for cell,value in zip(table.add_row().cells,row):cell.text=str(value)
        d.add_paragraph("预算合计　"+issue["budget"]+" 元")
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
    due:date=Field(default_factory=lambda:date.today()+timedelta(days=3))

class Comment(Form):
    note:str=Field(min_length=1,max_length=2000)

@router.post("/issues")
def new_issue(form:IssueForm,request:Request,db:DB,u:Actor):
    t=visible_task(db,u,form.task,True);require_writer(db,u,t);project_for(db,t,form.project)
    if t.line!="finance":fail(422,"请从财务任务发起补件")
    if form.due<date.today():fail(422,"补件期限不能早于发起日期")
    e=Entry(task=t.id,project=form.project,kind="issue",key=secrets.token_hex(10),state="open",payload=form.model_dump(mode="json"),actor=u.id)
    db.add(e);t.revision+=1;db.flush();record(db,request,u,"issue.open",e.id);db.commit();return ok(object_info(e))

@router.post("/issues/{eid}/{action}")
def issue_action(eid:int,action:Literal["reply","close"],form:Comment,request:Request,db:DB,u:Actor):
    e=db.get(Entry,eid)
    if not e or e.kind!="issue":fail(404,"补件不存在")
    t=visible_task(db,u,e.task,True);require_writer(db,u,t)
    if action=="reply" and (db.get(Department,u.department).line!="research" or e.state!="open"):fail(403,"请由科研协办人回复待补件问题")
    if action=="close" and (u.id!=e.actor or e.state!="replied"):fail(403,"由原发起人核对回复后关闭")
    e.state="replied" if action=="reply" else "closed"
    from .db import now
    e.payload={**e.payload,action:form.note,action+"_by":u.id,action+"_at":now().isoformat()}
    t.revision+=1;record(db,request,u,"issue."+action,eid);db.commit();return ok(object_info(e))

@router.post("/tasks/{tid}/joint-sign")
def cosign(tid:int,form:Comment,request:Request,db:DB,u:Actor):
    t=visible_task(db,u,tid,True);require_writer(db,u,t)
    if t.kind!="结题" and t.line!="finance":fail(409,"仅限财务资料联审或结题联签")
    line=db.get(Department,u.department).line
    if line not in {"research","finance"}:fail(403,"仅业务线可联签")
    digest=working_digest(db,t)
    other=db.scalar(select(Entry).where(Entry.task==tid,Entry.kind=="cosign",Entry.key!=line,Entry.actor==u.id))
    if other and other.payload.get("digest")==digest:fail(403,"两线须由不同人员确认")
    e=db.scalar(select(Entry).where(Entry.task==tid,Entry.kind=="cosign",Entry.key==line))
    if e and e.payload.get("digest")==digest:fail(409,"本线已确认当前内容")
    if not e:e=Entry(task=tid,kind="cosign",key=line,state="signed")
    e.actor=u.id;e.payload={"opinion":form.note,"digest":digest}
    db.add(e);t.revision+=1;record(db,request,u,"joint-sign."+line,tid,e.payload);db.commit();return ok()

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
            from .finance import write_xlsx
            z.writestr("交付清单.xlsx",write_xlsx([("交付清单",delivery_rows(db,t,final))]))
            for meta in final["files"]:
                f=db.get(FileObject,meta["id"]);z.writestr(f"materials/{f.id}-{f.name}",read_blob(f))
            for e in final["entries"]:
                if e["kind"]=="document":
                    z.writestr(f"documents/{e['id']}.docx",word_bytes(e["payload"],f"归档底稿 {e['id']}"))
        tmp.seek(0);record(db,request,u,"archive.download",tid);db.commit()
    except Exception:
        tmp.close()
        raise
    return StreamingResponse(file_chunks(tmp),media_type="application/zip",headers={"Content-Disposition":f'attachment; filename="task-{tid}.zip"'})
