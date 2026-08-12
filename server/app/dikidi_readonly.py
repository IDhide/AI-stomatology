"""
DIKIDI — доступ ТОЛЬКО НА ЧТЕНИЕ.

Оливия может посмотреть записи и свободные окна и подсказать пациенту
время его записи или предложить ближайшее свободное время («в десять
занято, могу предложить в двенадцать»). Создавать, переносить и отменять
записи Оливия НЕ может — это делает только живой администратор.

Без DIKIDI-ключей работает на демо-данных, чтобы сценарий можно было
проверить на MacBook прямо сейчас.

ВАЖНО: точный формат боевого API DIKIDI уточняется по документации из
кабинета (Настройки → Интеграция → создать ключ). Вся работа с HTTP
собрана в _fetch_bookings() — при получении ключа правится только она.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from loguru import logger

# Демо-записи (только при DIKIDI_DEMO=true — для теста сценария).
# Ключ — смещение дня от сегодня: 0 = сегодня, 1 = завтра.
# Каждая запись занимает час.
_DEMO_BUSY: dict[int, list[dict]] = {
    0: [
        {"start": "15:00", "end": "16:00", "client": "Анна", "service": "консультация терапевта"},
        {"start": "16:30", "end": "17:30", "client": "Дмитрий", "service": "чистка зубов"},
        {"start": "18:00", "end": "19:00", "client": "Мария", "service": "лечение канала"},
    ],
    1: [
        {"start": "12:00", "end": "13:00", "client": "Ольга", "service": "осмотр"},
        {"start": "14:00", "end": "15:30", "client": "Игорь", "service": "протезирование"},
        {"start": "17:00", "end": "18:00", "client": "Светлана", "service": "чистка зубов"},
    ],
}


def _to_min(hhmm: str) -> int:
    """«15:30» → минуты от полуночи."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class DikidiReadOnly:
    def __init__(
        self,
        api_key: str = "",
        company_id: str = "",
        base_url: str = "https://api.dikidi.net",
        demo: bool = False,
        *,
        work_start: str = "12:00",
        work_end: str = "21:00",
        slot_minutes: int = 60,
        grid_minutes: int = 30,
    ):
        self.api_key = api_key
        self.company_id = company_id
        self.base_url = base_url.rstrip("/")
        self.demo = demo and not (api_key and company_id)
        self.work_start = work_start
        self.work_end = work_end
        self.slot_minutes = slot_minutes
        self.grid_minutes = grid_minutes
        if api_key and company_id:
            self.enabled = True
        else:
            self.enabled = False
            if self.demo:
                logger.warning("DIKIDI: ключей нет, DIKIDI_DEMO=true — демо-записи")
            else:
                logger.info("DIKIDI: не подключён — Оливия работает без расписания")

    @property
    def available(self) -> bool:
        """Есть ли у Оливии хоть какие-то данные о записях."""
        return self.enabled or self.demo

    # ── данные ───────────────────────────────────────────────────────
    async def today_bookings(self) -> list[dict]:
        """Записи на сегодня: [{time, client, service}, ...]."""
        busy = await self._busy_for_day(0)
        return [
            {"time": b["start"], "client": b.get("client", ""), "service": b.get("service", "")}
            for b in busy
        ]

    async def free_slots(self, days: int = 2) -> dict[str, list[str]]:
        """
        Свободные окна на ближайшие дни: {"2026-08-12": ["12:00", ...]}.
        Окно = начало визита по сетке grid_minutes, визит длится slot_minutes
        и не должен пересекаться с занятыми интервалами и закрытием клиники.
        """
        result: dict[str, list[str]] = {}
        now = datetime.now()
        for offset in range(days):
            day = now.date() + timedelta(days=offset)
            busy = await self._busy_for_day(offset)
            busy_min = [(_to_min(b["start"]), _to_min(b["end"])) for b in busy]
            slots: list[str] = []
            start = _to_min(self.work_start)
            end = _to_min(self.work_end) - self.slot_minutes
            # сегодня предлагаем только с запасом в час от текущего момента
            earliest = (now.hour * 60 + now.minute + 60) if offset == 0 else 0
            t = start
            while t <= end:
                overlaps = any(bs < t + self.slot_minutes and t < be for bs, be in busy_min)
                if not overlaps and t >= earliest:
                    slots.append(_to_hhmm(t))
                t += self.grid_minutes
            result[day.isoformat()] = slots
        return result

    async def _busy_for_day(self, day_offset: int) -> list[dict]:
        """Занятые интервалы дня: [{start, end, client, service}]."""
        if not self.enabled:
            return list(_DEMO_BUSY.get(day_offset, [])) if self.demo else []
        day = (datetime.now().date() + timedelta(days=day_offset)).isoformat()
        try:
            records = await self._fetch_bookings(day, day)
        except Exception as e:
            logger.error(f"DIKIDI: не смог получить записи на {day}: {e}")
            return []
        busy = []
        for item in records:
            start = item.get("time", "")
            if not start:
                continue
            end = item.get("time_end") or _to_hhmm(_to_min(start) + self.slot_minutes)
            busy.append({
                "start": start,
                "end": end,
                "client": item.get("client_name", ""),
                "service": item.get("service_name", ""),
            })
        return busy

    async def _fetch_bookings(self, date_from: str, date_to: str) -> list[dict]:
        """
        ЕДИНСТВЕННАЯ точка работы с боевым API DIKIDI.

        TODO: уточнить путь/параметры по документации из кабинета DIKIDI
        (Настройки → Интеграция). Ожидаем список записей за период, у каждой
        — время начала/конца, имя клиента, услуга.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{self.base_url}/v1/records",
                params={
                    "company_id": self.company_id,
                    "date_from": date_from,
                    "date_to": date_to,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            r.raise_for_status()
            return r.json().get("data", [])

    # ── промпт ───────────────────────────────────────────────────────
    @staticmethod
    def format_for_prompt(
        bookings: list[dict],
        available: bool = True,
        free_slots: dict[str, list[str]] | None = None,
    ) -> str:
        """Блок для system-промпта: расписание + свободные окна + правила read-only."""
        if not available:
            # Расписания нет вообще — Оливия не должна ничего утверждать о записях
            return (
                "ДОСТУП К СИСТЕМЕ ЗАПИСИ: сейчас недоступен.\n"
                "• НИКОГДА не называй время чьей-либо записи и не подтверждай, "
                "что запись существует.\n"
                "• Если пациент спрашивает про свою запись — вежливо попроси "
                "подождать: администратор посмотрит запись и пригласит.\n"
                "• Новые записи ты не создаёшь: собери имя и телефон, скажи, что "
                "администратор перезвонит и согласует время."
            )
        if bookings:
            lines = "\n".join(
                f"  • {b['time']} — {b['client']}, {b['service']}" for b in bookings
            )
            schedule = f"ЗАПИСИ НА СЕГОДНЯ (из системы записи):\n{lines}"
        else:
            schedule = "ЗАПИСИ НА СЕГОДНЯ: список пуст или недоступен."

        slots_block = "СВОБОДНЫЕ ОКНА ДЛЯ ЗАПИСИ: нет данных."
        if free_slots:
            parts = []
            today = datetime.now().date().isoformat()
            for day, slots in free_slots.items():
                label = "сегодня" if day == today else f"{day[8:10]}.{day[5:7]}"
                shown = slots[:10]  # не раздуваем промпт бесконечным списком
                times = ", ".join(shown) if shown else "свободных окон нет"
                parts.append(f"  • {label}: {times}")
            slots_block = "СВОБОДНЫЕ ОКНА ДЛЯ ЗАПИСИ:\n" + "\n".join(parts)

        return (
            f"{schedule}\n\n{slots_block}\n\n"
            "ПРАВИЛА РАБОТЫ С ЗАПИСЯМИ (строго):\n"
            "• Ты можешь ТОЛЬКО смотреть записи и свободные окна. Создавать, "
            "переносить или отменять записи ты НЕ можешь — это делает только "
            "администратор.\n"
            "• Если пациент называет имя и оно есть в списке — подтверди время "
            "его записи и попроси подождать: администратор пригласит.\n"
            "• Если имени в списке нет — не выдумывай запись; предложи "
            "бесплатную консультацию и скажи, что администратор перезвонит "
            "и согласует время.\n"
            "• Если пациент называет желаемый день и время — сверься со "
            "СВОБОДНЫМИ ОКНАМИ. Если желаемое время занято — предложи "
            "ближайшее свободное в тот же день (или в соседний, если в этот "
            "окон нет). Клиника открывается в 12:00 — время раньше полудня "
            "не предлагай.\n"
            "• Даже если окно свободно, НИКОГДА не подтверждай запись как "
            "состоявшуюся: говори «передам администратору, он перезвонит и "
            "согласует точное время».\n"
            "• Никогда не называй записи других пациентов, если человек "
            "не назвал это имя сам."
        )
