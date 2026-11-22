import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, JSON,
                        Numeric, String, Text, UniqueConstraint, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA = Path(os.getenv("WORKSPACE_DATA", Path(__file__).resolve().parents[1] / "runtime"))
DATA.mkdir(parents=True, exist_ok=True)
URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA / 'workspace.db').as_posix()}")
engine = create_engine(URL, pool_pre_ping=True, connect_args={"timeout": 20, "check_same_thread": False} if URL.startswith("sqlite") else {})
if URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_config(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

Session = sessionmaker(bind=engine, expire_on_commit=False)
ID = BigInteger().with_variant(Integer, "sqlite")
def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase):
    pass

class Department(Base):
    __tablename__ = "sys_dept"
    id = Column(ID, primary_key=True)
    name = Column(String(80), nullable=False, unique=True)
    line = Column(String(16), nullable=False)
    parent_id = Column(ID, ForeignKey("sys_dept.id"))

class User(Base):
    __tablename__ = "sys_user"
    id = Column(ID, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    employee_no = Column(String(40), nullable=False, unique=True)
    department = Column(ID, ForeignKey("sys_dept.id"), nullable=False)
    team = Column(String(64), nullable=False)
    roles = Column(JSON, nullable=False)
    contact = Column(String(160), nullable=False, default="")
    enabled = Column(Boolean, default=True, nullable=False)
    password_hash = Column(String(180), nullable=False)
    history = Column(JSON, nullable=False, default=list)
    must_change = Column(Boolean, default=True, nullable=False)
    changed = Column(DateTime, default=now, nullable=False)
    failures = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime)
    last_login = Column(DateTime)
    revision = Column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": revision}

class LoginSession(Base):
    __tablename__ = "sys_session"
    id = Column(String(64), primary_key=True)
    user_id = Column(ID, ForeignKey("sys_user.id"), nullable=False, index=True)
    refresh_hash = Column(String(64), nullable=False)
    last_seen = Column(DateTime, nullable=False, default=now)
    expires = Column(DateTime, nullable=False)

class Audit(Base):
    __tablename__ = "sys_operation_log"
    id = Column(ID, primary_key=True)
    user_id = Column(ID, ForeignKey("sys_user.id"))
    at = Column(DateTime, nullable=False, default=now, index=True)
    action = Column(String(90), nullable=False)
    subject = Column(String(160), nullable=False)
    details = Column(JSON, nullable=False)
    ip = Column(String(64), nullable=False)
    agent = Column(String(240), nullable=False)

class SessionPost(Base):
    __tablename__ = "sys_session_post"
    session_id = Column(String(64),ForeignKey("sys_session.id",ondelete="CASCADE"),primary_key=True)
    department = Column(ID,ForeignKey("sys_dept.id"),nullable=False)

