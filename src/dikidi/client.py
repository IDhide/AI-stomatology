"""
client.py
=========
Единый асинхронный клиент DIKIDI API для ассистента.

По умолчанию ходит в ТЕСТОВЫЙ сервер `fake_server.py` (он повторяет реальные
пути DIKIDI). Когда будет доступ к настоящему DIKIDI — достаточно поменять
base_url и токен (переменные DIKIDI_BASE_URL / DIKIDI_TOKEN), код менять не
нужно. Сигнатуры методов совпадают с тем, что вызывает LLM через tools
(см. src/llm/tools.py) и веб-сценарий.

Эндпоинты (как в fake_server):
    GET  /v1/company/services
    GET  /v1/company/masters
    GET  /v1/booking/available-slots
    POST /v1/booking/create
    GET  /v1/clients/search
"""
from __future__ import annotations

from datetime import datetime

import aiohttp
from loguru import logger

_DAYS = ["понедельник", "вторник", "среду", "четверг",
         "пятницу", "субботу", "воскресенье"]


def _human(date: str, time: str, doctor: str) -> str:
    """Человеческое описание окна для озвучивания."""
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
        return f"{_DAYS[d.weekday()]} в {time}, врач {doctor}"
    except Exception:
        return f"{date} в {time}, врач {doctor}"


class DikidiClient:
    """Асинхронный HTTP-клиент DIKIDI (тестовый сервер или реальный API)."""

    def __init__(self, base_url: str, token: str = "demo-token", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        logger.success(f"DIKIDI клиент → {self.base_url}")

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    # ── услуги / врачи ──────────────────────────────────────
    async def get_services(self, limit: int = 8) -> list[dict]:
        s = await self._sess()
        async with s.get(f"{self.base_url}/v1/company/services") as r:
            r.raise_for_status()
            data = (await r.json()).get("data", [])
        return data[:limit]

    async def get_masters(self) -> list[dict]:
        s = await self._sess()
        async with s.get(f"{self.base_url}/v1/company/masters") as r:
            r.raise_for_status()
            return (await r.json()).get("data", [])

    # ── свободные окна ──────────────────────────────────────
    async def get_available_slots(
        self,
        specialty: str = "терапевт",
        date_from: str | None = None,
        date_to: str | None = None,
        priority: int = 2,
        limit: int = 5,
        **_,
    ) -> list[dict]:
        s = await self._sess()
        params = {"specialty": specialty, "limit": str(limit)}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        async with s.get(f"{self.base_url}/v1/booking/available-slots",
                         params=params) as r:
            r.raise_for_status()
            data = (await r.json()).get("data", [])
        for slot in data:
            slot["human"] = _human(slot.get("date", ""), slot.get("time", ""),
                                   slot.get("master_name", ""))
        return data

    # ── записи на приём (проверка на ресепшене) ─────────────
    async def get_appointments(
        self, time: str = "", name: str = "", date: str | None = None
    ) -> list[dict]:
        """Записи на сегодня, опционально фильтр по времени/имени."""
        s = await self._sess()
        params: dict[str, str] = {}
        if time:
            params["time"] = time
        if name:
            params["name"] = name
        if date:
            params["date"] = date
        try:
            async with s.get(f"{self.base_url}/v1/booking/appointments",
                             params=params) as r:
                r.raise_for_status()
                return (await r.json()).get("data", [])
        except Exception:
            logger.exception("DIKIDI: ошибка получения записей")
            return []

    # ── клиент ──────────────────────────────────────────────
    async def find_client(self, name: str = "", phone: str = "") -> dict:
        if not phone:
            return {"found": False}
        s = await self._sess()
        try:
            async with s.get(f"{self.base_url}/v1/clients/search",
                             params={"phone": phone}) as r:
                data = (await r.json()).get("data", [])
        except Exception:
            return {"found": False}
        if data:
            c = data[0]
            return {"found": True, "client_id": c.get("id"),
                    "name": c.get("name"), "phone": c.get("phone")}
        return {"found": False}

    # ── запись ──────────────────────────────────────────────
    async def create_booking(
        self,
        slot_id: str,
        procedure_code: str = "consult",
        client_id: str | None = None,
        client_name: str = "Гость",
        client_phone: str = "",
        note: str = "",
        **_,
    ) -> dict:
        s = await self._sess()
        payload = {
            "client": {"name": client_name, "phone": client_phone},
            "services": [{"slot_id": slot_id, "code": procedure_code, "note": note}],
        }
        async with s.post(f"{self.base_url}/v1/booking/create", json=payload) as r:
            ok = r.status < 400
            data = (await r.json()).get("data", {})
        if not ok:
            return {"ok": False, "error": data.get("message", "error")}
        return {
            "ok": True,
            "booking_id": data.get("id"),
            "human": _human(data.get("date", ""), data.get("time", ""),
                            data.get("master_name", "")),
            "date": data.get("date"),
            "time": data.get("time"),
            "doctor": data.get("master_name"),
        }

    async def cancel_booking(self, booking_id: str) -> dict:
        # в тестовом сервере отмена не реализована
        return {"ok": False, "error": "not_supported_in_test_api"}

    async def reschedule_booking(self, booking_id: str, new_slot_id: str) -> dict:
        return {"ok": False, "error": "not_supported_in_test_api"}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
