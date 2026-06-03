"""
Mock версия LLM для тестирования без Ollama
"""
import asyncio

from loguru import logger


class LLMAssistant:
    """Mock интеграция с LLM"""

    def __init__(self, config):
        self.config = config
        self.conversation_history = []

        # Предопределенные ответы
        self.mock_responses = {
            "маникюр": "Конечно! У нас есть классический маникюр за 1500 рублей и аппаратный за 2000 рублей. Какой вас интересует?",
            "свободн": "У нас есть свободные окна завтра в 10:00, 14:00 и 16:30. Какое время вам удобно?",
            "стоимость": "Стрижка женская стоит 2500 рублей, мужская - 1500 рублей. Окрашивание от 3000 рублей.",
            "запис": "Отлично! Записываю вас. Подскажите, пожалуйста, ваше имя и номер телефона?",
            "спасибо": "Пожалуйста! Будем рады видеть вас снова!",
            "default": "Понял вас. Чем еще могу помочь?"
        }

        logger.success("Mock LLM инициализирован (без Ollama)")

    async def get_response(self, user_message: str, dikidi_client) -> str:
        """
        Генерирует mock ответ на основе ключевых слов
        """
        logger.info("🤖 Mock LLM обрабатывает запрос...")

        # Имитация задержки обработки
        await asyncio.sleep(1)

        # Добавляем в историю
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Поиск подходящего ответа по ключевым словам
        user_lower = user_message.lower()
        response = self.mock_responses["default"]

        for keyword, mock_response in self.mock_responses.items():
            if keyword in user_lower:
                response = mock_response
                break

        # Добавляем ответ в историю
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })

        return response

    def reset_conversation(self):
        """Сброс истории разговора"""
        self.conversation_history = []
        logger.info("История разговора сброшена")
