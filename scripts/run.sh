#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  run.sh — удобный запуск Smile.AI
#
#  Использование:
#    bash scripts/run.sh               # оффлайн-демо (CPU, без камеры)
#    bash scripts/run.sh offline       # то же
#    bash scripts/run.sh prod          # production (нужны все сервисы)
#    bash scripts/run.sh test-ui       # только UI
#    bash scripts/run.sh docker        # через docker compose (CPU)
#    bash scripts/run.sh docker-gpu    # через docker compose (GPU)
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}") /.." && pwd)"
cd "$PROJECT_DIR"

MODE="${1:-offline}"

# Активируем venv если запущено не из него
if [ -d ".venv" ] && [ -z "${VIRTUAL_ENV:-}" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

_check_ollama() {
    if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "⚠  Ollama не запущен. Запустите: ollama serve"
        echo "   Или используйте оффлайн-режим: bash scripts/run.sh offline"
        exit 1
    fi
    echo "✓ Ollama доступен"
}

case "$MODE" in
    offline)
        echo "▶ Запуск оффлайн-демо (без камеры)…"
        python -m src.main_offline --no-camera
        ;;
    offline-sim)
        echo "▶ Запуск с симуляцией голоса (вводите текст в терминале)…"
        python -m src.main_offline --no-camera --simulate-voice
        ;;
    offline-window)
        echo "▶ Запуск в оконном режиме…"
        python -m src.main_offline --no-camera --windowed
        ;;
    prod)
        _check_ollama
        echo "▶ Запуск production…"
        python -m src.main
        ;;
    test-ui)
        echo "▶ Тест UI…"
        python scripts/test_ui.py
        ;;
    docker)
        echo "▶ Запуск через Docker (CPU)…"
        docker compose up --build
        ;;
    docker-gpu)
        echo "▶ Запуск через Docker (GPU)…"
        docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
        ;;
    docker-down)
        echo "▶ Остановка Docker…"
        docker compose down
        ;;
    *)
        echo "Использование: $0 [offline|offline-sim|offline-window|prod|test-ui|docker|docker-gpu|docker-down]"
        exit 1
        ;;
esac
