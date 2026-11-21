"""Start this private workstation and open it in the default browser."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from urllib.request import urlopen
import webbrowser

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
data=Path(os.getenv("WORKSPACE_DATA",ROOT/"runtime")).resolve()
data.mkdir(parents=True,exist_ok=True)
os.environ["WORKSPACE_DATA"]=str(data)
os.environ["TMP"]=os.environ["TEMP"]=str(data)
os.environ["ACCEPTANCE_TICKET"]=secrets.token_urlsafe(36)
os.environ.pop("DATABASE_URL",None)
os.environ.pop("S3_BUCKET",None)
os.environ.pop("OFFICE_MODE",None)

def start():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=18765)
    parser.add_argument("--no-browser",action="store_true")
    args=parser.parse_args()
    if not (ROOT/"web"/"dist"/"index.html").is_file():raise SystemExit("请使用已解压的本机验收包。源码运行请先编译网页。")
    import uvicorn
    from service.main import app
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=["127.0.0.1","localhost"])
    port=args.port
    here=f"http://127.0.0.1:{port}"
    state=data/".launch"
    with socket.socket() as sock:
        try:sock.bind(("127.0.0.1",port))
        except OSError:
            try:
                with urlopen(here+"/api/v1/local/status",timeout=2) as r:state_info=json.load(r)["data"]
                if not isinstance(state_info.get("accounts"),list):raise ValueError
                if state_info["setup"]:here+="/#first/"+state.read_text(encoding="ascii")
            except Exception:raise SystemExit("启动端口已被占用。请关闭旧窗口，或使用其他端口。")
            if not args.no_browser:webbrowser.open(here)
            return
    state.write_text(os.environ["ACCEPTANCE_TICKET"],encoding="ascii")
    def ready():
        for _ in range(150):
            try:
                with urlopen(here+"/api/v1/local/status",timeout=1) as r:needs=json.load(r)["data"]["setup"]
                break
            except OSError:time.sleep(.2)
        else:return
        dest=here+("/#first/"+os.environ["ACCEPTANCE_TICKET"] if needs else "")
        print("请在本机浏览器打开 "+dest,flush=True)
        if not args.no_browser:webbrowser.open(dest)
    threading.Thread(target=ready,daemon=True).start()
    print("科研财税协同已启动。使用期间请保持此窗口打开。",flush=True)
    uvicorn.run(app,host="127.0.0.1",port=port,access_log=False,log_level="warning")

if __name__=="__main__":start()
