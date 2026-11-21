import argparse
import getpass
import secrets
from sqlalchemy import select
from .auth import set_password
from .db import Department, Session, User
from .main import initialize

def provision(username,name,password):
    initialize()
    with Session.begin() as db:
        if db.scalar(select(User.id).limit(1)):
            raise ValueError("已有账号；初始化不覆盖现有数据")
        dept=db.scalar(select(Department).where(Department.line=="function"))
        u=User(username=username.strip().lower(),employee_no="SYS-001",name=name,department=dept.id,team="系统管理",
               roles=[{"role":"admin","expires":None}],enabled=True)
        set_password(u,password,True);db.add(u)

if __name__=="__main__":
    p=argparse.ArgumentParser(description="初始化内部系统管理员")
    p.add_argument("--username",default="admin")
    p.add_argument("--name",default="系统管理员")
    args=p.parse_args()
    pwd=getpass.getpass("设置管理员临时密码：")
    if pwd!=getpass.getpass("再次输入："):raise SystemExit("两次输入不一致")
    provision(args.username,args.name,pwd)
    print("管理员已建立，首次登录请修改密码。")
