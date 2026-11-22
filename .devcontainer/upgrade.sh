#!/usr/bin/env bash
# Run from the updated checkout in the existing GitHub trial.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
root=$PWD
data="$root/.local/shared-trial"
exec 8>"$data/upgrade.lock"
flock -n 8 || { echo "已有更新正在进行"; exit 1; }
stamp="$(date -u +%Y%m%dT%H%M%S)-$$"
stage="$root/.local/release-$stamp"
mkdir "$stage"
"$root/.local/trial-venv/bin/python" platform/backup_trial.py "$data" "$root/.local/backups/$stamp"
npm run build --prefix platform/web -- --outDir "$stage/dist"
test -s "$stage/dist/index.html"
if [[ -s "$data/service.pid" ]]; then
  pid=$(cat "$data/service.pid")
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    test "$(readlink -f "/proc/$pid/cwd")" = "$root/platform"
    tr '\0' ' ' <"/proc/$pid/cmdline" | grep -Fq -- '-m uvicorn service.main:app --host 0.0.0.0 --port 8000'
    kill -TERM "$pid"
    for _ in {1..30}; do
      if ! curl -fsS --max-time 1 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then break; fi
      sleep 1
    done
  fi
fi
mv platform/web/dist "$stage/previous-dist"
mv "$stage/dist" platform/web/dist
bash .devcontainer/start.sh
curl -fsS http://127.0.0.1:8000/api/openapi.json | "$root/.local/trial-venv/bin/python" -c 'import json,sys; assert "/api/v1/consultations/assigned" in json.load(sys.stdin)["paths"]'
git rev-parse HEAD >"$data/release"
echo "已就绪，已保留本次更新前的数据库与附件备份。"
