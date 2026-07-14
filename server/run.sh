#!/usr/bin/env bash
# Запуск серверного backend'а для локального теста (MacBook).
#   ./server/run.sh
# Открой http://localhost:8000 в Chrome и нажми «Запустить киоск».
set -euo pipefail

cd "$(dirname "$0")/.."   # корень репозитория (чтобы читался config/prompts.yaml)

# .env берётся из server/.env (см. server/.env.example)
if [ -f server/.env ]; then
  set -a; . server/.env; set +a
fi

exec uvicorn server.app.main:app --host 0.0.0.0 --port 8000 --reload
