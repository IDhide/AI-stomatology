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

import asyncio
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

from .booking_store import BookingStore
from .config import get_settings
from .conversation_log import ConversationLog
from .dikidi_readonly import DikidiReadOnly
from .orchestrator import Conversation
from .persona import Persona
from .providers import build_providers
from .telegram_notify import TelegramNotifier
from .voice_id.embedder import VoiceEmbedder
from .voice_id.store import VoiceMemoryStore

app = FastAPI(title="Dental AI — Server")

KIOSK_DIR = Path(__file__).resolve().parents[2] / "kiosk"
IDLE_VIDEO_DIR = Path(__file__).resolve().parents[2] / "assets" / "videos"

_settings = get_settings()
booking_store = BookingStore(_settings.bookings_dir)
telegram = TelegramNotifier(_settings.telegram_bot_token, _settings.telegram_chat_id, booking_store)

# Узнавание по голосу — выключено по умолчанию (см. VOICE_ID_ENABLED); модель
# грузим один раз при старте процесса, не на каждое WS-подключение.
voice_embedder = VoiceEmbedder() if _settings.voice_id_enabled else None
voice_memory = VoiceMemoryStore(_settings.voice_memory_path) if _settings.voice_id_enabled else None
if _settings.voice_id_enabled:
    if voice_embedder and voice_embedder.enabled:
        mode = "теневой режим (не влияет на диалог)" if _settings.voice_id_shadow_mode else "активно"
        logger.info(f"Голос: узнавание включено, {mode}, порог={_settings.voice_match_threshold}")
    else:
        logger.warning("VOICE_ID_ENABLED=true, но resemblyzer не установлен — узнавание по голосу не работает")


@app.on_event("startup")
async def _start_telegram_background_tasks() -> None:
    if not telegram.enabled:
        logger.info("Telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы — сводки отключены")
        return
    asyncio.create_task(telegram.run_updates_loop())
    asyncio.create_task(telegram.run_daily_digest_loop(_settings.telegram_digest_time))
    logger.info(f"Telegram: сводка заявок будет приходить в {_settings.telegram_digest_time}")


