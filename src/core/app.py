"""
Основной класс приложения - оркестратор всех модулей
"""
import asyncio
from enum import Enum
from typing import Optional

from loguru import logger

from camera.detector import PersonDetector
from voice.stt import SpeechToText
from voice.tts import TextToSpeech
from llm.assistant import LLMAssistant
from dikidi.client import DikidiClient
from ui.display import UIDisplay
from core.conversation_logger import ConversationLogger


class AppState(Enum):
    """Состояния приложения"""
    IDLE = "idle"  # Режим ожидания (медузы)
    DETECTING = "detecting"  # Обнаружен человек
    GREETING = "greeting"  # Приветствие
    CONVERSATION = "conversation"  # Разговор
    GOODBYE = "goodbye"  # Прощание


class SalonAssistant:
    """Главный класс AI-ассистента"""
    
    def __init__(self, config):
        self.config = config
        self.state = AppState.IDLE
        self.running = False
        
        # Инициализация модулей
        logger.info("Инициализация модулей...")
        
        self.detector = PersonDetector(config.camera)
        self.stt = SpeechToText(config.voice.stt)
        self.tts = TextToSpeech(config.voice.tts)
        self.llm = LLMAssistant(config.llm)
        self.dikidi = DikidiClient(config.dikidi)
        self.ui = UIDisplay(config.ui)
        self.conv_logger = ConversationLogger(config.logging.conversations)
        
        # Таймеры
        self.last_activity = None
        self.conversation_id = None
        
        logger.success("Все модули инициализированы")
    
    async def run(self):
        """Основной цикл приложения"""
        self.running = True
        logger.info("Запуск основного цикла")
        
        # Запуск UI в отдельной задаче
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
                
                await asyncio.sleep(0.1)
        finally:
            ui_task.cancel()
    
    async def _handle_idle_state(self):
        """Режим ожидания - показываем медуз"""
        self.ui.set_mode("idle")
        
        # Проверяем детекцию человека
        if self.detector.detect_person():
            logger.info("👤 Обнаружен человек!")
            self.state = AppState.DETECTING
    
    async def _handle_detecting_state(self):
        """Подтверждение присутствия человека"""
        await asyncio.sleep(self.config.camera.detection["cooldown_seconds"])
        
        if self.detector.detect_person():
            logger.info("✅ Присутствие подтверждено, переход к приветствию")
            self.state = AppState.GREETING
            self.conversation_id = self.conv_logger.start_conversation()
        else:
            logger.info("❌ Ложное срабатывание, возврат в режим ожидания")
            self.state = AppState.IDLE
    
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
        # Проверка таймаута
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_activity > self.config.timeouts.idle_return:
            logger.info("⏱️ Таймаут бездействия, возврат в режим ожидания")
            self.state = AppState.IDLE
            self.conv_logger.end_conversation(self.conversation_id)
            return
        
        # Проверка ухода клиента
        if not self.detector.detect_person():
            logger.info("👋 Клиент ушел, прощаемся")
            self.state = AppState.GOODBYE
            return
        
        # Слушаем клиента
        self.ui.set_mode("listening")
        user_text = await self.stt.listen()
        
        if user_text:
            logger.info(f"👤 Клиент: {user_text}")
            self.conv_logger.log_message(self.conversation_id, "user", user_text)
            self.last_activity = current_time
            
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
        await asyncio.sleep(self.config.timeouts.goodbye_delay)
        
        # Активация из режима ожидания
        self.ui.set_mode("speaking")
        
        goodbye = "До свидания! Будем рады видеть вас снова!"
        logger.info(f"👋 Прощание: {goodbye}")
        
        await self.tts.speak(goodbye, self.ui)
        self.conv_logger.log_message(self.conversation_id, "assistant", goodbye)
        self.conv_logger.end_conversation(self.conversation_id)
        
        self.state = AppState.IDLE
    
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("Завершение работы приложения...")
        self.running = False
        
        self.detector.cleanup()
        self.ui.cleanup()
        
        logger.success("Все ресурсы освобождены")
