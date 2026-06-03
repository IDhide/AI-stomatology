#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  setup_ollama_dental.sh
#  Поднимает Ollama, скачивает Qwen2.5-7B (q4_K_M) и собирает
#  кастомную модель smile-ru из Modelfile.
#
#  Использование:
#      bash scripts/setup_ollama_dental.sh
#
#  Требования: ~6 GB места на диске, ~6 GB VRAM (3060 12GB — с запасом).
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELFILE="${SCRIPT_DIR}/Modelfile"
MODEL_NAME="smile-ru"
BASE_MODEL="qwen2.5:7b-instruct-q4_K_M"

echo "▶ Проверяю наличие Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
    echo "  Ollama не найдена — устанавливаю (Linux/macOS)..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

echo "▶ Запускаю сервис Ollama в фоне (если не запущен)..."
if ! pgrep -x ollama >/dev/null 2>&1; then
    ollama serve >/tmp/ollama.log 2>&1 &
    sleep 3
fi

echo "▶ Проверяю доступность API..."
for i in 1 2 3 4 5; do
    if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
        break
    fi
    echo "  попытка $i..."
    sleep 2
done

echo "▶ Скачиваю базовую модель: ${BASE_MODEL}"
ollama pull "${BASE_MODEL}"

echo "▶ Собираю кастомную модель: ${MODEL_NAME}"
ollama create "${MODEL_NAME}" -f "${MODELFILE}"

echo "▶ Проверка: 'smile-ru' отвечает?"
RESP=$(ollama run "${MODEL_NAME}" "Здравствуйте" --verbose 2>&1 | head -n 5 || true)
echo "${RESP}"

cat <<EOF

────────────────────────────────────────────────────────
✅ Готово.
   Базовая модель:    ${BASE_MODEL}
   Кастомная модель:  ${MODEL_NAME}

Проверь вручную:
   ollama run ${MODEL_NAME} "Сколько стоит чистка зубов?"

Поменять промпт / температуру:
   1. отредактируй scripts/Modelfile
   2. ollama create ${MODEL_NAME} -f scripts/Modelfile
────────────────────────────────────────────────────────
EOF
