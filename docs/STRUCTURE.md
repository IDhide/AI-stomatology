# Структура проекта Smile.AI (AI стоматология)

> Бюджетный on-prem прототип голосового ассистента-администратора для стоматологии.
> Хост: одна машина с RTX 3060 12GB. Никаких облаков для LLM/STT/TTS.

## 1. Дерево каталогов

```
AI stomatology/
├── README.md                     — обзор и быстрый старт
├── QUICKSTART.md                 — пошаговый запуск
├── PROJECT_STATUS.md             — текущий статус задач
├── .env / .env.example           — креды (DIKIDI_TOKEN, RTSP, CONFIG_PATH)
├── requirements.txt              — полные зависимости (CUDA-сборка)
├── requirements-minimal.txt      — минимум для CPU-демо
│
├── config/
│   ├── settings.yaml             — все параметры (см. §3)
│   └── prompts.yaml              — system + tool prompts (RU)
│
├── assets/
│   ├── videos/jellyfish.mp4      — idle-видео с медузами (Seedance 2.0)
│   └── sounds/chime.wav          — звуковой триггер «слушаю»
│
├── data/
│   ├── logs/app.log              — приложение (loguru rotate)
│   ├── logs/conversations.jsonl  — каждое сообщение строкой JSON
│   └── conversations.db          — SQLite: clients, sessions, messages
│
├── docs/
│   ├── STRUCTURE.md              — этот документ
│   ├── SETUP.md                  — установка драйверов, моделей, Ollama
│   ├── ARCHITECTURE.md           — диаграммы FSM и event-bus
│   ├── API.md                    — DIKIDI endpoints, обёртки
│   └── DENTAL_KB.md              — словарь процедур + правила юмора
│
├── scripts/
│   ├── install.sh                — единый bootstrap (venv + cuda + ffmpeg)
│   ├── setup_ollama_dental.sh    — поднять Ollama + собрать модель smile-ru
│   ├── Modelfile                 — Modelfile для Qwen2.5-7B-Instruct, q4_K_M
│   ├── download_models.py        — faster-whisper, silero-vad, silero-tts
│   ├── test_components.py        — health-check всех модулей
│   ├── test_mic.py               — диагностика микрофона + VAD
│   ├── test_camera.py            — RTSP-поток Xi C200
│   └── test_dikidi.py            — sanity-check DIKIDI API
│
├── src/
│   ├── main.py                   — production entry (asyncio)
│   ├── main_demo.py              — demo: моки вместо железа
│   │
│   ├── core/
│   │   ├── app.py                — Orchestrator: event loop + FSM
│   │   ├── app_demo.py           — то же на mock-модулях
│   │   ├── config.py             — загрузка YAML + env
│   │   ├── state_machine.py      — IDLE/GREET/LISTEN/THINK/SPEAK/FAREWELL
│   │   ├── event_bus.py          — pub/sub между модулями
│   │   └── conversation_logger.py — JSONL + SQLite
│   │
│   ├── camera/
│   │   ├── detector.py           — Xi C200 RTSP + MediaPipe Face
│   │   ├── motion.py             — background-subtractor (MOG2)
│   │   ├── presence.py           — трекер «человек уходит» (timeout 3s)
│   │   └── detector_mock.py
│   │
│   ├── voice/
│   │   ├── stt.py                — faster-whisper large-v3 + RU lexicon
│   │   ├── tts.py                — Silero v4_ru + normalizer
│   │   ├── vad.py                — Silero-VAD: разделение пауз
│   │   ├── russian_normalizer.py — числа/даты/телефоны/ё-фикация (см. §4)
│   │   ├── dental_lexicon.py     — initial_prompt + post-correction
│   │   └── stt_mock.py / tts_mock.py
│   │
│   ├── llm/
│   │   ├── assistant.py          — Ollama + tool-calling, история, retry
│   │   ├── tools.py              — JSON-schema инструментов DIKIDI/KB
│   │   ├── prompt_builder.py     — сборка system + tools + history
│   │   └── assistant_mock.py
│   │
│   ├── dental/                   — НОВОЕ: «мозг» стоматологии
│   │   ├── knowledge_base.py     — процедуры, цены, длительности
│   │   ├── humor.py              — безопасные шутки + классификатор
│   │   ├── triage.py             — острая боль / плановый / косметика
│   │   ├── intents.py            — RU regex+keyword intent-классификатор
│   │   └── faq.py                — частые вопросы и готовые ответы
│   │
│   ├── dikidi/
│   │   ├── client.py             — async-обёртка над DIKIDI API
│   │   ├── booking.py            — create/cancel/reschedule
│   │   ├── slots.py              — поиск свободных окон с фильтрами
│   │   └── client_mock.py
│   │
│   └── ui/
│       ├── display.py            — Pygame fullscreen
│       ├── talking_circle.py     — пульсирующий круг (синх с TTS)
│       ├── idle_video.py         — петля медуз с fade
│       └── display_mock.py
│
└── tests/
    ├── test_normalizer.py        — золотые примеры русского текста
    ├── test_triage.py            — кейсы из реальных диалогов
    └── test_humor.py             — фильтр уместности
```

