#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  setup_macbook.sh — поднять проект на macOS для теста (без CUDA).
#  Подходит для Apple Silicon (M1/M2/M3/M4) и Intel Mac.
#
#  Что делает:
#    1. Ставит brew-зависимости (ffmpeg, portaudio, sdl2 — для pygame).
#    2. Ставит uv, создаёт .venv.
#    3. Ставит проект с группой [cpu] (torch без CUDA).
#    4. Проверяет доступ к камере и микрофону.
#    5. Подсказывает следующие шаги (ollama + модель).
#
#  Запуск:
#       bash scripts/setup_macbook.sh
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "▶ Проект: $PROJECT_DIR"
echo "▶ macOS: $(sw_vers -productName) $(sw_vers -productVersion) ($(uname -m))"

# ── 1. brew ──────────────────────────────────────────────────────
if ! command -v brew >/dev/null 2>&1; then
    echo "▶ Homebrew не найден — установите его с https://brew.sh, потом запустите снова."
    exit 1
fi
echo "▶ brew $(brew --version | head -1)"

echo "▶ Системные зависимости через brew..."
brew install --quiet ffmpeg portaudio sdl2 sdl2_image sdl2_mixer sdl2_ttf 2>&1 | tail -5 || true

# ── 2. uv ────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
    echo "▶ Устанавливаю uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
echo "▶ uv $(uv --version)"

# ── 3. venv + зависимости ─────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "▶ Создаю .venv (python 3.11)..."
    uv venv --python 3.11
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "▶ Ставлю проект (cpu-сборка, без CUDA)..."
uv pip install -e ".[cpu]"

# ── 4. health-check + камера + микрофон ───────────────────────────
echo "▶ Проверяю модули..."
python - <<'PY'
import sys, importlib
ok = True
for mod in ["loguru", "yaml", "pygame", "cv2", "numpy", "sounddevice",
            "torch", "faster_whisper", "mediapipe", "num2words"]:
    try:
        importlib.import_module(mod)
        print(f"  ✓ {mod}")
    except Exception as e:
        ok = False
        print(f"  ✗ {mod}: {e}")
import torch
print(f"\n  torch backend: cpu | MPS available: {torch.backends.mps.is_available()}")
sys.exit(0 if ok else 1)
PY

echo ""
echo "▶ Проверяю камеру FaceTime HD (1 кадр)..."
python - <<'PY'
import cv2
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("  ✗ камера не открылась.")
    print("    System Settings → Privacy & Security → Camera → дайте доступ Terminal/iTerm/IDE.")
else:
    ok, frame = cap.read()
    if ok:
        print(f"  ✓ кадр {frame.shape[1]}×{frame.shape[0]} получен")
    else:
        print("  ✗ кадр пустой — пересоберите доступ к камере")
    cap.release()
PY

echo ""
echo "▶ Проверяю микрофон (запись 1.5 с)..."
python - <<'PY'
try:
    import sounddevice as sd, numpy as np
    rec = sd.rec(int(1.5*16000), samplerate=16000, channels=1, dtype="float32")
    sd.wait()
    rms = float(np.sqrt(np.mean(rec**2)))
    print(f"  ✓ запись прошла, RMS={rms:.4f}")
    if rms < 1e-4:
        print("    Очень тихо — проверьте, что Terminal имеет доступ к Микрофону:")
        print("    System Settings → Privacy & Security → Microphone")
except Exception as e:
    print(f"  ✗ {e}")
    print("    Дайте Terminal/iTerm доступ к микрофону: System Settings → Privacy & Security → Microphone")
PY

cat <<EOF

────────────────────────────────────────────────────────
✅ Окружение готово. Дальше:

1) Установите Ollama для macOS:
   brew install ollama
   ollama serve &                        # стартует фоном
   # или просто запустите приложение Ollama.app

2) Соберите модель (быстрая для теста):
   ollama pull qwen2.5:3b-instruct-q4_K_M
   ollama create smile-ru -f scripts/Modelfile.mac   # см. инструкцию

3) Проверьте только UI (без камеры/мика):
   python scripts/test_ui.py

4) Запустите оффлайн-демо (с камерой Mac):
   python -m src.main_offline --config config/settings.mac.yaml --windowed

   Полезные ключи:
       --no-camera         только клавиатура (без камеры)
       --simulate-voice    реплики через stdin (без мика/TTS)

   Горячие клавиши UI:
       Esc — выйти
       F11 — переключить полный экран
       S   — скрыть/показать субтитры
       R   — сброс в режим ожидания
────────────────────────────────────────────────────────
EOF
