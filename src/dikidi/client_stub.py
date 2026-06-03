"""
client_stub.py
==============
Заглушка DIKIDI-клиента для оффлайн-демо.
Возвращает правдоподобные данные без сети, чтобы можно было пройти весь
пользовательский сценарий (приветствие → запрос окон → запись → подтверждение).

Сохраняет «записи» в памяти процесса, чтобы LLM мог их «отменить»/«перенести».
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from ..dental.knowledge_base import find_procedure


# ────────────────────────────────────────────────────────────
@dataclass
class _Slot:
    id: str
    date: str      # YYYY-MM-DD
    time: str      # HH:MM
    doctor: str
    specialty: str
    available: bool = True

    def for_voice(self) -> str:
        d = datetime.strptime(self.date, "%Y-%m-%d")
        days = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
        day_word = days[d.weekday()]
        return f"{day_word} в {self.time}, врач {self.doctor}"


@dataclass
class _Booking:
    id: str
    client_name: str
    client_phone: str
    slot: _Slot
    procedure_code: str
    note: str
    created_at: float = field(default_factory=time.time)


# ────────────────────────────────────────────────────────────
class DikidiClientStub:
    """
    Имитирует подмножество DIKIDI API, нужное для голосового ассистента.
    Все методы — async, чтобы сигнатура совпадала с настоящим клиентом.
    """

    DOCTORS: dict[str, list[str]] = {
        "терапевт":          ["Иванова А. С.", "Сидоров П. И."],
        "хирург":            ["Куликов В. А."],
        "ортодонт":          ["Петрова Е. М."],
        "ортопед":           ["Соколов Д. И."],
        "гигиенист":         ["Мария Л."],
        "детский стоматолог":["Лебедева О. В."],
        "имплантолог":       ["Куликов В. А."],
    }

    def __init__(self, *_, seed: int | None = 42, **__):
        self._rng = random.Random(seed)
        self._bookings: dict[str, _Booking] = {}
        self._slots: list[_Slot] = self._generate_slots()
        logger.warning("DIKIDI работает в STUB-режиме — реальных записей не создаётся")

    # ────────────────────────────────────────────────────────
    def _generate_slots(self) -> list[_Slot]:
        slots: list[_Slot] = []
        today = datetime.now().replace(minute=0, second=0, microsecond=0)
        for day_offset in range(0, 14):
            day = today + timedelta(days=day_offset)
            # выходных пока нет, считаем что клиника работает 7/7
            for hour in [10, 11, 13, 14, 15, 16, 17, 19]:
                for spec, doctors in self.DOCTORS.items():
                    # не все врачи работают каждый день
                    if self._rng.random() < 0.55:
                        continue
                    doctor = self._rng.choice(doctors)
                    sid = f"{day.strftime('%Y%m%d')}_{hour:02d}_{spec[:3]}"
                    slots.append(_Slot(
                        id=sid,
                        date=day.strftime("%Y-%m-%d"),
                        time=f"{hour:02d}:00",
                        doctor=doctor,
                        specialty=spec,
                        available=True,
                    ))
        return slots

    # ────────────────────────────────────────────────────────
    async def find_client(self, name: str = "", phone: str = "") -> dict[str, Any]:
        await asyncio.sleep(0.05)
        # Имитируем «такого клиента нет» в 70% случаев
        if not (name or phone):
            return {"found": False}
        if self._rng.random() < 0.7:
            return {"found": False}
        return {
            "found": True,
            "client_id": f"stub_{self._rng.randint(1000, 9999)}",
            "name": name or "Иван Иванов",
            "phone": phone or "+79161234567",
            "last_visit": "2025-11-12",
        }

    # ────────────────────────────────────────────────────────
    async def get_available_slots(
        self,
        specialty: str = "терапевт",
        date_from: str | None = None,
        date_to: str | None = None,
        priority: int = 2,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Возвращает первые `limit` подходящих свободных окон."""
        await asyncio.sleep(0.07)
        today = datetime.now().strftime("%Y-%m-%d")
        df = date_from or today
        # priority=0 (срочно) — только сегодня
        if priority == 0:
            dt_limit = today
        else:
            dt_limit = date_to or (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

        result = []
        for s in self._slots:
            if not s.available:
                continue
            if s.specialty != specialty:
                # для терапевта пускаем и общий «терапевт», и (при острой боли) хирурга
                if not (priority == 0 and s.specialty in ("терапевт", "хирург")):
                    continue
            if not (df <= s.date <= dt_limit):
                continue
            result.append({
                "slot_id": s.id,
                "date": s.date,
                "time": s.time,
                "doctor": s.doctor,
                "specialty": s.specialty,
                "human": s.for_voice(),
            })
            if len(result) >= limit:
                break
        return result

    # ────────────────────────────────────────────────────────
    async def get_services(self, limit: int = 8) -> list[dict[str, Any]]:
        """Список услуг с ценами/длительностями."""
        await asyncio.sleep(0.03)
        from ..dental.knowledge_base import KB
        return [
            {"code": p.code, "name": p.name,
             "price": p.price_from_rub, "duration": p.duration_min,
             "specialty": p.specialty}
            for p in KB[:limit]
        ]

    # ────────────────────────────────────────────────────────
    async def create_booking(
        self,
        slot_id: str,
        procedure_code: str,
        client_id: str | None = None,
        client_name: str = "",
        client_phone: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        await asyncio.sleep(0.08)
        slot = next((s for s in self._slots if s.id == slot_id), None)
        if slot is None or not slot.available:
            return {"ok": False, "error": "slot_not_available"}
        if not find_procedure(procedure_code) and procedure_code not in {p.code for p in __import__('src.dental.knowledge_base', fromlist=['KB']).KB}:
            # допускаем неизвестный код, но логируем
            logger.warning(f"Stub: неизвестный procedure_code='{procedure_code}'")

        slot.available = False
        booking_id = f"bk_{self._rng.randint(100000, 999999)}"
        self._bookings[booking_id] = _Booking(
            id=booking_id,
            client_name=client_name or "Гость",
            client_phone=client_phone,
            slot=slot,
            procedure_code=procedure_code,
            note=note,
        )
        logger.info(f"STUB booking создана: {booking_id} → {slot.for_voice()}")
        return {
            "ok": True,
            "booking_id": booking_id,
            "human": slot.for_voice(),
            "date": slot.date,
            "time": slot.time,
            "doctor": slot.doctor,
        }

    # ────────────────────────────────────────────────────────
    async def cancel_booking(self, booking_id: str) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        b = self._bookings.pop(booking_id, None)
        if not b:
            return {"ok": False, "error": "not_found"}
        b.slot.available = True
        return {"ok": True, "cancelled": booking_id}

    # ────────────────────────────────────────────────────────
    async def reschedule_booking(self, booking_id: str, new_slot_id: str) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        b = self._bookings.get(booking_id)
        if not b:
            return {"ok": False, "error": "booking_not_found"}
        new_slot = next((s for s in self._slots if s.id == new_slot_id), None)
        if not new_slot or not new_slot.available:
            return {"ok": False, "error": "slot_not_available"}
        b.slot.available = True
        new_slot.available = False
        b.slot = new_slot
        return {"ok": True, "human": new_slot.for_voice()}


# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def main():
        c = DikidiClientStub(seed=7)
        print("свободные окна на терапевта:")
        for s in await c.get_available_slots("терапевт", limit=3):
            print(" ", s)
        print("\nуслуги:")
        for s in await c.get_services(limit=4):
            print(" ", s)
        first = (await c.get_available_slots("терапевт", limit=1))[0]
        b = await c.create_booking(first["slot_id"], "caries_simple", client_name="Тест", client_phone="+79991234567")
        print("\nрезультат записи:", b)
    asyncio.run(main())
