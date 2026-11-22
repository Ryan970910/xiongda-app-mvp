#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv .local/trial-venv
.local/trial-venv/bin/python -m pip install -r platform/requirements.txt
npm ci --prefix platform/web
npm run build --prefix platform/web