class Customer(Base):
    __tablename__ = "biz_customer"
    id = Column(ID, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    code = Column(String(32), unique=True, nullable=False)
    manager = Column(ID, ForeignKey("sys_user.id"), nullable=False)
    department = Column(ID, ForeignKey("sys_dept.id"), nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    deleted = Column(Boolean, default=False, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": revision}

class Contract(Base):
    __tablename__ = "biz_contract"
    id = Column(ID, primary_key=True)
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    customer = Column(ID, ForeignKey("biz_customer.id"), nullable=False, index=True)
    amount = Column(Numeric(18,2), nullable=False)
    details = Column(JSON, nullable=False)
    status = Column(String(24), nullable=False, default="draft")
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": revision}

class Order(Base):
    __tablename__ = "biz_order"
    id = Column(ID, primary_key=True)
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    customer = Column(ID, ForeignKey("biz_customer.id"), nullable=False, index=True)
    contract = Column(ID, ForeignKey("biz_contract.id"), nullable=False)
    details = Column(JSON, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": revision}

class Task(Base):
    __tablename__ = "wf_task"
    id = Column(ID, primary_key=True)
    order_id = Column(ID, ForeignKey("biz_order.id"), nullable=False, index=True)
    customer = Column(ID, ForeignKey("biz_customer.id"), nullable=False, index=True)
    title = Column(String(128), nullable=False)
    line = Column(String(16), nullable=False)
    owner = Column(ID, ForeignKey("sys_user.id"), nullable=False)
    dispatcher = Column(ID, ForeignKey("sys_user.id"), nullable=False)
    department = Column(ID, ForeignKey("sys_dept.id"), nullable=False)
    team = Column(String(64), nullable=False)
    kind = Column(String(24), nullable=False)
    status = Column(String(24), nullable=False, default="assigned")
    previous = Column(String(24))
    deadline = Column(String(10), nullable=False)
    major = Column(Boolean, nullable=False, default=False)
    brief = Column(Text, nullable=False, default="")
    draft = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=0)
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": revision}

class Member(Base):
    __tablename__ = "wf_member"
    task = Column(ID, ForeignKey("wf_task.id"), primary_key=True)
    user = Column(ID, ForeignKey("sys_user.id"), primary_key=True)

class History(Base):
    __tablename__ = "wf_audit"
    id = Column(ID, primary_key=True)
    task = Column(ID, ForeignKey("wf_task.id"), nullable=False, index=True)
    actor = Column(ID, ForeignKey("sys_user.id"), nullable=False)
    action = Column(String(32), nullable=False)
    version = Column(Integer, nullable=False)
    at = Column(DateTime, nullable=False, default=now)
    note = Column(Text, nullable=False, default="")
    snapshot = Column(JSON)

class Project(Base):
    __tablename__ = "rd_project"
    id = Column(ID, primary_key=True)
    order_id = Column(ID, ForeignKey("biz_order.id"), nullable=False)
    customer = Column(ID, ForeignKey("biz_customer.id"), nullable=False, index=True)
    task = Column(ID, ForeignKey("wf_task.id"), nullable=False)
    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    budget = Column(Numeric(18,2), nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint("customer","code"),)

class Entry(Base):
    __tablename__ = "wf_workpaper"
    id = Column(ID, primary_key=True)
    task = Column(ID, ForeignKey("wf_task.id"), nullable=False, index=True)
    project = Column(ID, ForeignKey("rd_project.id"), index=True)
    kind = Column(String(32), nullable=False, index=True)
    key = Column(String(120), nullable=False)
    state = Column(String(32), nullable=False, default="draft")
    payload = Column(JSON, nullable=False)
    actor = Column(ID, ForeignKey("sys_user.id"), nullable=False)
    at = Column(DateTime, nullable=False, default=now)
    revision = Column(Integer, nullable=False, default=1)
    __table_args__ = (UniqueConstraint("task","kind","key"),)
    __mapper_args__ = {"version_id_col": revision}

class FileObject(Base):
    __tablename__ = "doc_material"
    id = Column(ID, primary_key=True)
    task = Column(ID, ForeignKey("wf_task.id"), nullable=False, index=True)
    project = Column(ID, ForeignKey("rd_project.id"))
    category = Column(String(64), nullable=False)
    name = Column(String(160), nullable=False)
    storage = Column(String(160), nullable=False, unique=True)
    digest = Column(String(64), nullable=False)
    size = Column(Integer, nullable=False)
    previous = Column(ID, ForeignKey("doc_material.id"))
    actor = Column(ID, ForeignKey("sys_user.id"), nullable=False)
    at = Column(DateTime, nullable=False, default=now)
    __table_args__ = (UniqueConstraint("previous"),)

def get_db():
    with Session() as db:
        yield db

def secret():
    value = os.getenv("JWT_SECRET")
    if value and len(value.encode()) >= 32:
        return value
    if value or not URL.startswith("sqlite"):
        raise RuntimeError("Configure JWT_SECRET with at least 32 bytes")
    keyfile = DATA / ".session-key"
    try:
        with keyfile.open("x", encoding="ascii") as stream:
            stream.write(secrets.token_hex(48))
    except FileExistsError:
        pass
    return keyfile.read_text(encoding="ascii").strip()
