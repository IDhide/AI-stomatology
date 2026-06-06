"""
server.py
=========
Веб-киоск Smile.AI + симуляция сценария «пациент подошёл к экрану».

Зачем: основной боевой UI на pygame требует физического дисплея. Веб-версия
повторяет тот же визуал (медузы → пульсирующий круг с аудио-волной → субтитры),
но открывается в любом браузере и стримит состояние через SSE. Это позволяет
посмотреть, «как выглядит визуал» и как реагирует система на появление человека,
без камеры/GPU/звука.

Что делает:
  • отдаёт статику из web/ (index.html, app.js, styles.css)
  • GET /api/events — SSE-поток состояний (mode/subtitle/amplitude)
  • запускает фоновый «сценарий»: симулятор присутствия (камера) → приветствие →
    диалог (данные берём из DikidiClientStub + dental KB) → прощание → idle
  • POST /api/trigger — вручную «впустить пациента» (как нажатие/детекция лица)

Запуск:
    python -m src.web.server --port 8080
    python -m src.web.server --port 8080 --no-loop   # без авто-сценария
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from aiohttp import web
from loguru import logger

from ..dikidi.client import DikidiClient
from ..core.conversation_logger import ConversationLogger
from ..core.config import load_config
from . import responder

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "videos"


# ────────────────────────────────────────────────────────────
#  Шина событий → всем подключённым браузерам
# ────────────────────────────────────────────────────────────
class EventBus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    async def publish(self, event: dict) -> None:
        dead = []
        for q in self._subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subs.discard(q)

    @property
    def n_clients(self) -> int:
        return len(self._subs)


# ────────────────────────────────────────────────────────────
#  Сценарий «администратор клиники»
# ────────────────────────────────────────────────────────────
class KioskScenario:
    """
    Прогоняет реалистичный диалог стоматологической клиники, синхронно
    отправляя UI-события. Реплики заранее заготовлены (без LLM/STT), но
    данные об окнах/услугах берутся из симулятора DIKIDI.
    """

    def __init__(self, bus: EventBus, dikidi: DikidiClientStub,
                 conv: ConversationLogger) -> None:
        self.bus = bus
        self.dikidi = dikidi
        self.conv = conv
        self.person_present = asyncio.Event()

    # ── низкоуровневые помощники ──
    async def mode(self, m: str) -> None:
        await self.bus.publish({"type": "mode", "mode": m})

    async def say(self, text: str) -> None:
        """Бот говорит: субтитр + режим speaking + имитация амплитуды речи."""
        await self.bus.publish({"type": "subtitle", "text": text, "who": "bot"})
        await self.mode("speaking")
        self.conv.log_message(self._cid, "assistant", text)
        # имитируем длительность речи и «амплитуду» по словам
        words = max(1, len(text.split()))
        duration = min(7.0, 0.28 * words + 0.6)
        t0 = time.monotonic()
        while time.monotonic() - t0 < duration:
            amp = 0.4 + 0.5 * abs((time.monotonic() * 7) % 1 - 0.5) * 2
            await self.bus.publish({"type": "amplitude", "value": amp})
            await asyncio.sleep(0.06)
        await self.bus.publish({"type": "amplitude", "value": 0.0})

    async def user(self, text: str) -> None:
        await self.mode("listening")
        await self.bus.publish({"type": "subtitle", "text": "вы: " + text, "who": "user"})
        self.conv.log_message(self._cid, "user", text)
        await asyncio.sleep(1.6)

    async def think(self, secs: float = 1.2) -> None:
        await self.mode("thinking")
        await asyncio.sleep(secs)

    # ── полный диалог ──
    async def run_once(self) -> None:
        self._cid = self.conv.start_conversation()
        logger.info("👤 СИМУЛЯЦИЯ КАМЕРЫ: лицо обнаружено → запуск диалога")

        await self.mode("greeting")
        await self.say("Здравствуйте, меня зовут Оливия, администратор клиники "
                       "«Стоматология номер один». Подскажите, что вас беспокоит?")

        await self.user("Хочу поставить виниры, сколько это стоит?")
        await self.think()
        # цены — из персоны (промпта), сейчас действует акция на E-Max
        await self.say("Сейчас у нас акция на виниры E-Max: от двадцати восьми с "
                       "половиной до тридцати пяти тысяч под ключ — входят все "
                       "манипуляции, сканирование и работа врача. Точную стоимость "
                       "врач назовёт на бесплатной консультации. Подобрать вам день?")

        await self.user("Да, давайте на этой неделе вечером.")
        await self.think()
        # окна смотрим в DIKIDI, но время НЕ подтверждаем — согласует администратор
        slots = await self.dikidi.get_available_slots("терапевт", limit=3)
        if slots:
            human = "; ".join(s["human"] for s in slots[:2])
            await self.say(f"Подойдёт, например, {human}. Назовите ваше имя и "
                           "продиктуйте номер, администратор перезвонит и согласует время?")
        else:
            await self.say("Подберём удобное время. Назовите ваше имя и продиктуйте "
                           "номер, администратор перезвонит и согласует запись?")

        await self.user("Мария, восемь девятьсот девяносто девять, ноль, ноль, ноль...")
        await self.think(0.9)
        await self.say("Записала, Мария. Администратор перезвонит и согласует точное "
                       "время консультации. Остались ещё вопросы?")

        await asyncio.sleep(0.8)
        logger.info("👋 СИМУЛЯЦИЯ КАМЕРЫ: пациент ушёл → возврат в режим ожидания")
        await self.bus.publish({"type": "clear_subtitle"})
        await self.mode("idle")
        self.conv.end_conversation(self._cid)

    async def auto_loop(self, period: float = 8.0) -> None:
        """Бесконечно: ждём «пациента», проигрываем диалог, пауза, снова."""
        await asyncio.sleep(2.0)
        while True:
            await self.run_once()
            logger.info(f"💤 Режим ожидания (медузы) ~{period:.0f}с…")
            await asyncio.sleep(period)


# ────────────────────────────────────────────────────────────
#  HTTP-обработчики
# ────────────────────────────────────────────────────────────
async def sse_events(request: web.Request) -> web.StreamResponse:
    bus: EventBus = request.app["bus"]
    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await resp.prepare(request)
    q = bus.subscribe()
    logger.info(f"🌐 Браузер подключился (клиентов: {bus.n_clients})")
    try:
        # начальное состояние
        await resp.write(b"data: " + json.dumps({"type": "mode", "mode": "idle"}).encode() + b"\n\n")
        while True:
            event = await q.get()
            await resp.write(b"data: " + json.dumps(event).encode() + b"\n\n")
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        bus.unsubscribe(q)
        logger.info(f"🌐 Браузер отключился (клиентов: {bus.n_clients})")
    return resp


async def trigger(request: web.Request) -> web.Response:
    """Ручной триггер «пациент подошёл» (как детекция лица камерой)."""
    scenario: KioskScenario = request.app["scenario"]
    asyncio.create_task(scenario.run_once())
    return web.json_response({"ok": True})


async def api_greeting(request: web.Request) -> web.Response:
    """Текст приветствия Оливии. Заодно — старт новой сессии (сброс контекста)."""
    session = request.app["session"]
    session["cid"] = None
    session["offtopic"] = 0
    llm = request.app.get("llm")
    if llm is not None and hasattr(llm, "reset_conversation"):
        llm.reset_conversation()

    source = request.query.get("source", "")
    if source == "camera":
        text = ("Здравствуйте! Меня зовут Оливия, администратор клиники "
                "«Стоматология номер один». Подскажите, как вас зовут?")
        if llm is not None:
            llm.history.append({
                "user": "[пациент подошёл к стойке — камера обнаружила лицо]",
                "assistant": text,
            })
    else:
        text = responder.greeting()

    return web.json_response({"text": text})


async def api_message(request: web.Request) -> web.Response:
    """
    Интерактивный режим: браузер распознал речь пациента (STT) и прислал текст.
    Возвращаем реплику Оливии — браузер озвучит её (TTS).
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "bad json"}, status=400)
    user_text = (data.get("text") or "").strip()
    session = request.app["session"]
    llm = request.app.get("llm")
    conv: ConversationLogger = request.app["conv"]

    # ── Умный мозг (Ollama): понимает контекст и свободную речь ──
    if llm is not None:
        if not user_text:
            return web.json_response({"reply": "", "ignored": True})
        logger.info(f"🎤 пациент: {user_text!r}")
        try:
            answer = await llm.get_response(user_text)
        except Exception:
            logger.exception("LLM error → fallback на правила")
            answer = responder.reply(user_text)
        if answer.strip().upper().startswith("ИГНОР"):
            logger.info(f"🙊 фоновый шум, игнорирую: {user_text!r}")
            return web.json_response({"reply": "", "ignored": True})
        logger.info(f"💬 Оливия: {answer!r}")
        if session.get("cid") is None:
            session["cid"] = conv.start_conversation()
        conv.log_message(session["cid"], "user", user_text)
        conv.log_message(session["cid"], "assistant", answer)
        return web.json_response({"reply": answer})

    # ── Правиловый запасной мозг: фильтр релевантности + шаблоны ──
    if not responder.is_relevant(user_text):
        session["offtopic"] += 1
        logger.info(f"🙊 нерелевантно ({session['offtopic']}): {user_text!r}")
        if session["offtopic"] == 3:
            session["offtopic"] = 0
            nudge = ("Если вам нужна стоматология — подскажите, что вас беспокоит, "
                     "и я помогу с записью?")
            return web.json_response({"reply": nudge, "nudge": True})
        return web.json_response({"reply": "", "ignored": True})

    session["offtopic"] = 0
    logger.info(f"🎤 пациент: {user_text!r}")

    # Запрос времени/записи → реально спрашиваем окна в тестовом DIKIDI
    if responder.wants_slots(user_text):
        dikidi = request.app["dikidi"]
        spec = responder.specialty_for(user_text)
        try:
            slots = await dikidi.get_available_slots(spec, limit=3)
        except Exception:
            logger.exception("DIKIDI недоступен")
            slots = []
        if slots:
            human = "; ".join(s["human"] for s in slots[:2])
            answer = (f"Подойдёт, например, {human}. Назовите ваше имя и "
                      "продиктуйте номер — администратор перезвонит и согласует "
                      "точное время?")
        else:
            answer = ("Сейчас подберём удобное время. Назовите ваше имя и "
                      "продиктуйте номер — администратор перезвонит и согласует "
                      "запись?")
    else:
        answer = responder.reply(user_text)

    logger.info(f"💬 Оливия: {answer!r}")
    if session.get("cid") is None:
        session["cid"] = conv.start_conversation()
    conv.log_message(session["cid"], "user", user_text)
    conv.log_message(session["cid"], "assistant", answer)
    return web.json_response({"reply": answer})


