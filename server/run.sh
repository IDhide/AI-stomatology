#!/usr/bin/env bash
# Запуск серверного backend'а для локального теста (MacBook).
#   ./server/run.sh
# Открой http://localhost:8000 в Chrome и нажми «Запустить киоск».
set -euo pipefail

cd "$(dirname "$0")/.."   # корень репозитория (чтобы читался config/prompts.yaml)

# Автоактивация виртуального окружения — не нужно помнить про source
if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi

if ! command -v uvicorn >/dev/null 2>&1; then
  echo "❌ uvicorn не найден. Установите зависимости:"
  echo "   python3 -m venv .venv && source .venv/bin/activate"
  echo "   pip install -r server/requirements.txt"
  exit 1
fi

# .env берётся из server/.env (см. server/.env.example)
if [ -f server/.env ]; then
  set -a; . server/.env; set +a
fi

exec uvicorn server.app.main:app --host 0.0.0.0 --port 8000 --reload
