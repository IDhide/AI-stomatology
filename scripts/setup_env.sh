#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  setup_env.sh — настройка окружения через uv
#
#  Что делает:
#    1. Устанавливает uv (если нет)
#    2. Создаёт .venv с Python 3.11
#    3. Устанавливает зависимости
#    4. Копирует .env.example → .env (если нет)
#    5. Создаёт нужные директории
#    6. Health-check окружения
#
#  Использование:
#    bash scripts/setup_env.sh           # CPU (для разработки)
#    bash scripts/setup_env.sh gpu       # CUDA 12.1 (RTX 3060)
#    bash scripts/setup_env.sh dev       # + ruff/pytest
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}") /.." && pwd)"
cd "$PROJECT_DIR"

VARIANT="${1:-cpu}"

echo "═══════════════════════════════════════════"
echo "  Smile.AI — настройка окружения"
echo "  Проект:  $PROJECT_DIR"
echo "  Вариант: $VARIANT"
echo "═══════════════════════════════════════════"

# ─── 1. uv ────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
    echo "▶ Устанавливаю uv…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
echo "▶ uv $(uv --version)"

# ─── 2. Python ────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 не найден. Установите Python 3.11:"
    echo "   sudo apt install -y python3.11 python3.11-venv"
    exit 1
fi

# ─── 3. Системные библиотеки (Debian/Ubuntu) ──────────────────────
if command -v apt-get >/dev/null 2>&1; then
    echo "▶ Проверяю системные зависимости…"
    MISSING_PKGS=()
    for pkg in ffmpeg libportaudio2 libsndfile1 libgl1 libglib2.0-0; do
        dpkg -l "$pkg" &>/dev/null || MISSING_PKGS+=("$pkg")
    done
    if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
        echo "  Устанавливаю: ${MISSING_PKGS[*]}"
        sudo apt-get install -y "${MISSING_PKGS[@]}"
    else
        echo "  ✓ Все системные зависимости установлены"
    fi
fi

# ─── 4. Виртуальное окружение ─────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "▶ Создаю .venv (python 3.11)…"
    uv venv --python 3.11
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "▶ Python: $(python --version)"

# ─── 5. Зависимости ───────────────────────────────────────────────
case "$VARIANT" in
    gpu)
        echo "▶ Устанавливаю зависимости (GPU, CUDA 12.1)…"
        uv pip install \
            --extra-index-url https://download.pytorch.org/whl/cu121 \
            -e ".[gpu]"
        ;;
    cpu)
        echo "▶ Устанавливаю зависимости (CPU)…"
        uv pip install -e ".[cpu]"
        ;;
    dev)
        echo "▶ Устанавливаю dev-зависимости…"
        uv pip install -e ".[cpu,dev]"
        ;;
    *)
        echo "❌ Неизвестный вариант: $VARIANT (gpu|cpu|dev)"; exit 1 ;;
esac

# ─── 6. .env ──────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "▶ Создаю .env из .env.example…"
    cp .env.example .env
    echo "  ⚠  Заполните .env своими значениями!"
fi

# ─── 7. Директории ────────────────────────────────────────────────
echo "▶ Создаю рабочие директории…"
mkdir -p data/logs assets/videos

# ─── 8. Health-check ──────────────────────────────────────────────
echo ""
echo "▶ Health-check…"
python - <<'PY'
import sys

required = [
    ("loguru",       "loguru"),
    ("yaml",         "PyYAML"),
    ("pydantic",     "pydantic"),
    ("dotenv",       "python-dotenv"),
    ("requests",     "requests"),
    ("aiohttp",      "aiohttp"),
    ("num2words",    "num2words"),
    ("numpy",        "numpy"),
    ("sounddevice",  "sounddevice"),
    ("soundfile",    "soundfile"),
    ("pygame",       "pygame"),
    ("cv2",          "opencv-python"),
]
optional = [
    ("torch",          "torch"),
    ("faster_whisper", "faster-whisper"),
    ("mediapipe",      "mediapipe"),
    ("omegaconf",      "omegaconf"),
]

failed = []
print("  Обязательные:")
for mod, pkg in required:
    try:
        __import__(mod)
        print(f"    ✓ {pkg}")
    except ImportError as e:
        failed.append(f"{pkg}: {e}")
        print(f"    ✗ {pkg}")

print("  Опциональные:")
for mod, pkg in optional:
    try:
        __import__(mod)
        print(f"    ✓ {pkg}")
    except ImportError:
        print(f"    · {pkg} (не установлен)")

try:
    import torch
    cuda_ok = torch.cuda.is_available()
    print(f"\n  CUDA: {'✓ ' + torch.cuda.get_device_name(0) if cuda_ok else '· недоступна (CPU-режим)'}")
except Exception:
    pass

if failed:
    print(f"\n❌ Не хватает: {'; '.join(failed)}")
    sys.exit(1)

print("\n✅ Окружение готово!")
PY

cat <<EOF

═══════════════════════════════════════════════════
  Готово! Команды запуска:

  Активация окружения:
    source .venv/bin/activate

  Оффлайн-демо (без DIKIDI, без камеры):
    python -m src.main_offline --no-camera

  Оффлайн-демо (с симуляцией голоса из stdin):
    python -m src.main_offline --no-camera --simulate-voice

  Production:
    python -m src.main

  Ollama-модель (после запуска Ollama):
    bash scripts/setup_ollama_dental.sh
═══════════════════════════════════════════════════
EOF
