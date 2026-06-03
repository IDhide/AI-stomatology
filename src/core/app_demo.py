"""
Демо версия приложения с mock модулями
"""
import asyncio
from enum import Enum

from loguru import logger

# Используем mock версии модулей
from camera.detector_mock import PersonDetector
from core.conversation_logger import ConversationLogger
from dikidi.client_mock import DikidiClient
from llm.assistant_mock import LLMAssistant
from ui.display_mock import UIDisplay
from voice.stt_mock import SpeechToText
from voice.tts_mock import TextToSpeech


class AppState(Enum):
    """Состояния приложения"""
    IDLE = "idle"
    DETECTING = "detecting"
    GREETING = "greeting"
    CONVERSATION = "conversation"
    GOODBYE = "goodbye"


class SalonAssistant:
    """Демо версия AI-ассистента с mock модулями"""

    def __init__(self, config):
        self.config = config
        self.state = AppState.IDLE
        self.running = False

        logger.info("Инициализация DEMO версии с mock модулями...")

        self.detector = PersonDetector(config.camera)
        self.stt = SpeechToText(config.voice.stt)
        self.tts = TextToSpeech(config.voice.tts)
        self.llm = LLMAssistant(config.llm)
        self.dikidi = DikidiClient(config.dikidi)
        self.ui = UIDisplay(config.ui)
        self.conv_logger = ConversationLogger(config.logging.conversations)

        self.last_activity = None
        self.conversation_id = None
        self.conversation_turns = 0  # Счетчик реплик для демо

        logger.success("Все mock модули инициализированы")

    async def run(self):
        """Основной цикл приложения"""
        self.running = True
        logger.info("🚀 Запуск демо режима")

        ui_task = asyncio.create_task(self.ui.run())

        try:
            while self.running:
                if self.state == AppState.IDLE:
                    await self._handle_idle_state()
                elif self.state == AppState.DETECTING:
                    await self._handle_detecting_state()
                elif self.state == AppState.GREETING:
                    await self._handle_greeting_state()
                elif self.state == AppState.CONVERSATION:
                    await self._handle_conversation_state()
                elif self.state == AppState.GOODBYE:
                    await self._handle_goodbye_state()

                await asyncio.sleep(0.5)
        finally:
            ui_task.cancel()

    async def _handle_idle_state(self):
        """Режим ожидания"""
        self.ui.set_mode("idle")
        logger.info("💤 Режим ожидания (показываем медуз)...")

        await asyncio.sleep(2)

        # В демо режиме автоматически "обнаруживаем" человека
        logger.info("👤 [DEMO] Симулируем появление клиента")
        self.state = AppState.DETECTING

    async def _handle_detecting_state(self):
        """Подтверждение присутствия"""
        logger.info("🔍 Подтверждение присутствия...")
        await asyncio.sleep(1)

        logger.info("✅ Присутствие подтверждено")
        self.state = AppState.GREETING
        self.conversation_id = self.conv_logger.start_conversation()
        self.conversation_turns = 0

    async def _handle_greeting_state(self):
        """Приветствие клиента"""
        self.ui.set_mode("speaking")

        greeting = "Здравствуйте! Я виртуальный администратор салона. Чем могу помочь?"
        logger.info(f"🗣️ Приветствие: {greeting}")

        await self.tts.speak(greeting, self.ui)
        self.conv_logger.log_message(self.conversation_id, "assistant", greeting)

        self.state = AppState.CONVERSATION
        self.last_activity = asyncio.get_event_loop().time()

    async def _handle_conversation_state(self):
        """Основной разговор"""
        # В демо режиме ограничиваем количество реплик
        if self.conversation_turns >= 3:
            logger.info("👋 [DEMO] Завершаем разговор после 3 реплик")
            self.state = AppState.GOODBYE
            return

        # Слушаем клиента (mock)
        self.ui.set_mode("listening")
        user_text = await self.stt.listen()

        if user_text:
            logger.info(f"👤 Клиент: {user_text}")
            self.conv_logger.log_message(self.conversation_id, "user", user_text)
            self.conversation_turns += 1

            # Получаем ответ от LLM
            self.ui.set_mode("thinking")
            response = await self.llm.get_response(user_text, self.dikidi)

            logger.info(f"🤖 Ассистент: {response}")
            self.conv_logger.log_message(self.conversation_id, "assistant", response)

            # Произносим ответ
            self.ui.set_mode("speaking")
            await self.tts.speak(response, self.ui)

    async def _handle_goodbye_state(self):
        """Прощание с клиентом"""
        await asyncio.sleep(1)

        self.ui.set_mode("speaking")

        goodbye = "До свидания! Будем рады видеть вас снова!"
        logger.info(f"👋 Прощание: {goodbye}")

        await self.tts.speak(goodbye, self.ui)
        self.conv_logger.log_message(self.conversation_id, "assistant", goodbye)
        self.conv_logger.end_conversation(self.conversation_id)

        logger.success("✅ Демо сессия завершена")
        self.running = False  # Останавливаем демо

    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("Завершение работы приложения...")
        self.running = False

        self.detector.cleanup()
        self.ui.cleanup()
        await self.dikidi.close()

        logger.success("Все ресурсы освобождены")
