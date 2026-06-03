#!/usr/bin/env python3
"""
Главный модуль AI-ассистента стоматологии (production)

Запуск:
    uv run python -m src.main
    python -m src.main
"""
import asyncio
import signal
import sys
from pathlib import Path

from loguru import logger

# Относительные импорты — проект запускается как пакет (-m src.main)
from .core.app import SalonAssistant
from .core.config import load_config


def setup_logging(config) -> None:
    """Настройка loguru-логирования из конфига."""
    logger.remove()

    if config.logging.console:
        logger.add(
            sys.stderr,
            level=config.logging.level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
                "<level>{message}</level>"
            ),
            colorize=True,
        )

    log_file_cfg = config.logging.file or {}
    if log_file_cfg.get("enabled", True):
        log_path = Path(log_file_cfg.get("path", "data/logs/app.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_path),
            level=config.logging.level,
            rotation=log_file_cfg.get("max_size", "10MB"),
            retention=int(log_file_cfg.get("backup_count", 5)),
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        )


async def main() -> int:
    """Точка входа production-режима."""
    config = load_config()
    setup_logging(config)

    logger.info("🚀 Запуск Smile.AI — стоматологический ассистент")
    logger.info(f"Версия: {config.app.version}  |  Клиника: {config.app.clinic_name}")

    assistant = SalonAssistant(config)

    loop = asyncio.get_running_loop()

    def _stop(sig_name: str) -> None:
        logger.info(f"Получен сигнал {sig_name}, завершаем работу…")
        loop.create_task(assistant.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: _stop(s))
        except NotImplementedError:
            # Windows не поддерживает add_signal_handler
            signal.signal(sig, lambda *_: _stop(sig.name))

    try:
        await assistant.run()
    except Exception:
        logger.exception("Критическая ошибка — приложение аварийно завершено")
        return 1
    finally:
        await assistant.shutdown()

    logger.info("👋 Приложение завершено штатно")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
