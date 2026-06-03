"""
Mock версия DIKIDI клиента для тестирования без API
"""
import asyncio
from datetime import datetime, timedelta

from loguru import logger


class DikidiClient:
    """Mock клиент для DIKIDI API"""

    def __init__(self, config):
        self.config = config
        logger.success("Mock DIKIDI клиент инициализирован (без реального API)")

    async def get_available_slots(
        self,
        service_id: int | None = None,
        master_id: int | None = None,
        days_ahead: int = 7
    ) -> list[dict]:
        """Mock получение свободных слотов"""
        await asyncio.sleep(0.5)

        # Генерируем mock слоты
        slots = []
        base_date = datetime.now() + timedelta(days=1)

        for hour in [10, 12, 14, 16, 18]:
            slots.append({
                "date": base_date.strftime("%Y-%m-%d"),
                "time": f"{hour}:00",
                "master_id": 1,
                "master_name": "Анна Иванова"
            })

        logger.info(f"Mock: Получено {len(slots)} свободных слотов")
        return slots

    async def create_booking(
        self,
        client_name: str,
        client_phone: str,
        service_id: int,
        master_id: int,
        datetime_str: str
    ) -> dict | None:
        """Mock создание записи"""
        await asyncio.sleep(0.5)

        booking = {
            "id": 12345,
            "client_name": client_name,
            "client_phone": client_phone,
            "datetime": datetime_str,
            "status": "confirmed"
        }

        logger.success(f"Mock: Запись создана для {client_name}")
        return booking

    async def find_client(self, phone: str) -> dict | None:
        """Mock поиск клиента"""
        await asyncio.sleep(0.3)

        # Всегда возвращаем mock клиента
        client = {
            "id": 999,
            "name": "Мария Петрова",
            "phone": phone,
            "visits": 5
        }

        logger.info(f"Mock: Клиент найден - {client['name']}")
        return client

    async def get_services(self) -> list[dict]:
        """Mock получение услуг"""
        await asyncio.sleep(0.3)

        services = [
            {"id": 1, "name": "Стрижка женская", "price": 2500, "duration": 60},
            {"id": 2, "name": "Стрижка мужская", "price": 1500, "duration": 30},
            {"id": 3, "name": "Маникюр классический", "price": 1500, "duration": 60},
            {"id": 4, "name": "Маникюр аппаратный", "price": 2000, "duration": 90},
            {"id": 5, "name": "Окрашивание", "price": 3000, "duration": 120},
        ]

        logger.info(f"Mock: Получено {len(services)} услуг")
        return services

    async def get_masters(self) -> list[dict]:
        """Mock получение мастеров"""
        await asyncio.sleep(0.3)

        masters = [
            {"id": 1, "name": "Анна Иванова", "specialization": "Парикмахер"},
            {"id": 2, "name": "Елена Смирнова", "specialization": "Мастер маникюра"},
            {"id": 3, "name": "Ольга Кузнецова", "specialization": "Колорист"},
        ]

        logger.info(f"Mock: Получено {len(masters)} мастеров")
        return masters

    async def close(self):
        """Mock закрытие сессии"""
        logger.info("Mock DIKIDI сессия закрыта")
