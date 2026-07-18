"""
FastAPI backend: WebSocket-мост между киоском и стриминговым пайплайном.

Протокол WS (одно соединение = один экран/киоск):

  Клиент → сервер
    JSON  {"type":"presence","present":true}   человек вошёл  → приветствие
    JSON  {"type":"presence","present":false}  человек ушёл   → прощание
    JSON  {"type":"utterance_start"}            начало реплики пациента
    BIN   <pcm16 mono 16k>                      аудио-чанки реплики
    JSON  {"type":"utterance_end"}              конец реплики → обработка

  Сервер → клиент
    JSON  {"type":"state","value":"idle|listening|thinking|speaking"}
    JSON  {"type":"transcript","text":...}      что услышали от пациента
    JSON  {"type":"reply","text":...}           текст фразы ассистента
    BIN   <pcm16 mono 16k>                      аудио для проигрывания
    JSON  {"type":"speak_end"}                  ассистент договорил
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

# Компактные трейсбеки: без дампа переменных на 200 строк (diagnose)
# и без раскрутки стека через весь uvicorn (backtrace)
logger.remove()
logger.add(sys.stderr, level="DEBUG", backtrace=False, diagnose=False)

from .config import get_settings
from .conversation_log import ConversationLog
from .dikidi_readonly import DikidiReadOnly
from .orchestrator import Conversation
from .persona import Persona
from .providers import build_providers

app = FastAPI(title="Dental AI — Server")

KIOSK_DIR = Path(__file__).resolve().parents[2] / "kiosk"


@app.middleware("http")
async def no_cache_static(request, call_next):
    """Киоск-страница и её JS/CSS не должны залипать в кэше браузера."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/health")
async def health():
    cfg = get_settings()
    return {
        "status": "ok",
        "llm": cfg.llm_provider if cfg.has_grok else "mock",
        # какая именно модель загружена — видно сразу, без чтения логов
        "llm_model": cfg.grok_model if cfg.has_grok else None,
        "stt": cfg.stt_provider if cfg.has_elevenlabs else "mock",
        "tts": cfg.tts_provider if (cfg.has_elevenlabs and cfg.tts_voice_id) else "mock",
    }


@app.get("/voices")
async def voices():
    """
    Голоса, доступные ТВОЕМУ аккаунту ElevenLabs.
    Открой http://localhost:8000/voices — категория premade работает на Free.
    """
    cfg = get_settings()
    if not cfg.has_elevenlabs:
        return {"error": "нет ELEVENLABS_API_KEY в server/.env"}
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": cfg.elevenlabs_api_key},
        )
        r.raise_for_status()
        data = r.json().get("voices", [])
    result = [
        {
            "voice_id": v.get("voice_id"),
            "name": v.get("name"),
            "category": v.get("category"),
            "labels": v.get("labels", {}),
            "works_on_free": v.get("category") in ("premade", "cloned", "generated"),
        }
        for v in data
    ]
    # premade сверху — их можно использовать на бесплатном тарифе
    result.sort(key=lambda v: (not v["works_on_free"], v["name"] or ""))
    return {"hint": "возьми voice_id с works_on_free=true → ELEVENLABS_VOICE_ID",
            "voices": result}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    cfg = get_settings()
    stt, llm, tts = build_providers(cfg)
    persona = Persona(cfg.prompts_path)
    conv = Conversation(stt, llm, tts, persona)
    dikidi = DikidiReadOnly(
        api_key=cfg.dikidi_api_key,
        company_id=cfg.dikidi_company_id,
        base_url=cfg.dikidi_base_url,
        demo=cfg.dikidi_demo,
    )
    convlog = ConversationLog(cfg.conversations_dir)

    audio_buf = bytearray()
    recording = False

    async def send_state(value: str):
        await ws.send_json({"type": "state", "value": value})

    async def audio_sink(chunk: bytes):
        await ws.send_bytes(chunk)

    async def speak(coro_factory, state: str = "speaking"):
        await send_state(state)
        await coro_factory()
        await ws.send_json({"type": "speak_end"})
        await send_state("idle")

    logger.info("Киоск подключён")
    try:
        await send_state("idle")
        while True:
            msg = await ws.receive()

            # клиент отключился (закрыл вкладку / Ctrl+C) — выходим тихо,
            # иначе следующий receive() бросит RuntimeError
            if msg.get("type") == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"] is not None:
                if recording:
                    audio_buf.extend(msg["bytes"])
                continue

            if "text" not in msg or msg["text"] is None:
                continue

            try:
                data = json.loads(msg["text"])
            except json.JSONDecodeError:
                continue

            mtype = data.get("type")

            if mtype == "presence":
                try:
                    if data.get("present"):
                        convlog.start()
                        # свежие записи на сегодня → в контекст Оливии (read-only)
                        bookings = await dikidi.today_bookings()
                        conv.set_context(
                            DikidiReadOnly.format_for_prompt(bookings, dikidi.available)
                        )
                        greeting_holder: list[str] = []
                        async def _greet():
                            greeting_holder.append(await conv.greet(audio_sink))
                        await speak(_greet)
                        if greeting_holder:
                            convlog.log("assistant", greeting_holder[0])
                    else:
                        farewell_holder: list[str] = []
                        async def _farewell():
                            farewell_holder.append(await conv.farewell(audio_sink))
                        await speak(_farewell)
                        if farewell_holder:
                            convlog.log("assistant", farewell_holder[0])
                        convlog.end("patient_left")
                except Exception:
                    logger.exception("Ошибка при приветствии/прощании")
                    await ws.send_json({"type": "speak_end"})
                    await send_state("idle")

            elif mtype == "utterance_start":
                if not recording:
                    audio_buf.clear()
                    recording = True
                    await send_state("listening")

            elif mtype == "utterance_cancel":
                # клиент решил, что это был шорох, а не речь
                recording = False
                audio_buf.clear()
                await send_state("idle")

            elif mtype == "utterance_end":
                recording = False
                audio = bytes(audio_buf)
                audio_buf.clear()
                await send_state("thinking")

                async def on_transcript(t: str):
                    convlog.log("user", t)
                    await ws.send_json({"type": "transcript", "text": t})

                reply_buf: list[str] = []

                async def on_reply_text(t: str):
                    reply_buf.append(t)
                    await ws.send_json({"type": "reply", "text": t})

                await send_state("speaking")
                try:
                    await conv.handle_utterance(
                        audio,
                        audio_sink,
                        on_transcript=on_transcript,
                        on_reply_text=on_reply_text,
                    )
                except Exception:
                    # ни одна ошибка STT/LLM/TTS не должна ронять соединение
                    logger.exception("Ошибка обработки реплики")
                if reply_buf:
                    convlog.log("assistant", " ".join(reply_buf))
                await ws.send_json({"type": "speak_end"})
                if conv.ended:
                    # LLM поставил метку [КОНЕЦ]: диалог завершён,
                    # киоск возвращается к медузам без повторного прощания
                    logger.info("Диалог завершён — возврат в режим ожидания")
                    convlog.end("assistant_closed")
                    await ws.send_json({"type": "conversation_end"})
                await send_state("idle")

    except WebSocketDisconnect:
        logger.info("Киоск отключён")
    finally:
        # не теряем расшифровку, если связь оборвалась посреди разговора
        convlog.end("disconnect")


# Раздаём статику киоска последней (чтобы /ws и /health имели приоритет)
if KIOSK_DIR.exists():
    @app.get("/")
    async def index():
        return FileResponse(KIOSK_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(KIOSK_DIR)), name="kiosk")
