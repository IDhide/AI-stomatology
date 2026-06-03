"""
main_offline.py
===============
Оффлайн-демо Smile.AI — без реального DIKIDI API.

Что работает:
  • камера (Xi C200 RTSP или USB) → детекция лица → старт диалога
  • STT (faster-whisper) + TTS (Silero) на русском
  • LLM (Ollama, model `smile-ru`) с intents/triage/FAQ/юмором
  • DIKIDI заменён на DikidiClientStub — отдаёт правдоподобные «окна»
    и хранит «записи» в памяти
  • UI на 1920×1080: видео медуз → круг с пульсацией → субтитры
  • Логирование диалогов в data/logs/conversations.jsonl

CLI:
   python -m src.main_offline                  — всё реально + DIKIDI-stub
   python -m src.main_offline --no-camera      — без камеры (триггер по Space)
   python -m src.main_offline --windowed       — оконный режим, удобно дебажить
   python -m src.main_offline --simulate-voice — без мика/тts: реплики из stdin
"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from pathlib import Path

from loguru import logger

from .core.config import load_config
from .core.conversation_logger import ConversationLogger
from .dikidi.client_stub import DikidiClientStub
from .ui.display import UIDisplay


# ────────────────────────────────────────────────────────────
def setup_logging(cfg) -> None:
    logger.remove()
    logger.add(sys.stdout, level=cfg.logging.level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan> | {message}")
    f = cfg.logging.file or {}
    if f.get("enabled", True):
        path = Path(f.get("path", "data/logs/app.log"))
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(str(path), rotation=f.get("max_size", "10MB"),
                   retention=int(f.get("backup_count", 5)),
                   level=cfg.logging.level, encoding="utf-8")


# ────────────────────────────────────────────────────────────
class OfflineApp:
    """
    Состояния: IDLE → GREETING → LISTENING → THINKING → SPEAKING → ... → IDLE
    Переходы инициируются:
      - камера: face_present_changed
      - VAD/STT: speech_ended  (внутри listen())
      - LLM:    response_ready (внутри get_response())
      - TTS:    speaking_done  (внутри speak())
      - таймаут: idle_return (10с тишины → возврат в idle)
    """

    def __init__(self, args, cfg):
        self.args = args
        self.cfg = cfg
        self.running = True

        # ── UI ──
        if args.windowed:
            cfg.ui.window["fullscreen"] = False
            cfg.ui.window["width"] = 1280
            cfg.ui.window["height"] = 720
        self.ui = UIDisplay(cfg.ui)

        # ── DIKIDI stub ──
        self.dikidi = DikidiClientStub()

        # ── STT / TTS ──
        self.stt = None
        self.tts = None
        if not args.simulate_voice:
            self._init_voice()

        # ── LLM ──
        self.llm = None
        self._init_llm()

        # ── Камера ──
        self.camera = None
        if not args.no_camera:
            self._init_camera()

        # ── Логгер диалогов ──
        log_cfg = cfg.logging.conversations or {}
        self.conv_logger = ConversationLogger(
            log_cfg.get("jsonl_path", "data/logs/conversations.jsonl")
        )

        # Состояние
        self.state = "idle"
        self._last_activity_t = time.monotonic()
        self._person_present = False

    # ────────────────────────────────────────────────────────
    def _init_voice(self) -> None:
        try:
            from .voice.stt import SpeechToText
            from .voice.tts import TextToSpeech
            self.stt = SpeechToText(self.cfg.voice.stt)
            self.tts = TextToSpeech(self.cfg.voice.tts)
        except Exception as e:
            logger.error(f"Не удалось инициализировать голос: {e}. "
                         "Переключаюсь в simulate-voice (stdin/print).")
            self.args.simulate_voice = True

    def _init_llm(self) -> None:
        from .llm.assistant import LLMAssistant
        try:
            self.llm = LLMAssistant(self.cfg.llm, self.dikidi)
        except Exception as e:
            logger.error(f"LLM недоступен ({e}). Использую echo-fallback.")
            self.llm = _EchoFallback()

    def _init_camera(self) -> None:
        try:
            from .camera.detector import CameraDetector
            self.camera = CameraDetector(self.cfg.camera)
        except Exception as e:
            logger.warning(f"Камера недоступна ({e}). Триггер по клавише.")
            self.camera = None

    # ────────────────────────────────────────────────────────
    async def run(self) -> None:
        # 1. UI в фоне
        ui_task = asyncio.create_task(self.ui.run())

        # 2. Камера / триггер
        if self.camera is not None:
            cam_task = asyncio.create_task(self._camera_loop())
        else:
            cam_task = asyncio.create_task(self._fake_camera_loop())

        # 3. Основной диалоговый цикл
        try:
            await self._dialog_loop()
        finally:
            self.running = False
            for t in (ui_task, cam_task):
                t.cancel()
            self.ui.cleanup()

    # ────────────────────────────────────────────────────────
    async def _camera_loop(self) -> None:
        """Опрашивает камеру и обновляет _person_present."""
        cooldown = float(self.cfg.camera.detection.get("cooldown_seconds", 2))
        lost_after = float(self.cfg.camera.detection.get("presence_lost_after", 3.0))
        last_seen = 0.0
        last_change = 0.0
        while self.running:
            try:
                present = await asyncio.to_thread(self.camera.detect_presence)
            except Exception as e:
                logger.warning(f"camera error: {e}")
                await asyncio.sleep(0.5)
                continue
            now = time.monotonic()
            if present:
                last_seen = now
                if not self._person_present and now - last_change > cooldown:
                    self._person_present = True
                    last_change = now
                    logger.info("👤 пациент появился")
            else:
                if self._person_present and now - last_seen > lost_after:
                    self._person_present = False
                    last_change = now
                    logger.info("👤 пациент ушёл")
            await asyncio.sleep(0.15)

    async def _fake_camera_loop(self) -> None:
        """Без камеры: первый раз — Space, потом каждые 30 сек reset."""
        logger.info("Триггер по клавиатуре: нажми Space в окне UI для старта.")
        self._person_present = True   # сразу впускаем
        while self.running:
            await asyncio.sleep(1.0)

    # ────────────────────────────────────────────────────────
    async def _dialog_loop(self) -> None:
        """Главный цикл состояний."""
        idle_timeout = float(self.cfg.timeouts.idle_return)
        warmup = float(self.cfg.timeouts.warmup_after_face)
        max_conv = float(self.cfg.timeouts.max_conversation)
        conv_started_at = 0.0
        was_present = False

        while self.running:
            await asyncio.sleep(0.1)

            # IDLE → GREETING
            if self.state == "idle":
                if self._person_present and not was_present:
                    was_present = True
                    await asyncio.sleep(warmup)
                    await self._enter_greeting()
                    conv_started_at = time.monotonic()
                continue

            # FAREWELL по уходу
            if not self._person_present and self.state != "idle":
                if was_present:
                    logger.info("→ FAREWELL: пациент ушёл")
                    await self._say(self._farewell_text(), who="bot")
                    self._go_idle()
                    was_present = False
                continue

            # Таймаут разговора
            if conv_started_at and time.monotonic() - conv_started_at > max_conv:
                logger.info("→ FAREWELL: разговор слишком долгий")
                await self._say("Простите, у меня прервалась связь. Если что — позовите снова.", who="bot")
                self._go_idle()
                continue

            # LISTENING — слушаем пациента
            if self.state == "listening":
                user_text = await self._listen()
                if not user_text:
                    # тишина idle_timeout секунд → idle
                    if time.monotonic() - self._last_activity_t > idle_timeout:
                        await self._say(self._farewell_text(short=True), who="bot")
                        self._go_idle()
                    continue
                self._last_activity_t = time.monotonic()

                self.ui.set_subtitle(f"вы: {user_text}", who="user")
                self.conv_logger.log_user(user_text)

                # → THINKING
                self.state = "thinking"
                self.ui.set_mode("thinking")
                reply = await self._think(user_text)

                # → SPEAKING
                await self._say(reply, who="bot")
                self.conv_logger.log_assistant(reply)

                # обратно на слух
                self.state = "listening"
                self.ui.set_mode("listening")

    # ────────────────────────────────────────────────────────
    async def _enter_greeting(self) -> None:
        self.state = "greeting"
        self.ui.set_mode("greeting")
        text = self.llm.prompts.get("greeting") if hasattr(self.llm, "prompts") else \
               "Здравствуйте, я Лена, администратор клиники Smile. Чем могу помочь?"
        await self._say(text or "Здравствуйте!", who="bot")
        self.conv_logger.log_assistant(text or "Здравствуйте!")
        self.state = "listening"
        self.ui.set_mode("listening")
        self._last_activity_t = time.monotonic()

    async def _listen(self) -> str:
        if self.args.simulate_voice:
            return await asyncio.to_thread(self._stdin_input)
        if self.stt is None:
            return ""
        return await self.stt.listen(timeout=int(self.cfg.timeouts.idle_return))

    def _stdin_input(self) -> str:
        try:
            sys.stdout.write("[simulate] вы: ")
            sys.stdout.flush()
            line = sys.stdin.readline()
            return line.strip()
        except Exception:
            return ""

    async def _think(self, user_text: str) -> str:
        try:
            return await self.llm.get_response(user_text)
        except Exception:
            logger.exception("LLM error")
            return "Простите, мне нужна минутка. Повторите, пожалуйста, ваш вопрос."

    async def _say(self, text: str, who: str = "bot") -> None:
        if not text:
            return
        self.ui.set_subtitle(text, who=who)
        self.ui.set_mode("speaking")
        if self.args.simulate_voice or self.tts is None:
            logger.info(f"[simulate TTS] {text}")
            # имитируем длительность речи ~ 0.06s/слово
            await asyncio.sleep(min(8.0, 0.06 * len(text.split()) + 0.5))
        else:
            await self.tts.speak(text, ui_display=self.ui)
        self.ui.set_mode("listening")

    def _farewell_text(self, short: bool = False) -> str:
        if short:
            return "Если что — я рядом, позовите. Хорошего дня!"
        return "Спасибо, что выбрали нашу клинику. Хорошего дня, до встречи!"

    def _go_idle(self) -> None:
        self.state = "idle"
        self.ui.set_mode("idle")
        self.ui.clear_subtitle()
        if hasattr(self.llm, "reset_conversation"):
            self.llm.reset_conversation()


# ────────────────────────────────────────────────────────────
class _EchoFallback:
    """Дегенерат-«LLM» если Ollama недоступен — чтобы UI/TTS работали для проверки."""
    prompts: dict = {}

    async def get_response(self, text: str, *_):
        return "Я вас услышала. Сейчас передам администратору."

    def reset_conversation(self) -> None:
        pass


# ────────────────────────────────────────────────────────────
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smile.AI оффлайн-демо (без DIKIDI)")
    p.add_argument("--config", default="config/settings.yaml")
    p.add_argument("--no-camera", action="store_true",
                   help="отключить камеру (триггер по Space)")
    p.add_argument("--windowed", action="store_true",
                   help="оконный режим 1280×720 вместо fullscreen")
    p.add_argument("--simulate-voice", action="store_true",
                   help="без микрофона/TTS: ввод/вывод текстом в stdin/stdout")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config(args.config)
    setup_logging(cfg)
    logger.info(f"=== Smile.AI offline-demo v{cfg.app.version} ===")
    if args.simulate_voice:
        logger.warning("simulate-voice: реальный микрофон и TTS отключены")
    app = OfflineApp(args, cfg)
    loop = asyncio.new_event_loop()

    def _stop(*_):
        app.running = False
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(app.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
