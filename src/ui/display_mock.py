"""
Mock версия UI для тестирования без Pygame
"""
import asyncio

from loguru import logger


class UIDisplay:
    """Mock визуальный интерфейс"""

    def __init__(self, config):
        self.config = config
        self.mode = "idle"
        self.running = False
        logger.success("Mock UI инициализирован (без Pygame)")

    async def run(self):
        """Основной цикл отрисовки UI"""
        self.running = True
        logger.info("Mock UI запущен")

        while self.running:
            await asyncio.sleep(1)

    def set_mode(self, mode: str):
        """Установка режима отображения"""
        if mode != self.mode:
            logger.debug(f"Mock UI режим: {self.mode} -> {mode}")
            self.mode = mode

    def start_speaking_animation(self):
        """Запуск анимации речи"""
        self.set_mode("speaking")

    def stop_speaking_animation(self):
        """Остановка анимации речи"""
        pass

    def cleanup(self):
        """Освобождение ресурсов"""
        self.running = False
        logger.info("Mock UI ресурсы освобождены")
