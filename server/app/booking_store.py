"""
Заявки на запись, которые Оливия собирает голосом за день.

Каждая заявка — то, что пациент назвал (имя, телефон, удобное время), и что
Оливия ЗАЧИТАЛА ему обратно для подтверждения перед тем, как отдать это
серверу (см. промпт: телефон повторяется по цифрам и подтверждается).
Дополнительно перепроверяем телефон здесь: STT иногда ошибается даже после
подтверждения пациентом, а восстановить контакт потом будет уже нельзя.

Файлы — по дням, как в conversation_log.py: data/bookings/ГГГГ-ММ-ДД.jsonl.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger

_DIGIT_RE = re.compile(r"\d")

# Разговорное «удобное время» → часть дня. Оливия не назначает точные слоты
# (см. dikidi_readonly.py — это делает администратор), поэтому это не
# расписание с точным временем, а порядок обзвона.
_MORNING_WORDS = ("утр", "с утра")
_AFTERNOON_WORDS = ("днём", "днем", "обед", "полдень")
_EVENING_WORDS = ("вечер",)
_HOUR_RE = re.compile(r"\b([01]?\d|2[0-3])\s*(?:[:.\-]\d{2})?\s*(?:ч\b|час)?")

BUCKET_ORDER = ("утро", "день", "вечер", "не указано")


def normalize_ru_phone(raw: str) -> tuple[str | None, bool]:
    """
    Приводит надиктованный голосом номер к виду «+7 921 555-12-34».

    Возвращает (номер_или_None, валиден_ли). Валиден = ровно 11 цифр,
    первая — 7 или 8 (приводим к 7), либо 10 цифр без кода страны.
    Если формат не распознан — возвращаем исходный текст с valid=False,
    чтобы заявка не терялась целиком, а администратор перепроверил номер сам.
    """
    digits = "".join(_DIGIT_RE.findall(raw or ""))
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    valid = len(digits) == 11 and digits[0] == "7"
    if not valid:
        cleaned = (raw or "").strip()
        return (cleaned or None), False
    formatted = f"+{digits[0]} {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return formatted, True


def time_bucket(preferred_time: str) -> str:
    """Грубо раскладывает свободный текст «удобного времени» по частям дня."""
    text = (preferred_time or "").lower()
    m = _HOUR_RE.search(text)
    if m:
        try:
            hour = int(m.group(1))
        except ValueError:
            hour = None
        if hour is not None:
            if hour < 12:
                return "утро"
            if hour < 17:
                return "день"
            return "вечер"
    if any(w in text for w in _MORNING_WORDS):
        return "утро"
    if any(w in text for w in _AFTERNOON_WORDS):
        return "день"
    if any(w in text for w in _EVENING_WORDS):
        return "вечер"
    return "не указано"


@dataclass
class BookingRequest:
    name: str
    phone_raw: str
    preferred_time: str
    note: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    phone: str | None = field(default=None, init=True)
    phone_valid: bool = field(default=False, init=True)

    def __post_init__(self) -> None:
        self.phone, self.phone_valid = normalize_ru_phone(self.phone_raw)


class BookingStore:
    def __init__(self, base_dir: str = "data/bookings"):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def _file_for(self, day: datetime) -> Path:
        return self.base / f"{day:%Y-%m-%d}.jsonl"

    def add(self, booking: BookingRequest) -> None:
        path = self._file_for(datetime.now())
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(booking), ensure_ascii=False) + "\n")
            logger.info(f"📝 Заявка сохранена: {booking.name} / {booking.phone_raw}")
        except Exception as e:
            logger.error(f"Не смог записать заявку: {e}")

    def for_day(self, day: datetime | None = None) -> list[BookingRequest]:
        path = self._file_for(day or datetime.now())
        if not path.exists():
            return []
        out: list[BookingRequest] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(BookingRequest(**json.loads(line)))
            except Exception as e:
                logger.warning(f"Пропускаю битую строку заявки: {e}")
        return out
