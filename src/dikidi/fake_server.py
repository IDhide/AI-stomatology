"""
fake_server.py
==============
Тестовый DIKIDI API — самостоятельный HTTP-сервер.

Поднимает HTTP-сервер с теми же путями, что и боевой DIKIDI, поэтому клиент
`dikidi/client.py` работает с ним без изменений — достаточно указать base_url
на этот сервер (по умолчанию так и есть). Для реального DIKIDI меняется только
DIKIDI_BASE_URL / DIKIDI_TOKEN.

Эндпоинты (подмножество, нужное ассистенту):
    GET  /v1/company/services           — список услуг
    GET  /v1/company/masters            — список врачей
    GET  /v1/booking/available-slots    — свободные окна
    POST /v1/booking/create             — создать запись
    GET  /v1/clients/search             — найти клиента по телефону
    GET  /healthz                       — проверка живости

Авторизация: заголовок `Authorization: Bearer <token>`. Сервер принимает
любой непустой токен (это симуляция), но логирует его отсутствие.

Запуск:
    python -m src.dikidi.fake_server --host 127.0.0.1 --port 8089
    python -m src.dikidi.fake_server --no-auth        # не требовать токен
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

from aiohttp import web
from loguru import logger

try:
    from ..dental.knowledge_base import KB
except ImportError:  # запуск как отдельный файл
    from src.dental.knowledge_base import KB


# ────────────────────────────────────────────────────────────
#  Данные клиники
# ────────────────────────────────────────────────────────────
DOCTORS = [
    {"id": 1, "name": "Иванова Анна Сергеевна",   "specialty": "терапевт"},
    {"id": 2, "name": "Сидоров Пётр Игоревич",    "specialty": "терапевт"},
    {"id": 3, "name": "Куликов Виктор Алексеевич","specialty": "хирург"},
    {"id": 4, "name": "Петрова Елена Михайловна", "specialty": "ортодонт"},
    {"id": 5, "name": "Соколов Дмитрий Ильич",    "specialty": "ортопед"},
    {"id": 6, "name": "Мария Лебедева",           "specialty": "гигиенист"},
    {"id": 7, "name": "Лебедева Ольга Викторовна","specialty": "детский стоматолог"},
    {"id": 8, "name": "Куликов Виктор Алексеевич","specialty": "имплантолог"},
]

WORK_HOURS = [10, 11, 13, 14, 15, 16, 17, 19]


class FakeDikidiState:
    """Состояние симулятора: окна, записи, клиенты."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.bookings: dict[str, dict] = {}
        self.clients: dict[str, dict] = {
            "+79161234567": {
                "id": 1001, "name": "Иван Иванов",
                "phone": "+79161234567", "visits": 3, "last_visit": "2025-11-12",
            }
        }
        self.slots = self._generate_slots()

    def _generate_slots(self) -> list[dict]:
        slots: list[dict] = []
        today = datetime.now().replace(minute=0, second=0, microsecond=0)
        for day_offset in range(0, 14):
            day = today + timedelta(days=day_offset)
            for hour in WORK_HOURS:
                for doc in DOCTORS:
                    # не каждый врач работает в каждый час
                    if self.rng.random() < 0.6:
                        continue
                    sid = f"{day.strftime('%Y%m%d')}{hour:02d}_{doc['id']}"
                    slots.append({
                        "slot_id": sid,
                        "date": day.strftime("%Y-%m-%d"),
                        "time": f"{hour:02d}:00",
                        "master_id": doc["id"],
                        "master_name": doc["name"],
                        "specialty": doc["specialty"],
                        "available": True,
                    })
        return slots


# ────────────────────────────────────────────────────────────
#  Обработчики
# ────────────────────────────────────────────────────────────
def _check_auth(request: web.Request) -> bool:
    if request.app["no_auth"]:
        return True
    auth = request.headers.get("Authorization", "")
    ok = auth.startswith("Bearer ") and len(auth) > len("Bearer ")
    if not ok:
        logger.warning(f"DIKIDI(fake): запрос без валидного токена → {request.path}")
    return ok


def _envelope(data, status: int = 200, **extra) -> web.Response:
    """DIKIDI отдаёт ответы в обёртке {'status': ..., 'data': ...}."""
    payload = {"status": "ok" if status < 400 else "error", "data": data}
    payload.update(extra)
    return web.json_response(payload, status=status)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "fake-dikidi"})


