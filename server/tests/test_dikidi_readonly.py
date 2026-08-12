"""
tests/test_dikidi_readonly.py
Расчёт свободных окон для записи (демо-режим, без сети).
"""
from datetime import datetime, timedelta

import pytest

from server.app.dikidi_readonly import DikidiReadOnly


@pytest.mark.asyncio
async def test_free_slots_tomorrow_around_demo_busy():
    """Демо-завтра занято 12:00–13:00, 14:00–15:30, 17:00–18:00.
    Сетка 30 мин, визит 60 мин, клиника 12:00–21:00."""
    dikidi = DikidiReadOnly(demo=True)
    slots = await dikidi.free_slots(days=2)

    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    assert tomorrow in slots
    assert slots[tomorrow] == [
        "13:00", "15:30", "16:00", "18:00", "18:30", "19:00", "19:30", "20:00",
    ]


@pytest.mark.asyncio
async def test_today_slots_never_in_the_past():
    """Сегодня не предлагаем окна раньше чем через час от текущего момента."""
    dikidi = DikidiReadOnly(demo=True)
    slots = await dikidi.free_slots(days=1)

    today = datetime.now().date().isoformat()
    earliest = datetime.now() + timedelta(hours=1)
    for s in slots[today]:
        h, m = int(s[:2]), int(s[3:])
        assert h * 60 + m >= earliest.hour * 60 + earliest.minute


@pytest.mark.asyncio
async def test_format_for_prompt_lists_free_slots():
    dikidi = DikidiReadOnly(demo=True)
    bookings = await dikidi.today_bookings()
    slots = await dikidi.free_slots(days=2)
    text = DikidiReadOnly.format_for_prompt(bookings, dikidi.available, free_slots=slots)

    assert "СВОБОДНЫЕ ОКНА ДЛЯ ЗАПИСИ" in text
    assert "завтра" in text or "сегодня" in text
    assert "НИКОГДА не подтверждай запись" in text


@pytest.mark.asyncio
async def test_api_failure_marks_day_unknown_not_free(monkeypatch):
    """Если API упал, день НЕ показываем полностью свободным — это ложь."""
    dikidi = DikidiReadOnly(api_key="k", company_id="1")

    async def boom(date_from, date_to):
        raise RuntimeError("API 404")

    monkeypatch.setattr(dikidi, "_fetch_bookings", boom)
    slots = await dikidi.free_slots(days=2)

    assert all(v is None for v in slots.values())
    text = DikidiReadOnly.format_for_prompt([], dikidi.available, free_slots=slots)
    assert "данных нет" in text
