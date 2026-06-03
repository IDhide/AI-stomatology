# Тест на MacBook — пошаговый гид

Цель: проверить весь сценарий (камера → STT → LLM → TTS → UI) на ноутбуке,
прежде чем переносить на основную Linux-машину с RTX 3060.

На Mac работают все компоненты, кроме CUDA-ускорения — STT/TTS считаются на CPU.
Для теста этого достаточно: голос звучит так же, распознавание чуть медленнее.

---

## 0. Что нужно один раз настроить в macOS

Mac строго спрашивает разрешения для каждой программы, поэтому ОДИН раз откройте:

**System Settings → Privacy & Security**

- **Camera** — включите для приложения, из которого будете запускать
  (обычно Terminal, iTerm, или ваша IDE — PyCharm/VS Code).
- **Microphone** — то же самое.

Без этого `cv2.VideoCapture(0)` вернёт пустой кадр, а `sounddevice` —
тишину RMS≈0. Скрипт `setup_macbook.sh` подскажет, если что-то не дано.

---

## 1. Установка

```bash
cd ~/path/to/AI\ stomatology
bash scripts/setup_macbook.sh
```

Что произойдёт:
1. `brew install ffmpeg portaudio sdl2 sdl2_*` — системные библиотеки.
2. Поставится `uv`, создастся `.venv` с Python 3.11.
3. Поставится проект с группой `[cpu]` (torch без CUDA).
4. Скрипт тут же откроет камеру (1 кадр) и микрофон (1.5 с) — проверка
   разрешений. Если что-то не разрешено — он подскажет, где включить.

> Apple Silicon (M1–M4): всё работает «из коробки». `torch.backends.mps.is_available()`
> покажет `True`, но `faster-whisper` всё равно использует CPU — это нормально для теста.

---

## 2. Ollama для macOS

```bash
brew install ollama
ollama serve &                            # фоновый сервис
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama create smile-ru -f scripts/Modelfile.mac
```

Проверка:

```bash
ollama run smile-ru "Здравствуйте"
# должно ответить «Здравствуйте, я Лена…»
```

Почему 3B, а не 7B как на основной машине: 7B-q4 хочет ~6 GB RAM,
на 8 GB MacBook это уже впритык. 3B (~2 GB) работает у всех и даёт
сравнимое качество для теста сценария.
На основной машине с 3060 12GB используйте `scripts/Modelfile` (7B).

---

## 3. Запуск

### 3.1. Сначала только UI — проверка экрана

```bash
source .venv/bin/activate
python scripts/test_ui.py
```

Откроется окно 1280×720 на ~36 секунд: пробежит все режимы IDLE → GREETING →
LISTENING → THINKING → SPEAKING с тестовыми субтитрами и пульсацией круга
от синусоиды. Это нужно, чтобы убедиться, что pygame и видео медуз заводятся.

### 3.2. Полный оффлайн-демо с камерой и микрофоном Mac

```bash
python -m src.main_offline --config config/settings.mac.yaml --windowed
```

Что произойдёт:
- откроется окно с медузами;
- FaceTime HD начнёт следить за лицом;
- как только вы подойдёте к ноуту — Лена поздоровается;
- говорите по-русски в микрофон → она отвечает;
- DIKIDI заменён на stub: окна, врачи, цены — правдоподобные «фейк»-данные;
- когда вы отойдёте от ноута (камера не видит лицо ~3 с) — Лена попрощается
  и вернётся в режим ожидания с медузами.

### 3.3. Полезные ключи для теста

| Команда | Когда использовать |
|---|---|
| `--simulate-voice` | без микрофона: реплики печатаете в терминал |
| `--no-camera` | без камеры: ассистент сразу «увидит» вас |
| `--windowed` | окно 1280×720 (по умолчанию для Mac) |

Без полного экрана удобно тестировать: видно и окно UI, и логи в терминале.

### 3.4. Горячие клавиши UI

| Клавиша | Действие |
|---|---|
| `Esc` | выйти |
| `F11` | переключить fullscreen |
| `S` | скрыть/показать субтитры |
| `R` | сброс в IDLE |

---

## 4. Если что-то не работает

| Симптом | Что делать |
|---|---|
| Камера не открывается | System Settings → Privacy → Camera → разрешить Terminal/IDE |
| Микрофон молчит | System Settings → Privacy → Microphone → разрешить, перезапустить Terminal |
| `mediapipe` падает с архитектурой | `uv pip install --reinstall mediapipe` (требует Rosetta на старых сборках) |
| `faster-whisper` слишком медленный | смените в `settings.mac.yaml` `model: small` → `tiny` |
| Ollama «model not found» | `ollama list` и поправьте `model:` в `settings.mac.yaml` |
| TTS читает «один пять три ноль» вместо «пятнадцать тридцать» | проверьте, что `russian_normalizer` подгружен — он встроен в `voice/tts.py` |
| Звук TTS тихий | громкость System → Sound → Output, плюс `sd.default.device` если несколько устройств |

---

## 5. Перенос на основную машину (Linux + RTX 3060)

Когда тест на Mac пройден:

```bash
# на Linux
bash scripts/setup_env.sh            # CUDA-сборка torch
bash scripts/setup_ollama_dental.sh  # 7B модель (smile-ru)
python -m src.main_offline           # уже с дефолтным settings.yaml (fullscreen 1920×1080)
```

Различия конфигов:

| Параметр | Mac (settings.mac.yaml) | Linux 3060 (settings.yaml) |
|---|---|---|
| `voice.stt.model` | `small` | `large-v3` |
| `voice.stt.device` | `cpu` | `cuda` |
| `voice.stt.compute_type` | `int8` | `int8_float16` |
| `llm.fallback_model` | `qwen2.5:3b-...` | `qwen2.5:7b-...` |
| `ui.window.fullscreen` | `false` | `true` |
| `ui.window.size` | 1280×720 | 1920×1080 |
| `camera.fps` | 15 | 15 |
| `dental.alert_on_urgent` | false | true (нотификации админу) |

Логика, промпты, нормализатор, юмор, DIKIDI-клиент, UI — общие, ничего менять
не нужно. Только `--config` и Modelfile.
