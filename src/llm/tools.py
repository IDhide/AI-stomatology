"""
tools.py
========
JSON-описание инструментов (function calling) для LLM-ассистента.
LLM выдаёт блок <tool>{"name":"...","args":{...}}</tool>; диспетчер
ниже парсит и вызывает соответствующий метод DIKIDI/KB.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from loguru import logger

from ..dental.knowledge_base import find_procedure


TOOL_SCHEMAS = [
    {
        "name": "find_client",
        "description": "Найти клиента в базе DIKIDI по имени и/или телефону",
        "args": {"name": "str?", "phone": "str?"},
    },
    {
        "name": "find_free_slots",
        "description": "Найти свободные окна. priority: 0=сегодня срочно, 1=в течение дня, 2=неделя, 3=любое",
        "args": {
            "specialty": "str (терапевт|хирург|ортодонт|ортопед|гигиенист|детский стоматолог)",
            "date_from": "str? (YYYY-MM-DD)",
            "date_to": "str? (YYYY-MM-DD)",
            "priority": "int (0..3)",
        },
    },
    {
        "name": "create_booking",
        "description": "Создать запись",
        "args": {
            "client_id": "str|null",
            "client_name": "str?",
            "client_phone": "str?",
            "slot_id": "str",
            "procedure_code": "str",
            "note": "str?",
        },
    },
    {
        "name": "cancel_booking",
        "description": "Отменить запись",
        "args": {"booking_id": "str"},
    },
    {
        "name": "reschedule_booking",
        "description": "Перенести запись",
        "args": {"booking_id": "str", "new_slot_id": "str"},
    },
    {
        "name": "get_procedure_info",
        "description": "Получить цену/длительность/описание процедуры",
        "args": {"query": "str"},
    },
]


def render_tools_for_prompt() -> str:
    """Человекочитаемое описание инструментов — кладётся в system."""
    lines = ["Доступные инструменты:"]
    for t in TOOL_SCHEMAS:
        args = ", ".join(f"{k}: {v}" for k, v in t["args"].items())
        lines.append(f"  • {t['name']}({args}) — {t['description']}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Парсинг <tool>...</tool> в ответе LLM
# ──────────────────────────────────────────────────────────────────────
_TOOL_RE = re.compile(r"<tool>\s*(\{.*?\})\s*</tool>", re.DOTALL)


def extract_tool_calls(llm_response: str) -> tuple[str, list[dict]]:
    """
    Делит ответ LLM на «реплику для пациента» и список tool-вызовов.
    Возвращает (speech_text, [tool_call, ...]).
    """
    calls: list[dict] = []
    for m in _TOOL_RE.finditer(llm_response):
        raw = m.group(1)
        try:
            call = json.loads(raw)
            if isinstance(call, dict) and "name" in call:
                calls.append(call)
        except json.JSONDecodeError as e:
            logger.warning(f"Не удалось распарсить tool: {e}: {raw[:120]}")
    speech = _TOOL_RE.sub("", llm_response).strip()
    return speech, calls


# ──────────────────────────────────────────────────────────────────────
# Диспетчер вызовов
# ──────────────────────────────────────────────────────────────────────
class ToolDispatcher:
    """Маршрутизирует tool-вызовы в DIKIDI / KB и возвращает результат для LLM."""

    def __init__(self, dikidi_client):
        self.dikidi = dikidi_client

    async def call(self, tool_call: dict) -> dict:
        name = tool_call.get("name", "")
        args = tool_call.get("args", {}) or {}
        logger.info(f"🔧 tool: {name}({args})")
        try:
            handler: Callable[..., Awaitable[Any]] | None = getattr(self, f"_t_{name}", None)
            if handler is None:
                return {"ok": False, "error": f"unknown tool: {name}"}
            result = await handler(**args)
            return {"ok": True, "result": result}
        except TypeError as e:
            return {"ok": False, "error": f"bad args: {e}"}
        except Exception as e:
            logger.exception("tool error")
            return {"ok": False, "error": str(e)}

    # ─── индивидуальные обработчики ─────────────────────────────
    async def _t_find_client(self, name: str = "", phone: str = "") -> Any:
        return await self.dikidi.find_client(name=name, phone=phone)

    async def _t_find_free_slots(self, specialty: str = "терапевт",
                                  date_from: str | None = None,
                                  date_to: str | None = None,
                                  priority: int = 2) -> Any:
        return await self.dikidi.get_available_slots(
            specialty=specialty, date_from=date_from, date_to=date_to, priority=priority
        )

    async def _t_create_booking(self, slot_id: str, procedure_code: str,
                                client_id: str | None = None,
                                client_name: str = "",
                                client_phone: str = "",
                                note: str = "") -> Any:
        return await self.dikidi.create_booking(
            client_id=client_id, client_name=client_name, client_phone=client_phone,
            slot_id=slot_id, procedure_code=procedure_code, note=note,
        )

    async def _t_cancel_booking(self, booking_id: str) -> Any:
        return await self.dikidi.cancel_booking(booking_id)

    async def _t_reschedule_booking(self, booking_id: str, new_slot_id: str) -> Any:
        return await self.dikidi.reschedule_booking(booking_id, new_slot_id)

    async def _t_get_procedure_info(self, query: str) -> Any:
        p = find_procedure(query)
        if not p:
            return {"found": False}
        return {
            "found": True,
            "code": p.code,
            "name": p.name,
            "duration_min": p.duration_min,
            "price_from_rub": p.price_from_rub,
            "specialty": p.specialty,
            "description": p.description,
            "contraindications": list(p.contraindications),
            "pediatric": p.pediatric,
        }
