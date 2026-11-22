# 科研财税协同本机验收版

Windows 用户请读 [使用说明](使用说明.md) 和 [验收范围](验收范围.md)。首次设置由本机启动器打开，不使用固定默认密码。可分享给同事的单位内部地址由办公室网络管理员配置；真实业务数据不进入 GitHub。

## 在 GitHub 约同事试办

从仓库主页进入 **Code → Codespaces**，选择已有的试办环境。第一次创建时使用 main 分支和 2 核机型。等启动窗口出现“试办工作台已就绪”，在下方 **Ports** 找到 8000，将 **Port Visibility** 设置为 **Public**，复制这一行的网页地址发给同事。只有这个端口需要对外开放。

在左侧文件栏打开 `.local/shared-trial/initial-accounts.tsv`。每个岗位有独立的首次登录密码，给每位同事单独发送对应的一行，管理员账号由负责人保管。首次登录后按网页提示改密，再用新密码登录。试办只使用虚构资料。

可先让科研承办在“我的待办”打开“青禾温控试验 · 确认立项清单”并确认接件，再让派单经理刷新同一任务查看“办理中”。数据保存在这个 Codespace。休眠后，负责人在[自己的 Codespaces](https://github.com/codespaces) 打开原来的环境，等服务就绪，在 **Ports** 重新将 **8000 → Port Visibility** 设为 **Public**，同事就能继续使用原链接。删除环境会一并删除试办资料。

## 从源码运行

使用可运行本仓库 Python 依赖的 Windows x64 Python 3.11 或 3.12、Node 22。在项目根目录使用 PowerShell。

```powershell
python -m venv .local/accept-venv
.local/accept-venv/Scripts/python.exe -m pip install -r platform/requirements.txt --cache-dir .local/pip-cache
npm.cmd ci --prefix platform/web --cache .local/npm-cache
npm.cmd run build --prefix platform/web
.local/accept-venv/Scripts/python.exe platform/start.py
```

浏览器工作台和业务接口来自同一本地进程。接口说明在运行中的 `/api/docs`。本机数据在 `platform/runtime`，也可通过 `WORKSPACE_DATA` 指向独立磁盘目录。默认端口 18765。办公室 HTTPS 入口使用 `platform/office.py`，配置步骤见操作手册。公开 Pages 仅承载浏览器演示及准备问答。

## 验证

```powershell
.local/accept-venv/Scripts/python.exe platform/tests/acceptance.py
.local/accept-venv/Scripts/python.exe -c "import sys,runpy;sys.path.insert(0,'platform');runpy.run_path('platform/tests/annual.py',run_name='__main__')"
.local/accept-venv/Scripts/python.exe platform/tests/volume.py
```

验收测试主动使用临时数据库。可将 TMP 和 TEMP 指向 D 盘现有的临时目录。`package_local.py` 把 Windows CPython 的运行文件、所需库、业务服务及已编译网页打进一个离线包，输出到新的目录。构建输入只从明确列出的文件选取。压缩包不含本机用户、业务数据库、附件、证书、私钥或内部说明书。
