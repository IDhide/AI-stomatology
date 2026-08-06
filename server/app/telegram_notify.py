"""
Телеграм-бот для администратора клиники.

Раз в день (после закрытия, см. TELEGRAM_DIGEST_TIME) присылает сводку
заявок на запись, которые Оливия собрала за день, с двумя кнопками:

    📋 Заявки на запись        — сырой список (кто, телефон, когда удобно)
    🗓 Рекомендуемое расписание — тот же список, сгруппированный по частям
                                  дня, чтобы администратору было удобно
                                  обзванивать по порядку

Оливия НЕ бронирует слоты (см. dikidi_readonly.py) — поэтому «расписание»
это порядок звонков администратора, а не точное время приёма.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
from loguru import logger

from .booking_store import BUCKET_ORDER, BookingRequest, BookingStore, time_bucket

_API = "https://api.telegram.org/bot{token}/{method}"


def _format_entry(i: int, b: BookingRequest) -> str:
    phone = b.phone or b.phone_raw or "—"
    warn = "" if b.phone_valid else " ⚠️ проверить номер"
    note = f" — {b.note}" if b.note else ""
    return f"{i}. {b.name or 'без имени'} — {phone}{warn}\n   «{b.preferred_time or 'не указано'}»{note}"


def format_requests_message(bookings: list[BookingRequest]) -> str:
    if not bookings:
        return "Сегодня заявок на запись не было."
    lines = [f"📋 Заявки на запись за {datetime.now():%d.%m.%Y} ({len(bookings)}):", ""]
    lines += [_format_entry(i, b) for i, b in enumerate(bookings, 1)]
    return "\n".join(lines)


def format_schedule_message(bookings: list[BookingRequest]) -> str:
    if not bookings:
        return "Сегодня заявок нет — расписание пустое."
    groups: dict[str, list[BookingRequest]] = {k: [] for k in BUCKET_ORDER}
    for b in bookings:
        groups[time_bucket(b.preferred_time)].append(b)
    lines = [f"🗓 Рекомендуемый порядок звонков на {datetime.now():%d.%m.%Y}:", ""]
    n = 0
    for bucket in BUCKET_ORDER:
        entries = groups[bucket]
        if not entries:
            continue
        lines.append(f"— {bucket.upper()} —")
        for b in entries:
            n += 1
            lines.append(_format_entry(n, b))
        lines.append("")
    lines.append("Точное время приёма согласовывает администратор по звонку.")
    return "\n".join(lines).strip()


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, store: BookingStore):
        self.token = token
        self.chat_id = chat_id
        self.store = store
        self.enabled = bool(token and chat_id)
        self._offset = 0

    async def _call(self, method: str, **params) -> dict:
        url = _API.format(token=self.token, method=method)
        async with httpx.AsyncClient(timeout=35.0) as client:
            r = await client.post(url, json=params)
            r.raise_for_status()
            return r.json()

    async def send_digest(self) -> None:
        if not self.enabled:
            return
        count = len(self.store.for_day())
        text = (
            f"Сводка за {datetime.now():%d.%m.%Y}: заявок на запись — {count}.\n"
            "Выберите, что показать:"
        )
        keyboard = {
            "inline_keyboard": [[
                {"text": "📋 Заявки на запись", "callback_data": "bookings:list"},
                {"text": "🗓 Рекомендуемое расписание", "callback_data": "bookings:schedule"},
            ]]
        }
        try:
            await self._call("sendMessage", chat_id=self.chat_id, text=text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Telegram: не смог отправить сводку: {e}")

    async def _handle_callback(self, cb: dict) -> None:
        data = cb.get("data", "")
        chat_id = cb["message"]["chat"]["id"]
        bookings = self.store.for_day()
        if data == "bookings:list":
            text = format_requests_message(bookings)
        elif data == "bookings:schedule":
            text = format_schedule_message(bookings)
        else:
            text = "Не понимаю эту кнопку."
        try:
            await self._call("answerCallbackQuery", callback_query_id=cb["id"])
            await self._call("sendMessage", chat_id=chat_id, text=text)
        except Exception as e:
            logger.error(f"Telegram: ошибка обработки кнопки: {e}")

    async def run_updates_loop(self) -> None:
        """Долгий поллинг getUpdates — обрабатывает нажатия кнопок."""
        if not self.enabled:
            return
        logger.info("Telegram: слушаю нажатия кнопок")
        while True:
            try:
                resp = await self._call(
                    "getUpdates", offset=self._offset, timeout=25,
                    allowed_updates=["callback_query"],
                )
                for update in resp.get("result", []):
                    self._offset = update["update_id"] + 1
                    cb = update.get("callback_query")
                    if cb:
                        await self._handle_callback(cb)
            except Exception as e:
                logger.error(f"Telegram: getUpdates упал, жду 5с ({e})")
                await asyncio.sleep(5)

    @staticmethod
    def _parse_digest_time(digest_time: str) -> tuple[int, int]:
        hour_s, _, minute_s = digest_time.partition(":")
        try:
            return int(hour_s), int(minute_s or 0)
        except ValueError:
            logger.warning(f"TELEGRAM_DIGEST_TIME='{digest_time}' не похоже на ЧЧ:ММ, беру 21:00")
            return 21, 0

    async def run_daily_digest_loop(self, digest_time: str) -> None:
        """Раз в сутки, в digest_time (ЧЧ:ММ, локальное время сервера),
        шлёт сводку за день с кнопками."""
        if not self.enabled:
            return
        hour, minute = self._parse_digest_time(digest_time)
        while True:
            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            await self.send_digest()
