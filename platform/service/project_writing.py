from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import Column, ForeignKey, Integer, JSON, and_, func, or_, select

from .auth import Actor, DB, Form, fail, ok, record, roles
from .configuration import catalog
from .db import Base, Department, Entry, ID, Member, Project, Task
from .materials import DocumentForm, deliver, save_document, word_bytes
from .workflow import access_tasks, checked_revision, object_info, projects_query, visible_task

router = APIRouter(prefix="/projects/{pid}/writing")


class ProjectDraft(Base):
    __tablename__ = "rd_writing_draft"
    id = Column(ID, primary_key=True)
    project = Column(ID, ForeignKey("rd_project.id"), nullable=False, index=True)
    author = Column(ID, ForeignKey("sys_user.id"), nullable=False)
    payload = Column(JSON, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": revision}


class DraftText(Form):
    template: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=128)
    values: dict[str, str] = Field(max_length=40)
    revision: int | None = Field(default=None, gt=0)


class Transfer(Form):
    task: int = Field(gt=0)
    revision: int = Field(gt=0)


def workspace(db, u, pid):
    project = db.scalar(projects_query(db, u).where(Project.id == pid))
    if not project:
        fail(404, "项目不存在或不在本人数据范围")
    research_post = db.get(Department, u.department).line == "research" and bool(roles(u) & {"staff", "leader"})
    assigned = or_(Task.owner == u.id, Task.id.in_(select(Member.task).where(Member.user == u.id)))
    tasks = db.scalars(select(Task).where(Task.order_id == project.order_id, Task.line == "research",
                       assigned).order_by(Task.id)).all() if research_post else []
    writable = not project.details.get("closed") and any(
        t.id == project.task or t.status in {"assigned", "working", "revision"} for t in tasks)
    return project, writable, [t for t in tasks if t.status in {"working", "revision"}]


def own_draft(db, u, pid, did):
    draft = db.scalar(select(ProjectDraft).where(ProjectDraft.id == did, ProjectDraft.project == pid,
                                                 ProjectDraft.author == u.id))
    if not draft:
        fail(404, "草稿不存在或不属于当前账号")
    return draft


@router.get("")
def details(pid: int, db: DB, u: Actor):
    p, writable, tasks = workspace(db, u, pid)
    linked = Entry.project == pid
    # Before approval there was no project ID. Only an unambiguous sole project inherits those documents.
    if db.scalar(select(func.count(Project.id)).where(Project.task == p.task)) == 1:
        linked = or_(linked, and_(Entry.project.is_(None), Entry.task == p.task))
    docs = db.execute(select(Entry, Task).join(Task, Entry.task == Task.id).where(
        Task.order_id == p.order_id, access_tasks(db,u), Entry.kind == "document", linked).order_by(Entry.id.desc()))
    drafts = db.scalars(select(ProjectDraft).where(ProjectDraft.project == pid, ProjectDraft.author == u.id)
                        .order_by(ProjectDraft.id.desc()))
    return ok({"project": object_info(p), "can_write": bool(writable),
               "tasks": [{"id": t.id, "title": t.title} for t in tasks],
               "drafts": [object_info(d) for d in drafts],
               "documents": [{"id": e.id, "title": e.payload["title"], "task": t.id,
                              "task_title": t.title, "status": t.status} for e,t in docs]})


def store_draft(pid, form, request, db, u, did=None):
    _, writable, _ = workspace(db, u, pid)
    if not writable:
        fail(403, "仅本项目获派的科研承办或协办可编写未结题项目的材料")
    if did is None:
        draft = ProjectDraft(project=pid, author=u.id)
        layout = catalog(db).get(form.template)
        if not layout or layout["category"] == "pick":
            fail(422, "请选择科研文书大纲")
    else:
        draft = own_draft(db, u, pid, did)
        checked_revision(draft, form.revision)
        layout = draft.payload["layout"]
        if form.template != layout["id"]:
            fail(422, "已保存草稿须沿用原大纲")
    if not form.title.strip() or set(form.values) - set(layout["fields"]) or any(len(s)>10000 for s in form.values.values()):
        fail(422, "请填写标题，按大纲填写各栏，每栏最多一万字")
    draft.payload = {"template": layout["id"], "layout": layout, "title": form.title.strip(),
                     "values": {key: form.values.get(key, "") for key in layout["fields"]}}
    db.add(draft)
    db.flush()
    record(db, request, u, "project.draft.save", draft.id, {"project": pid, "revision": draft.revision})
    db.commit()
    return ok(object_info(draft))


@router.post("/drafts")
def create(pid: int, form: DraftText, request: Request, db: DB, u: Actor):
    return store_draft(pid, form, request, db, u)


@router.put("/drafts/{did}")
def update(pid: int, did: int, form: DraftText, request: Request, db: DB, u: Actor):
    return store_draft(pid, form, request, db, u, did)


@router.get("/drafts/{did}/word")
def export(pid: int, did: int, request: Request, db: DB, u: Actor):
    workspace(db, u, pid)
    draft = own_draft(db, u, pid, did)
    data = word_bytes(draft.payload, f"项目草稿 · 版本 {draft.revision}")
    record(db, request, u, "project.draft.export", did)
    db.commit()
    return deliver(data, draft.payload["title"] + ".docx",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.post("/drafts/{did}/transfer")
def transfer(pid: int, did: int, form: Transfer, request: Request, db: DB, u: Actor):
    project, writable, _ = workspace(db, u, pid)
    if not writable:
        fail(403, "当前项目不可编写")
    draft = own_draft(db, u, pid, did)
    checked_revision(draft, form.revision)
    task = visible_task(db, u, form.task, True)
    if task.line != "research" or task.order_id != project.order_id:
        fail(422, "请选择同一订单的科研任务")
    payload = draft.payload
    document = DocumentForm(task=task.id, project=pid, title=payload["title"],
                            template=payload["template"], values=payload["values"])
    db.delete(draft)
    record(db, request, u, "project.draft.transfer", did, {"task": task.id, "project": pid})
    return save_document(document, request, db, u, layout=payload["layout"])
