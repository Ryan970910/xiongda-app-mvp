#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
export WORKSPACE_DATA="$PWD/.local/shared-trial"
export RD_SHARED_TRIAL=1 OFFICE_MODE=1
unset DATABASE_URL S3_BUCKET ACCEPTANCE_TICKET JWT_SECRET
mkdir -p "$WORKSPACE_DATA"
python="$PWD/.local/trial-venv/bin/python"
test -s platform/web/dist/index.html
cd platform
exec 9>"$WORKSPACE_DATA/start.lock"
flock 9
pid_file="$WORKSPACE_DATA/service.pid"
health=http://127.0.0.1:8000/api/health
if [[ -s "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null && curl -fsS "$health" >/dev/null; then
  exit 0
fi
"$python" -m service.trial
nohup "$python" -m uvicorn service.main:app --host 0.0.0.0 --port 8000 --no-access-log \
  </dev/null >>"$WORKSPACE_DATA/service.log" 2>&1 9>&- &
pid=$!
echo "$pid" > "$pid_file"
for attempt in {1..30}; do
  kill -0 "$pid" 2>/dev/null || break
  if curl -fs "$health" >/dev/null; then
    echo "试办工作台已就绪。首次分配的账号保存在 .local/shared-trial/initial-accounts.tsv"
    exit 0
  fi
  sleep 1
done
echo "工作台启动失败，请查看 .local/shared-trial/service.log" >&2
exit 1
