#!/usr/bin/env python3
"""
Демо версия AI-ассистента с mock модулями (без камеры, голоса, UI)
"""
import asyncio
import signal
import sys
from pathlib import Path

from loguru import logger

from core.app_demo import SalonAssistant
from core.config import load_config


def setup_logging(config):
    """Настройка логирования"""
    logger.remove()
    
    # Консольный вывод
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
    )


async def main():
    """Основная функция"""
    config = load_config()
    setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("🚀 AI Администратор Салона Красоты - DEMO РЕЖИМ")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Это демо версия без реальной камеры, голоса и UI")
    logger.info("Используются mock модули для симуляции работы")
    logger.info("")
    
    assistant = SalonAssistant(config)
    
    def signal_handler(sig, frame):
        logger.info("Получен сигнал завершения...")
        asyncio.create_task(assistant.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await assistant.run()
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        return 1
    finally:
        await assistant.shutdown()
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("👋 Демо завершено!")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
