"""
Mock версия STT для тестирования без Whisper
"""
import asyncio

from loguru import logger


class SpeechToText:
    """Mock распознавание речи"""

    def __init__(self, config):
        self.config = config
        logger.success("Mock STT инициализирован (без Whisper)")

        # Предопределенные фразы для симуляции
        self.mock_phrases = [
            "Здравствуйте, хочу записаться на маникюр",
            "Какие у вас есть свободные окна на завтра?",
            "Сколько стоит стрижка?",
            "Запишите меня на 15:00",
            "Спасибо, до свидания"
        ]
        self.phrase_index = 0

    async def listen(self, timeout: int = 30) -> str:
        """
        Симулирует прослушивание речи
        """
        logger.info("🎤 Mock: Слушаю... (симуляция)")

        # Имитация задержки
        await asyncio.sleep(2)

        # Возвращаем следующую фразу из списка
        text = self.mock_phrases[self.phrase_index % len(self.mock_phrases)]
        self.phrase_index += 1

        logger.success(f"✅ Mock распознано: {text}")
        return text
