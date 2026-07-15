"""
DIKIDI — доступ ТОЛЬКО НА ЧТЕНИЕ.

Оливия может посмотреть записи на сегодня и подсказать пациенту время его
записи («Ваша запись сегодня в пятнадцать ноль-ноль, присаживайтесь,
администратор вас пригласит»). Создавать, переносить и отменять записи
Оливия НЕ может — это делает только живой администратор.

Без DIKIDI-ключей работает на демо-данных, чтобы сценарий можно было
проверить на MacBook прямо сейчас.
"""
from __future__ import annotations

from datetime import datetime

import httpx
from loguru import logger

# Демо-записи на сегодня (только при DIKIDI_DEMO=true — для теста сценария)
_DEMO_BOOKINGS = [
    {"time": "15:00", "client": "Анна", "service": "консультация терапевта"},
    {"time": "16:30", "client": "Дмитрий", "service": "чистка зубов"},
    {"time": "18:00", "client": "Мария", "service": "лечение канала"},
]


class DikidiReadOnly:
    def __init__(self, api_key: str = "", company_id: str = "",
                 base_url: str = "https://api.dikidi.net", demo: bool = False):
        self.api_key = api_key
        self.company_id = company_id
        self.base_url = base_url.rstrip("/")
        self.enabled = bool(api_key and company_id)
        self.demo = demo and not self.enabled
        if not self.enabled:
            if self.demo:
                logger.warning("DIKIDI: ключей нет, DIKIDI_DEMO=true — демо-записи")
            else:
                logger.info("DIKIDI: не подключён — Оливия работает без расписания")

    @property
    def available(self) -> bool:
        """Есть ли у Оливии хоть какие-то данные о записях."""
        return self.enabled or self.demo

    async def today_bookings(self) -> list[dict]:
        """Записи на сегодня: [{time, client, service}, ...]."""
        if not self.enabled:
            return list(_DEMO_BOOKINGS) if self.demo else []
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self.base_url}/v1/records",
                    params={"company_id": self.company_id,
                            "date_from": today, "date_to": today},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                r.raise_for_status()
                data = r.json().get("data", [])
            return [
                {
                    "time": item.get("time", ""),
                    "client": item.get("client_name", ""),
                    "service": item.get("service_name", ""),
                }
                for item in data
            ]
        except Exception as e:
            logger.error(f"DIKIDI today_bookings: {e}")
            return []

    @staticmethod
    def format_for_prompt(bookings: list[dict], available: bool = True) -> str:
        """Блок для system-промпта: расписание + жёсткие правила read-only."""
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
        return (
            f"{schedule}\n\n"
            "ПРАВИЛА РАБОТЫ С ЗАПИСЯМИ (строго):\n"
            "• Ты можешь ТОЛЬКО смотреть записи. Создавать, переносить или "
            "отменять записи ты НЕ можешь — это делает только администратор.\n"
            "• Если пациент называет имя и оно есть в списке — подтверди время "
            "его записи и попроси подождать: администратор пригласит.\n"
            "• Если имени в списке нет — не выдумывай запись; предложи "
            "бесплатную консультацию и скажи, что администратор перезвонит "
            "и согласует время.\n"
            "• Никогда не называй записи других пациентов, если человек "
            "не назвал это имя сам."
        )
