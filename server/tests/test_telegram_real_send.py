"""
Интеграционный тест: реальная отправка сводки в Telegram.

Запуск:
    cd server && ../.venv/bin/python -m pytest tests/test_telegram_real_send.py -v

Перед запуском в .env должны быть заданы TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from server.app.booking_store import BookingRequest, BookingStore
from server.app.config import get_settings
from server.app.telegram_notify import TelegramNotifier, format_requests_message, format_schedule_message


@pytest.mark.asyncio
async def test_real_telegram_digest():
    """Отправляет в Telegram пробную сводку с заявками на запись."""
    cfg = get_settings()
    assert cfg.has_telegram, "TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID должны быть заданы в server/.env"

    store = BookingStore(cfg.bookings_dir)

    # Добавляем тестовые заявки за сегодня
    test_bookings = [
        BookingRequest(name="Анна", phone_raw="89215551234", preferred_time="утром", note="Тестовая заявка 1"),
        BookingRequest(name="Дмитрий", phone_raw="плохо расслышала номер", preferred_time="после 18", note="Тестовая заявка 2 — номер не распознан"),
        BookingRequest(name="Елена", phone_raw="89215559876", preferred_time="днём", note="Тестовая заявка 3"),
    ]
    for b in test_bookings:
        store.add(b)

    notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id, store)
    assert notifier.enabled

    # 1. Сводка с кнопками (то, что приходит раз в день)
    await notifier.send_digest()

    # 2. Сразу пришлём содержимое обеих кнопок, чтобы проверить форматирование
    bookings = store.for_day()
    await notifier._call(
        "sendMessage",
        chat_id=cfg.telegram_chat_id,
        text=format_requests_message(bookings),
    )
    await notifier._call(
        "sendMessage",
        chat_id=cfg.telegram_chat_id,
        text=format_schedule_message(bookings),
    )

    print(f"✅ Сообщения отправлены в чат {cfg.telegram_chat_id} в {datetime.now():%H:%M:%S}")
