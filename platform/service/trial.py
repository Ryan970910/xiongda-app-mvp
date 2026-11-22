"""Initialize private, per-person credentials for one shared trial workspace."""
import csv
import os
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select, text

from .db import Audit, DATA, Session, User, engine
from .local import ACCOUNTS, seed_example
from .main import initialize


def initialize_trial():
    if os.getenv("RD_SHARED_TRIAL") != "1" or engine.dialect.name != "sqlite":
        raise RuntimeError("请在共享试办启动环境中运行")
    initialize()
    with Session.begin() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        if db.scalar(select(User.id).limit(1)):
            return
        passwords = {name: secrets.token_urlsafe(21) + "9a" for name, *_ in ACCOUNTS}
        people = seed_example(db, passwords, shared=True)
        db.add(Audit(user_id=people["admin"].id, action="trial.initialize",
                     subject="fictional-workspace", details={}, ip="", agent="codespace"))
        db.flush()
        # Publish credentials before committing. An interrupted empty database can be seeded again.
        with TemporaryDirectory(dir=DATA) as temp:
            temp_path = Path(temp) / "initial-accounts.tsv"
            with temp_path.open("x", newline="", encoding="utf-8-sig") as sheet:
                temp_path.chmod(0o600)
                writer = csv.writer(sheet, delimiter="\t")
                writer.writerow(["岗位", "账号", "首次登录密码"])
                for name, label, *_ in ACCOUNTS:
                    writer.writerow([label, name, passwords[name]])
                sheet.flush()
                os.fsync(sheet.fileno())
            temp_path.replace(DATA / "initial-accounts.tsv")


if __name__ == "__main__":
    initialize_trial()
