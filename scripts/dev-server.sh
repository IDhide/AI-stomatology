#!/usr/bin/env bash
# Dev-сервер для превью Kimi Work: поднимает FastAPI-бэкенд (киоск + стенд
# /voice-test) и пробрасывает host/port, которые передаёт превью-раннер.
set -euo pipefail

cd "$(dirname "$0")/.."   # корень репозитория

if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi

if [ -f server/.env ]; then
  set -a; . server/.env; set +a
fi

# пробрасываем аргументы (--host/--port) дальше в uvicorn;
# если порт не передали — берём $PORT, иначе 8000
args=("$@")
has_port=0
for a in ${args[@]+"${args[@]}"}; do
  [ "$a" = "--port" ] && has_port=1
done
if [ "$has_port" -eq 0 ]; then
  args+=(--port "${PORT:-8000}")
fi

exec uvicorn server.app.main:app --host 0.0.0.0 --reload "${args[@]}"