async def index(request: web.Request) -> web.Response:
    return web.FileResponse(WEB_DIR / "index.html")


async def api_tts(request: web.Request) -> web.Response:
    """
    Серверный синтез речи (Piper). GET ?text=... → audio/wav.
    Голос одинаковый в любом браузере, ничего наружу не уходит.
    """
    text = (request.query.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "no text"}, status=400)
    from . import tts
    audio, err = await asyncio.to_thread(tts.synthesize, text)
    if err:
        return web.json_response({"error": err}, status=503)
    return web.Response(body=audio, content_type="audio/wav",
                        headers={"Cache-Control": "no-store"})


async def api_tts_status(request: web.Request) -> web.Response:
    """Проверка: доступен ли серверный TTS (чтобы клиент решил, использовать его)."""
    from . import tts
    available = await asyncio.to_thread(tts.is_available)
    return web.json_response({"available": bool(available)})


async def api_stt(request: web.Request) -> web.Response:
    """
    Серверное распознавание речи (для Firefox и др. без Web Speech API).
    Тело запроса — аудио (audio/webm|ogg|wav) из MediaRecorder браузера.
    """
    audio = await request.read()
    ctype = request.headers.get("Content-Type", "")
    suffix = ".webm"
    if "ogg" in ctype:
        suffix = ".ogg"
    elif "wav" in ctype:
        suffix = ".wav"
    elif "mp4" in ctype or "m4a" in ctype:
        suffix = ".mp4"

    from . import stt
    text, err = await asyncio.to_thread(stt.transcribe, audio, suffix)
    if err:
        logger.warning(f"STT ошибка: {err}")
        return web.json_response({"text": "", "error": err}, status=503)
    logger.info(f"🎤 STT распознал: {text!r}")
    return web.json_response({"text": text})


