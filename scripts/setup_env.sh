#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  setup_env.sh — поднимает виртуальное окружение через uv.
#
#  Что делает:
#    1. Ставит uv, если его нет.
#    2. Создаёт .venv с Python 3.11.
#    3. Ставит зависимости (CUDA-сборка torch для Linux+NVIDIA по умолчанию).
#    4. Проверяет ключевые библиотеки.
#
#  Использование:
#       bash scripts/setup_env.sh           # CUDA-сборка (по умолч.)
#       bash scripts/setup_env.sh cpu       # без GPU
#       bash scripts/setup_env.sh dev       # +ruff/pytest
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

VARIANT="${1:-gpu}"          # gpu | cpu | dev

echo "▶ Проект:   $PROJECT_DIR"
echo "▶ Вариант:  $VARIANT"

# ─── 1. uv ────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
    echo "▶ Устанавливаю uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1090
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
echo "▶ uv $(uv --version)"

# ─── 2. виртуальное окружение ─────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "▶ Создаю .venv (python 3.11)..."
    uv venv --python 3.11
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ─── 3. зависимости ───────────────────────────────────────────────
case "$VARIANT" in
    gpu)
        echo "▶ Ставлю проект + CUDA-сборку torch (cu121)..."
        # torch для CUDA 12.1 идёт с отдельного индекса
        uv pip install \
            --extra-index-url https://download.pytorch.org/whl/cu121 \
            -e ".[gpu]"
        ;;
    cpu)
        echo "▶ Ставлю проект (CPU-сборка)..."
        uv pip install -e ".[cpu]"
        ;;
    dev)
        echo "▶ Ставлю dev-зависимости (без torch)..."
        uv pip install -e ".[dev]"
        ;;
    *)
        echo "Неизвестный вариант: $VARIANT"; exit 1 ;;
esac

# ─── 4. ffmpeg / portaudio: проверим, без них soundfile/cv2 могут жаловаться
echo "▶ Проверяю системные библиотеки..."
for bin in ffmpeg; do
    if ! command -v $bin >/dev/null 2>&1; then
        echo "  ⚠ $bin не найден — поставьте: sudo apt install -y $bin libportaudio2 libsndfile1"
    fi
done

# ─── 5. health-check ──────────────────────────────────────────────
echo "▶ Health-check..."
python - <<'PY'
import sys
checks = [
    ("loguru", "loguru"),
    ("yaml", "PyYAML"),
    ("pygame", "pygame"),
    ("cv2", "opencv-python"),
    ("numpy", "numpy"),
    ("sounddevice", "sounddevice"),
    ("num2words", "num2words"),
]
opt = [
    ("torch", "torch"),
    ("faster_whisper", "faster-whisper"),
    ("mediapipe", "mediapipe"),
]
miss = []
for mod, pkg in checks:
    try:
        __import__(mod)
        print(f"  ✓ {pkg}")
    except Exception as e:
        miss.append(f"{pkg}: {e}")
        print(f"  ✗ {pkg}")

print()
for mod, pkg in opt:
    try:
        __import__(mod)
        print(f"  ✓ {pkg} (опц.)")
    except Exception:
        print(f"  · {pkg} (опц., не установлен)")

if miss:
    sys.exit("Не хватает: " + "; ".join(miss))

try:
    import torch
    print(f"\n  CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
except Exception:
    pass
PY

cat <<EOF

────────────────────────────────────────────────────────
✅ Окружение готово.

Активация в новом терминале:
   source .venv/bin/activate

Запуск без DIKIDI (оффлайн-демо):
   python -m src.main_offline

Только UI-тест (без камеры/мика):
   python scripts/test_ui.py

Ollama-модель собирается отдельно:
   bash scripts/setup_ollama_dental.sh
────────────────────────────────────────────────────────
EOF
