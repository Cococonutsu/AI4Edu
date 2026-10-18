#!/usr/bin/env bash
# 同时启动后端（8000）与前端（5173）。Ctrl+C 一起停止。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$ROOT/backend" && uv run uvicorn ai4edu.server.app:app --reload --port 8000) &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd "$ROOT/frontend" && npm run dev