async def get_services(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _envelope({"message": "unauthorized"}, status=401)
    services = [
        {
            "id": i + 1,
            "code": p.code,
            "name": p.name,
            "price": p.price_from_rub,
            "duration": p.duration_min,
            "specialty": p.specialty,
        }
        for i, p in enumerate(KB)
    ]
    logger.info(f"DIKIDI(fake): отдано {len(services)} услуг")
    return _envelope(services)


async def get_masters(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _envelope({"message": "unauthorized"}, status=401)
    logger.info(f"DIKIDI(fake): отдано {len(DOCTORS)} врачей")
    return _envelope(DOCTORS)


async def available_slots(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _envelope({"message": "unauthorized"}, status=401)
    st: FakeDikidiState = request.app["state"]
    q = request.query
    specialty = q.get("specialty")
    master_id = q.get("master_id")
    date_from = q.get("date_from")
    date_to = q.get("date_to")
    limit = int(q.get("limit", 8))

    today = datetime.now().strftime("%Y-%m-%d")
    df = date_from or today
    dt = date_to or (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    result = []
    for s in st.slots:
        if not s["available"]:
            continue
        if specialty and s["specialty"] != specialty:
            continue
        if master_id and str(s["master_id"]) != str(master_id):
            continue
        if not (df <= s["date"] <= dt):
            continue
        result.append({k: s[k] for k in
                       ("slot_id", "date", "time", "master_id", "master_name", "specialty")})
        if len(result) >= limit:
            break
    logger.info(f"DIKIDI(fake): найдено {len(result)} окон (specialty={specialty})")
    return _envelope(result)


async def create_booking(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _envelope({"message": "unauthorized"}, status=401)
    st: FakeDikidiState = request.app["state"]
    try:
        body = await request.json()
    except Exception:
        return _envelope({"message": "bad json"}, status=400)

    client = body.get("client", {})
    services = body.get("services", [{}])
    svc = services[0] if services else {}
    slot_id = svc.get("slot_id") or svc.get("datetime")

    slot = next((s for s in st.slots if s["slot_id"] == slot_id), None)
    if slot is None:
        # допускаем запись по datetime-строке (как в боевом payload)
        slot = next((s for s in st.slots if s["available"]), None)
    if slot is None or not slot["available"]:
        return _envelope({"message": "slot_not_available"}, status=409)

    slot["available"] = False
    booking_id = st.rng.randint(100000, 999999)
    record = {
        "id": booking_id,
        "client_name": client.get("name", "Гость"),
        "client_phone": client.get("phone", ""),
        "date": slot["date"],
        "time": slot["time"],
        "master_id": slot["master_id"],
        "master_name": slot["master_name"],
        "status": "confirmed",
    }
    st.bookings[str(booking_id)] = record
    logger.success(f"DIKIDI(fake): запись #{booking_id} → "
                   f"{record['date']} {record['time']} ({record['master_name']})")
    return _envelope(record, status=201)


async def search_client(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _envelope({"message": "unauthorized"}, status=401)
    st: FakeDikidiState = request.app["state"]
    phone = request.query.get("phone", "")
    found = st.clients.get(phone)
    if found:
        logger.info(f"DIKIDI(fake): клиент найден — {found['name']}")
        return _envelope([found])
    logger.info("DIKIDI(fake): клиент не найден")
    return _envelope([])


# ────────────────────────────────────────────────────────────
def build_app(no_auth: bool = False, seed: int = 42) -> web.Application:
    app = web.Application()
    app["state"] = FakeDikidiState(seed=seed)
    app["no_auth"] = no_auth
    app.add_routes([
        web.get("/healthz", health),
        web.get("/v1/company/services", get_services),
        web.get("/v1/company/masters", get_masters),
        web.get("/v1/booking/available-slots", available_slots),
        web.post("/v1/booking/create", create_booking),
        web.get("/v1/clients/search", search_client),
    ])
    return app


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Симулятор DIKIDI API (HTTP)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8089)
    p.add_argument("--no-auth", action="store_true", help="не требовать Bearer-токен")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    logger.info(f"🦷 Запуск симулятора DIKIDI API на http://{args.host}:{args.port}")
    logger.info(f"   auth: {'отключена' if args.no_auth else 'Bearer-токен обязателен'}")
    web.run_app(build_app(no_auth=args.no_auth, seed=args.seed),
                host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
