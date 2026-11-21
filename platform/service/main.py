from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from . import auth, workflow
from .db import Audit, Base, Department, Session, engine

def initialize():
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        if not db.query(Department).count():
            db.add_all([Department(name="系统管理",line="function"),Department(name="科研咨询",line="research"),Department(name="财务咨询",line="finance")])

@asynccontextmanager
async def startup(app):
    initialize()
    yield

app=FastAPI(title="科研财税协同内部服务",version="1.0.0",lifespan=startup,docs_url="/api/docs",redoc_url=None,openapi_url="/api/openapi.json")
app.include_router(auth.router,prefix="/api/v1")
app.include_router(workflow.router,prefix="/api/v1")

def problem(status,message):
    return JSONResponse(status_code=status,content={"code":status,"message":message,"data":None})

@app.exception_handler(HTTPException)
async def http_error(request:Request,exc:HTTPException):
    return problem(exc.status_code,exc.detail)

@app.exception_handler(RequestValidationError)
async def validation(request:Request,exc:RequestValidationError):
    # Validation errors may contain raw password input. Return only field paths and messages.
    issues=[{"field":".".join(map(str,e["loc"])),"message":e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422,content={"code":422,"message":"字段校验失败","data":issues})

@app.exception_handler(IntegrityError)
async def conflict(request:Request,exc:IntegrityError):
    return problem(409,"编号或版本冲突，请核对最新记录")

@app.exception_handler(StaleDataError)
async def stale(request:Request,exc:StaleDataError):
    return problem(409,"数据已更新，请刷新并重试")

@app.middleware("http")
async def access_log(request:Request,call_next):
    response=await call_next(request)
    if request.url.path.startswith("/api/v1/"):
        with Session.begin() as db:
            db.add(Audit(user_id=getattr(request.state,"user",None),action="http."+request.method,
                         subject=request.url.path[:160],details={"status":response.status_code},ip=request.client.host if request.client else "",
                         agent=request.headers.get("user-agent","")[:240]))
        response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="same-origin"
    return response

@app.get("/api/health")
def health():
    from sqlalchemy import text
    with engine.connect() as c: c.execute(text("SELECT 1"))
    return {"status":"ok"}

def mount_frontend():
    dist=Path(__file__).resolve().parents[1]/"web"/"dist"
    if dist.is_dir():app.mount("/",StaticFiles(directory=dist,html=True),name="www")
