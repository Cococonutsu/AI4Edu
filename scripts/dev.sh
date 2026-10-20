#!/usr/bin/env bash
# 同时启动后端（8000，代码与 config/ 改动自动重载）与前端（5173）。Ctrl+C 一起停止。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 端口被占用时直接说明是谁占着，而不是让一半服务起不来。
for port in 8000 5173; do
  if pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1)" && [ -n "$pid" ]; then
    echo "端口 $port 已被占用（进程 $pid：$(ps -o command= -p "$pid" | cut -c1-80)）。" >&2
    echo "先停掉它再启动：kill $pid" >&2
    exit 1
  fi
done

# 除了 Python 源码，config/ 下的 YAML（判据、阈值、提醒文字）改动也要重载。
(cd "$ROOT/backend" && uv run uvicorn ai4edu.server.app:app --port 8000 \
  --reload --reload-dir "$ROOT/backend/src" --reload-dir "$ROOT/config" \
  --reload-include '*.yaml') &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd "$ROOT/frontend" && npm run dev
