"""Assemble an offline Windows x64 workstation from a Windows CPython installation."""
from argparse import ArgumentParser
from pathlib import Path
import shutil
import sys
import zipfile

def build(std,packages,out):
    src=Path(__file__).resolve().parent
    if out.exists():raise SystemExit("请指定新的输出目录，避免覆盖验收数据。")
    dest=out/"科研财税协同";py=dest/"python";py.mkdir(parents=True)
    for name in ["python.exe","python3.dll","LICENSE.txt","vcruntime140.dll","vcruntime140_1.dll",f"python{sys.version_info.major}{sys.version_info.minor}.dll"]:
        shutil.copy2(std/name,py/name)
    skip=shutil.ignore_patterns("__pycache__","*.pyc","*.pdb","*.lib","*.exp","test","tests","site-packages","idlelib","tkinter","turtledemo","ensurepip")
    shutil.copytree(std/"Lib",py/"Lib",ignore=skip)
    shutil.copytree(std/"DLLs",py/"DLLs",ignore=skip)
    target=py/"Lib"/"site-packages";target.mkdir()
    keep={"fastapi","starlette","pydantic","pydantic_core","sqlalchemy","greenlet","anyio","uvicorn","jwt","python_multipart","multipart","docx","lxml","openpyxl","et_xmlfile","typing_extensions","typing_inspection","annotated_types","annotated_doc","opentelemetry","idna","click","h11","tzdata","packaging","colorama"}
    for item in packages.iterdir():
        stem=item.name.split("-")[0] if item.name.endswith(".dist-info") else item.stem
        if stem.lower() not in keep|{"pyjwt","python_docx","opentelemetry_api"}:continue
        if item.is_dir():shutil.copytree(item,target/item.name,ignore=skip)
        else:shutil.copy2(item,target/item.name)
    shutil.copytree(src/"service",dest/"service",ignore=skip)
    shutil.copytree(src/"web"/"dist",dest/"web"/"dist")
    shutil.copy2(src/"start.py",dest/"start.py")
    shutil.copy2(src/"office.py",dest/"office.py")
    shutil.copy2(src/"backup_trial.py",dest/"backup_trial.py")
    shutil.copy2(src/"交付与培训.md",dest/"交付与培训.txt")
    shutil.copy2(src/"试办测试报告.md",dest/"试办测试报告.txt")
    shutil.copy2(src/"使用说明.md",dest/"使用说明.txt")
    shutil.copy2(src/"验收范围.md",dest/"验收范围.txt")
    (dest/"双击启动.cmd").write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\nset "PYTHONUTF8=1"\r\nset "PYTHONDONTWRITEBYTECODE=1"\r\nset "PYTHONPATH="\r\nset "PYTHONHOME="\r\n"python\\python.exe" -E -X utf8 -B start.py\r\nif errorlevel 1 pause\r\n')
    (dest/"办公室联机.cmd").write_bytes((dest/"双击启动.cmd").read_bytes().replace(b"start.py",b"office.py"))
    archive=out/"research-finance-windows-x64.zip"
    with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for f in dest.rglob("*"):
            if f.is_file():z.write(f,f.relative_to(out))
    print(archive,flush=True)

if __name__=="__main__":
    p=ArgumentParser();p.add_argument("output",type=Path);p.add_argument("--packages",type=Path,required=True)
    args=p.parse_args();build(Path(sys.base_prefix),args.packages.resolve(),args.output.resolve())
