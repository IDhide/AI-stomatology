"""
sim_client.py
=============
HTTP-клиент к симулятору DIKIDI (`fake_server.py`), совместимый по интерфейсу
с `DikidiClientStub`. Нужен, чтобы веб-сценарий (src/web/server.py) ходил за
данными в ОТДЕЛЬНЫЙ контейнер с API, а не держал заглушку в памяти — так
docker-compose демонстрирует реальное общение двух сервисов по сети.

Методы повторяют те, что использует KioskScenario:
    get_services(limit)         -> list[dict]   (code/name/price/duration/specialty)
    get_available_slots(spec)   -> list[dict]   (+ поле 'human' для озвучивания)
    create_booking(slot_id,...) -> dict         ({'ok': bool, 'human': str, ...})
"""
from __future__ import annotations

from datetime import datetime

import aiohttp
from loguru import logger

_DAYS = ["понедельник", "вторник", "среду", "четверг",
         "пятницу", "субботу", "воскресенье"]


def _human(date: str, time: str, doctor: str) -> str:
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
        return f"{_DAYS[d.weekday()]} в {time}, врач {doctor}"
    except Exception:
        return f"{date} в {time}, врач {doctor}"


class SimDikidiClient:
    """Async-клиент к fake_server. base_url, например http://dikidi-sim:8089."""

    def __init__(self, base_url: str, token: str = "demo-token", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        logger.info(f"DIKIDI: HTTP-симулятор {self.base_url}")

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    async def find_client(self, name: str = "", phone: str = "") -> dict:
        """Поиск клиента в симуляторе DIKIDI по телефону."""
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

    async def cancel_booking(self, booking_id: str) -> dict:
        # в симуляторе отмена не реализована — понятный ответ для LLM
        return {"ok": False, "error": "not_supported_in_sim"}

    async def reschedule_booking(self, booking_id: str, new_slot_id: str) -> dict:
        return {"ok": False, "error": "not_supported_in_sim"}

    async def get_services(self, limit: int = 8) -> list[dict]:
        s = await self._sess()
        async with s.get(f"{self.base_url}/v1/company/services") as r:
            r.raise_for_status()
            data = (await r.json()).get("data", [])
        return data[:limit]

    async def get_available_slots(self, specialty: str = "терапевт",
                                  limit: int = 5, **_) -> list[dict]:
        s = await self._sess()
        params = {"specialty": specialty, "limit": str(limit)}
        async with s.get(f"{self.base_url}/v1/booking/available-slots",
                         params=params) as r:
            r.raise_for_status()
            data = (await r.json()).get("data", [])
        for slot in data:
            slot["human"] = _human(slot["date"], slot["time"], slot["master_name"])
        return data

    async def create_booking(self, slot_id: str, procedure_code: str,
                             client_name: str = "Гость", client_phone: str = "",
                             **_) -> dict:
        s = await self._sess()
        payload = {
            "client": {"name": client_name, "phone": client_phone},
            "services": [{"slot_id": slot_id, "code": procedure_code}],
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

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
