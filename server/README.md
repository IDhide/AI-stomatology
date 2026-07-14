# Серверный backend (новая архитектура)

Стриминговый голосовой пайплайн: **Grok (LLM) + ElevenLabs (STT+TTS)**,
веб-киоск на Three.js, память и распознавание лиц на Supabase (pgvector).

Отличие от старого `src/` (Pygame + Ollama, последовательный пайплайн):
здесь этапы **перекрываются** (LLM токены → нарезка на предложения → TTS
→ проигрывание), поэтому первый звук идёт через ~1–1.5 с, а не 15.

## Быстрый старт (MacBook, без ключей — на mock)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
chmod +x server/run.sh && ./server/run.sh
```

Открой **http://localhost:8000** в Chrome → «Запустить киоск».
Кнопки внизу слева (👤 Вошёл / 🚪 Ушёл / 🎤 Говорить) эмулируют камеру для теста.

Без ключей STT/LLM/TTS работают на заглушках — но весь пайплайн, WebSocket,
переключение медузы↔шар и синхронизация анимации уже видны.

## Включить реальные сервисы

Скопируй `server/.env.example` → `server/.env` и заполни:

| Ключ | Где взять |
|------|-----------|
| `XAI_API_KEY` | console.x.ai — API-ключ Grok |
| `ELEVENLABS_API_KEY` | elevenlabs.io → Profile → API key |
| `ELEVENLABS_VOICE_ID` | id женского русского голоса из твоей библиотеки |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase → Project settings → API |

Перезапусти сервер — фабрика провайдеров сама подхватит реальные API
(`/health` покажет, что активно, а что на mock).

## Распознавание лиц (опционально, фаза 2)

```bash
pip install insightface onnxruntime opencv-python-headless
```

Выполни `server/app/memory/schema.sql` в Supabase (SQL Editor) — создаст
таблицы `patients` (с `vector(512)`), `sessions`, `interactions` и функцию
поиска `match_patient`.

## Структура

```
server/app/
  main.py            FastAPI + WebSocket, раздача киоска
  orchestrator.py    стриминговый пайплайн (перекрытие LLM→TTS)
  persona.py         персона Оливии (из config/prompts.yaml)
  config.py          выбор провайдеров + секреты из .env
  providers/
    base.py          интерфейсы STT/LLM/TTS (слой абстракции)
    llm_grok.py      Grok (xAI), стриминг
    tts_elevenlabs.py  ElevenLabs Flash, стриминг
    stt_elevenlabs.py  ElevenLabs Scribe
    mock.py          заглушки для работы без ключей
  memory/            Supabase: профили, сессии, «здоровались ли»
  face/              InsightFace: эмбеддинг лица → pgvector
kiosk/               веб-клиент (медузы idle + фиолетовый шар)
```