@app.middleware("http")
async def cache_control_static(request, call_next):
    """Киоск-страница и её JS/CSS не должны залипать в кэше браузера,
    а тяжёлые видео-файлы — наоборот, кэшируем, чтобы не грузились заново."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-cache"
    elif path.startswith("/assets/") and path.endswith((".mp4", ".webm", ".ogg")):
        resp.headers["Cache-Control"] = "public, max-age=3600"
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
        "telegram": "on" if cfg.has_telegram else "off",
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
    )    convlog = ConversationLog(cfg.conversations_dir)

    audio_buf = bytearray()
    recording = False

    # ── Узнавание по голосу: состояние на одну сессию (один визит) ─────
    dikidi_context = ""
    voice_sample_buf = bytearray()
    voice_match_attempted = False
    voice_matched_id: int | None = None
    voice_embedding: list[float] | None = None

    async def send_state(value: str):
        await ws.send_json({"type": "state", "value": value})

    async def audio_sink(chunk: bytes):
        await ws.send_bytes(chunk)

    async def speak(coro_factory, state: str = "speaking"):
        await send_state(state)
        await coro_factory()
        await ws.send_json({"type": "speak_end"})
        await send_state("idle")

    def finalize_voice(booking) -> None:
        """
        Вызывается на всех точках завершения сессии. Если голос за визит
        совпал с уже известным — просто отмечаем «видели». Если не
        совпал, но за сессию собрана заявка с именем (см. booking_store) —
        заводим новый голосовой отпечаток. Без имени отпечаток не имеет
        смысла сохранять — представиться в следующий раз всё равно нечем.
        """
        if not (cfg.voice_id_enabled and voice_embedder and voice_embedder.enabled):
            return
        if voice_matched_id is not None:
            voice_memory.touch_seen(voice_matched_id)
        elif voice_embedding and booking and booking.name:
            voice_memory.enroll(voice_embedding, booking.name, booking.phone)

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
                        # новый визит — сбрасываем состояние узнавания по голосу
                        # предыдущего пациента (WS-соединение живёт весь день)
                        voice_sample_buf.clear()
                        voice_match_attempted = False
                        voice_matched_id = None
                        voice_embedding = None
                        # свежие записи на сегодня + свободные окна → в контекст Оливии (read-only)
                        bookings = await dikidi.today_bookings()
                        free = await dikidi.free_slots(days=cfg.dikidi_days_ahead)
                        dikidi_context = DikidiReadOnly.format_for_prompt(
                            bookings, dikidi.available, free_slots=free
                        )
                        conv.set_context(dikidi_context)
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
                        booking = conv.take_booking()
                        if booking:
                            booking_store.add(booking)
                        finalize_voice(booking)
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

                # Узнавание по голосу: копим речь пациента и пробуем узнать один
                # раз за визит, как только накопилось достаточно (короткие фразы
                # дают слишком шумный отпечаток — см. план/README).
                if (
                    cfg.voice_id_enabled
                    and voice_embedder
                    and voice_embedder.enabled
                    and not voice_match_attempted
                ):
                    voice_sample_buf.extend(audio)
                    sample_seconds = len(voice_sample_buf) / 2 / 16000
                    # буфер не раздуваем бесконечно: если за 30с накопленного
                    # аудио чистой речи так и не набралось — сдаёмся на этот визит
                    if sample_seconds >= 30:
                        voice_match_attempted = True
                        logger.info("🎙️ Голос: 30с аудио без достаточной речи — пропускаю узнавание")
                    elif sample_seconds >= cfg.voice_min_sample_seconds:
                        voice_embedding = voice_embedder.embed(bytes(voice_sample_buf))
                        # embed() вернул None — чистой речи мало: НЕ считаем
                        # попытку состоявшейся, копим дальше
                        if voice_embedding:
                            voice_match_attempted = True
                            match = voice_memory.match(
                                voice_embedding,
                                cfg.voice_match_threshold,
                                weak_threshold=cfg.voice_match_weak_threshold,
                            )
                            logger.info(
                                f"🎙️ Голос: distance={match.distance:.3f} "
                                f"is_new={match.is_new} shadow={cfg.voice_id_shadow_mode}"
                            )
                            if not match.is_new and not cfg.voice_id_shadow_mode:
                                voice_matched_id = match.patient_id
                                conv.set_voice_match(match)
                                voice_line = VoiceMemoryStore.format_for_prompt(match)
                                conv.set_context(
                                    "\n\n".join(p for p in (dikidi_context, voice_line) if p)
                                )
                                # Уверенное совпадение — подмешиваем свежий отпечаток
                                # в сохранённый: голос/микрофон «плывут» со временем,
                                # так база сама адаптируется к киоску
                                if match.confidence == "high":
                                    voice_memory.update_embedding(match.patient_id, voice_embedding)

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
                    booking = conv.take_booking()
                    if booking:
                        booking_store.add(booking)
                    finalize_voice(booking)
                    convlog.end("assistant_closed")
                    await ws.send_json({"type": "conversation_end"})
                await send_state("idle")

    except WebSocketDisconnect:
        logger.info("Киоск отключён")
    finally:
        # не теряем заявку и расшифровку, если связь оборвалась посреди разговора
        booking = conv.take_booking()
        if booking:
            booking_store.add(booking)
        finalize_voice(booking)
        convlog.end("disconnect")


# Видео-заставка (медузы) лежит в assets/videos/ (вне kiosk/, чтобы не
# коммитить тяжёлый файл вместе с фронтендом) — отдаём его по тому же
# пути /assets/jellyfish.mp4, который запрашивает kiosk/app.js
if IDLE_VIDEO_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(IDLE_VIDEO_DIR)), name="idle-video")

# Раздаём статику киоска последней (чтобы /ws, /health и /assets имели приоритет)
if KIOSK_DIR.exists():
    @app.get("/")
    async def index():
        return FileResponse(KIOSK_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(KIOSK_DIR)), name="kiosk")
