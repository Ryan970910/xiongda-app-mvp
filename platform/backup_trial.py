"""Back up a running SQLite trial into a new, offline directory."""
import argparse
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile


def backup(source, target):
    source, target = source.resolve(), target.resolve()
    if target.exists() or target.is_relative_to(source):
        raise ValueError("请指定运行数据目录以外、尚未存在的备份目录")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        staging = Path(tmp) / "backup"
        objects = staging / "objects"
        objects.mkdir(parents=True)
        live = sqlite3.connect((source / "workspace.db").as_uri() + "?mode=ro", uri=True)
        snapshot = sqlite3.connect(staging / "workspace.db")
        try:
            live.backup(snapshot)
            if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("数据库备份校验失败")
            snapshot.execute("PRAGMA foreign_keys=ON")
            snapshot.execute("DELETE FROM sys_session")
            snapshot.commit()
            files = "SELECT storage,digest FROM doc_material UNION SELECT storage,digest FROM biz_customer_file"
            if snapshot.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='policy_template_file'").fetchone():
                files += " UNION SELECT storage,digest FROM policy_template_file"
            rows = snapshot.execute(files)
            for key, digest in rows:
                if Path(key).name != key or key in {".", ".."}:
                    raise ValueError("无效的附件索引")
                dest = objects / key
                shutil.copyfile(source / "objects" / key, dest)
                with dest.open("rb") as f:
                    if hashlib.file_digest(f, "sha256").hexdigest() != digest:
                        raise ValueError("附件校验失败，本次备份未交付")
        finally:
            live.close()
            snapshot.close()
        staging.rename(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    backup(args.source, args.target)
