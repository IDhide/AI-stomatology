"""
Mock версия TTS для тестирования без синтеза речи
"""
import asyncio
from loguru import logger


class TextToSpeech:
    """Mock синтез речи"""
    
    def __init__(self, config):
        self.config = config
        logger.success("Mock TTS инициализирован (без Silero)")
    
    async def speak(self, text: str, ui_display=None):
        """
        Симулирует произнесение текста
        """
        if not text:
            return
        
        logger.info(f"🔊 Mock произношу: {text}")
        
        # Имитация времени произнесения (примерно 0.1 сек на символ)
        duration = len(text) * 0.05
        
        if ui_display:
            ui_display.start_speaking_animation()
        
        await asyncio.sleep(min(duration, 5))  # Максимум 5 секунд
        
        if ui_display:
            ui_display.stop_speaking_animation()
        
        logger.success("✅ Mock произнесено")