# ────────────────────────────────────────────────────────────
def build_app(auto_loop: bool = True) -> web.Application:
    app = web.Application()
    bus = EventBus()

    # Единый DIKIDI-клиент. По умолчанию — тестовый сервер fake_server
    # (в docker это контейнер dikidi-sim). Для реального DIKIDI поменяйте
    # DIKIDI_BASE_URL и DIKIDI_TOKEN — код не меняется.
    dikidi_url = os.getenv("DIKIDI_BASE_URL", "http://127.0.0.1:8089").strip()
    dikidi_token = os.getenv("DIKIDI_TOKEN", "demo-token")
    dikidi = DikidiClient(dikidi_url, token=dikidi_token)

    conv = ConversationLogger({"enabled": True,
                               "jsonl_path": "data/logs/conversations.jsonl"})
    scenario = KioskScenario(bus, dikidi, conv)

    # ── Умный мозг на Ollama (если доступен) ──
    # Включается, когда задан OLLAMA_HOST. Использует персону из
    # config/prompts.yaml, держит контекст диалога, ходит в DIKIDI через tools.
    # Если Ollama недоступен — тихо откатываемся на правиловый responder.
    llm = None
    if os.getenv("OLLAMA_HOST"):
        try:
            from ..llm.assistant import LLMAssistant
            cfg = load_config()
            llm = LLMAssistant(cfg.llm, dikidi)
            logger.success(f"🧠 Мозг: Ollama ({llm.model})")
        except Exception as e:
            logger.warning(f"🧠 Ollama недоступен ({e}). Мозг: правиловый responder.")
            llm = None
    else:
        logger.info("🧠 Мозг: правиловый responder (OLLAMA_HOST не задан)")

    app["bus"] = bus
    app["scenario"] = scenario
    app["conv"] = conv
    app["dikidi"] = dikidi
    app["llm"] = llm
    app["auto_loop"] = auto_loop
    # состояние сессии киоска (изменяемый dict — без мутации app после старта)
    app["session"] = {"cid": None, "offtopic": 0}

    app.add_routes([
        web.get("/", index),
        web.get("/api/events", sse_events),
        web.post("/api/trigger", trigger),
        web.get("/api/greeting", api_greeting),
        web.post("/api/message", api_message),
        web.post("/api/stt", api_stt),
        web.get("/api/tts", api_tts),
        web.get("/api/tts/status", api_tts_status),
    ])
    # статика
    app.router.add_static("/", path=str(WEB_DIR), name="web")
    if ASSETS_DIR.exists():
        app.router.add_static("/assets/", path=str(ASSETS_DIR), name="assets")

    async def on_start(app: web.Application) -> None:
        if app["auto_loop"]:
            app["loop_task"] = asyncio.create_task(scenario.auto_loop())

        # ── Серверная камера (RTSP / USB) ──
        # Если задан CAMERA_SOURCE — запускаем фоновый детектор.
        # При обнаружении человека → POST /api/trigger (запуск голосовой сессии).
        if os.getenv("CAMERA_SOURCE", "").strip():
            from ..camera import detector
            loop = asyncio.get_event_loop()

            def _on_person():
                asyncio.run_coroutine_threadsafe(bus.publish({
                    "type": "camera", "event": "person_detected"
                }), loop)

            def _on_left():
                asyncio.run_coroutine_threadsafe(bus.publish({
                    "type": "camera", "event": "person_left"
                }), loop)

            if detector.start(_on_person, _on_left):
                logger.success("Камера: серверная детекция запущена")

    async def on_cleanup(app: web.Application) -> None:
        t = app.get("loop_task")
        if t:
            t.cancel()
        if os.getenv("CAMERA_SOURCE", "").strip():
            from ..camera import detector
            detector.stop()
        await dikidi.close()

    app.on_startup.append(on_start)
    app.on_cleanup.append(on_cleanup)
    return app


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Smile.AI веб-киоск")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--demo", action="store_true",
                   help="прокручивать заготовленный диалог (без микрофона) — для показа визуала")
    p.add_argument("--no-loop", action="store_true",
                   help="(устарело) то же, что без --demo: интерактивный режим")
    args = p.parse_args(argv)

    mode = "ДЕМО-сценарий" if args.demo else "интерактивный (микрофон + голос)"
    logger.info(f"🦷 Smile.AI веб-киоск: http://{args.host}:{args.port} | режим: {mode}")
    web.run_app(build_app(auto_loop=args.demo),
                host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
