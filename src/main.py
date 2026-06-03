#!/usr/bin/env python3
"""
Главный модуль AI-ассистента администратора
"""
import asyncio
import signal
import sys
from pathlib import Path

from loguru import logger

from core.app import SalonAssistant
from core.config import load_config


def setup_logging(config):
    """Настройка логирования"""
    logger.remove()
    
    # Консольный вывод
    if config.logging.console:
        logger.add(
            sys.stderr,
            level=config.logging.level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
        )
    
    # Файловый вывод
    if config.logging.file.enabled:
        log_path = Path(config.logging.file.path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_path,
            level=config.logging.level,
            rotation=config.logging.file.max_size,
            retention=config.logging.file.backup_count,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}"
        )


async def main():
    """Основная функция"""
    # Загрузка конфигурации
    config = load_config()
    setup_logging(config)
    
    logger.info("🚀 Запуск AI Администратора Салона Красоты")
    logger.info(f"Версия: {config.app.version}")
    
    # Создание экземпляра приложения
    assistant = SalonAssistant(config)
    
    # Обработка сигналов завершения
    def signal_handler(sig, frame):
        logger.info("Получен сигнал завершения, останавливаем приложение...")
        asyncio.create_task(assistant.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Запуск приложения
        await assistant.run()
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        return 1
    finally:
        await assistant.shutdown()
    
    logger.info("👋 Приложение завершено")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
