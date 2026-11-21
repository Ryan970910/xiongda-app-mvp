"""Serve the already initialized workstation over an approved private HTTPS address."""
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))

def main():
    config=BASE/"办公室配置.json"
    if not config.exists():
        raise SystemExit("请先单机验收，再请单位负责网络的同事按《办公室联机》准备办公室配置.json。")
    d=json.loads(config.read_text(encoding="utf-8-sig"))
    addr=ipaddress.IPv4Address(d["内网地址"])
    ranges=[ipaddress.ip_network(n) for n in ["10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"]]
    if not any(addr in n for n in ranges):raise SystemExit("请选择本机办公室专用网卡的内网地址")
    dns=d["内网主机名"].strip().lower()
    if not dns or "*" in dns or "/" in dns:raise SystemExit("请提供内网证书所对应的确切主机名")
    cert=(BASE/d["证书文件"]).resolve();key=(BASE/d["私钥文件"]).resolve()
    if not cert.is_file() or not key.is_file():raise SystemExit("未找到单位配置的 HTTPS 证书或私钥")
    data=Path(os.getenv("WORKSPACE_DATA",BASE/"runtime")).resolve()
    if not (data/"workspace.db").is_file():raise SystemExit("请先用双击启动建立本机验收案例")
    os.environ.update(WORKSPACE_DATA=str(data),TMP=str(data),TEMP=str(data),OFFICE_MODE="1")
    for name in ["DATABASE_URL","S3_BUCKET","ACCEPTANCE_TICKET"]:os.environ.pop(name,None)
    from service.db import Session, User
    from sqlalchemy import select
    with Session() as db:
        users=db.scalars(select(User).where(User.enabled.is_(True)))
        if len([u for u in users if not u.employee_no.startswith("LOCAL-")])<2:
            raise SystemExit("请先以本机管理员身份为两位同事各开一个个人测试账号。")
    from service.main import app
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import PlainTextResponse
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=[dns,str(addr)])
    @app.middleware("http")
    async def private_only(req,call_next):
        client=ipaddress.ip_address(req.client.host)
        if not any(client in net for net in ranges):return PlainTextResponse("仅限单位专网访问",403)
        return await call_next(req)
    port=int(d.get("端口",18766))
    print(f"请同事在单位网络打开 https://{dns}:{port} ，使用各自账号。",flush=True)
    import uvicorn
    uvicorn.run(app,host=str(addr),port=port,ssl_certfile=str(cert),ssl_keyfile=str(key),proxy_headers=False,access_log=False)

if __name__=="__main__":main()