## 2. Состояния (FSM)

```
              ┌─── presence_lost (3s)  ───┐
              │                            ▼
   IDLE ─face_detected─► GREETING ─tts_done─► LISTENING
    ▲                                         │
    │                                  speech_end (VAD)
    │                                         ▼
    │                                      THINKING
    │                                         │
    │                                   llm_response
    │                                         ▼
    │                                      SPEAKING
    │                                         │
    │                                   tts_done / pause 10s
    │                                         ▼
    │                                      FAREWELL ──tts_done──┐
    │                                                            │
    └────────────────────────────────────────────────────────────┘
```

Каждый переход публикуется в `event_bus` — UI и логгер слушают независимо.

## 3. Конфиг (settings.yaml — ключевые секции)

| Секция | Что задаёт |
|---|---|
| `app` | name, debug |
| `camera` | RTSP URL Xi C200, FPS, пороги face/motion, cooldown |
| `voice.stt` | model=`large-v3`, compute_type=`int8_float16`, language=`ru`, beam_size=5 |
| `voice.tts` | speaker=`xenia`, sample_rate=48000, ssml=true |
| `voice.vad` | threshold=0.5, min_silence_ms=700 |
| `llm` | model=`smile-ru`, temperature=0.4, num_ctx=4096 |
| `dikidi` | base_url, company_id, token |
| `dental` | enable_humor=true, humor_threshold=0.6, working_hours, doctors[] |
| `ui` | resolution, fullscreen, circle radius/color, idle_video path |
| `timeouts` | idle_return=10, goodbye_delay=3, max_conversation=300 |

## 4. Русскоязычный pipeline (главное)

Большинство «русских» голосовых ассистентов плохо звучат и плохо слышат, потому что:

- **STT** запускают на `base`/`small` Whisper без `language="ru"` и без initial_prompt.
- **TTS** не нормализуют числа («15 30» вместо «пятнадцать тридцать»).
- Никто не правит распространённые ошибки распознавания: «корица» → «кариес», «полтит» → «пульпит».

Мы решаем это так:

1. `voice/stt.py` — `faster-whisper large-v3` int8_float16 на CUDA, `language="ru"`,
   `vad_filter=True`, `initial_prompt=DENTAL_PROMPT` со списком терминов и имён врачей.
   После транскрипции `dental_lexicon.post_correct(text)` правит словарь ошибок.

2. `voice/russian_normalizer.py` (см. отдельный файл) — перед каждым TTS:
   - числа → словами в нужном падеже (`15 рублей` → `пятнадцать рублей`);
   - даты → `21.05` → `двадцать первого мая`;
   - время → `15:30` → `в пятнадцать тридцать`;
   - телефоны → группами по 2-3 цифры;
   - ё-фикация для слов из словаря (`еще` → `ещё`);
   - ударения через `+` (`импл+антация`) — Silero поддерживает.

3. `voice/vad.py` — Silero-VAD режет тишину и обрезает фразы на естественных паузах,
   это убирает «эээ» и не даёт Whisper галлюцинировать на молчании.

4. `dental/intents.py` — лёгкая регулярка/ключевые слова на русском *до* LLM,
   чтобы дешёвые случаи (приветствие/прощание/уточнение цены) обрабатывать без сети.

## 5. Стоматологическая логика

- `dental/knowledge_base.py` — справочник процедур: код, название, синонимы,
  длительность, цена «от», противопоказания, специализация врача.
- `dental/triage.py` — по тексту жалобы определяет приоритет:
  - **urgent** (острая боль, флюс, кровотечение) → «ближайшее окно сегодня + рекомендация»;
  - **planned** (осмотр, гигиена, отбеливание) → обычная запись;
  - **cosmetic** (виниры, отбеливание, эстетика) → консультация ортодонта/эстетиста;
  - **pediatric** (ребёнок, детский) → детский врач.
- `dental/humor.py` — пул лёгких шуток, активируется только когда:
  - intent ∈ {greeting, planned, gigiena, smalltalk} и
  - тональность пациента ≥ 0 и
  - в последних 3 репликах нет слов *боль/страх/паника/срочно*.

## 6. Точки расширения

- Заменить Whisper на `gigaam` (Сбер, чисто русский) — drop-in в `voice/stt.py`.
- Заменить Silero TTS на `xtts-v2` — те же `synthesize(text)->np.ndarray`.
- Подключить локальную RAG-базу прайса/протоколов — добавить tool в `llm/tools.py`.
- Добавить телеграм-нотификации админу при острых случаях — слушатель `event_bus`.
