"""
Клиент для работы с DIKIDI API
"""
from datetime import datetime, timedelta

import aiohttp
from loguru import logger


class DikidiClient:
    """Клиент для взаимодействия с DIKIDI API"""

    def __init__(self, config):
        self.config = config
        self.base_url = config.base_url
        self.api_key = config.api_key
        self.company_id = config.company_id
        self.timeout = config.timeout

        self.session: aiohttp.ClientSession | None = None

        logger.success("DIKIDI клиент инициализирован")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение или создание HTTP сессии"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self.session

    async def get_available_slots(
        self,
        service_id: int | None = None,
        master_id: int | None = None,
        days_ahead: int = 7
    ) -> list[dict]:
        """
        Получить свободные окна для записи

        Args:
            service_id: ID услуги (опционально)
            master_id: ID мастера (опционально)
            days_ahead: Количество дней вперед

        Returns:
            Список свободных слотов
        """
        try:
            session = await self._get_session()

            # Формируем параметры запроса
            params = {
                "company_id": self.company_id,
                "date_from": datetime.now().strftime("%Y-%m-%d"),
                "date_to": (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            }

            if service_id:
                params["service_id"] = service_id
            if master_id:
                params["master_id"] = master_id

            async with session.get(
                f"{self.base_url}/v1/booking/available-slots",
                params=params
            ) as response:
                response.raise_for_status()
                data = await response.json()

                slots = data.get("data", [])
                logger.info(f"Получено {len(slots)} свободных слотов")
                return slots

        except Exception as e:
            logger.error(f"Ошибка получения слотов: {e}")
            return []

    async def create_booking(
        self,
        client_name: str,
        client_phone: str,
        service_id: int,
        master_id: int,
        datetime_str: str
    ) -> dict | None:
        """
        Создать запись клиента

        Args:
            client_name: Имя клиента
            client_phone: Телефон клиента
            service_id: ID услуги
            master_id: ID мастера
            datetime_str: Дата и время в формате ISO

        Returns:
            Данные созданной записи или None
        """
        try:
            session = await self._get_session()

            payload = {
                "company_id": self.company_id,
                "client": {
                    "name": client_name,
                    "phone": client_phone
                },
                "services": [{
                    "service_id": service_id,
                    "master_id": master_id,
                    "datetime": datetime_str
                }]
            }

            async with session.post(
                f"{self.base_url}/v1/booking/create",
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()

                logger.success(f"Запись создана: {data.get('data', {}).get('id')}")
                return data.get("data")

        except Exception as e:
            logger.error(f"Ошибка создания записи: {e}")
            return None

    async def find_client(self, phone: str) -> dict | None:
        """
        Найти клиента по номеру телефона

        Args:
            phone: Номер телефона

        Returns:
            Данные клиента или None
        """
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/v1/clients/search",
                params={
                    "company_id": self.company_id,
                    "phone": phone
                }
            ) as response:
                response.raise_for_status()
                data = await response.json()

                clients = data.get("data", [])
                if clients:
                    logger.info(f"Клиент найден: {clients[0].get('name')}")
                    return clients[0]
                else:
                    logger.info("Клиент не найден")
                    return None

        except Exception as e:
            logger.error(f"Ошибка поиска клиента: {e}")
            return None

    async def get_services(self) -> list[dict]:
        """
        Получить список услуг компании

        Returns:
            Список услуг
        """
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/v1/company/services",
                params={"company_id": self.company_id}
            ) as response:
                response.raise_for_status()
                data = await response.json()

                services = data.get("data", [])
                logger.info(f"Получено {len(services)} услуг")
                return services

        except Exception as e:
            logger.error(f"Ошибка получения услуг: {e}")
            return []

    async def get_masters(self) -> list[dict]:
        """
        Получить список мастеров

        Returns:
            Список мастеров
        """
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/v1/company/masters",
                params={"company_id": self.company_id}
            ) as response:
                response.raise_for_status()
                data = await response.json()

                masters = data.get("data", [])
                logger.info(f"Получено {len(masters)} мастеров")
                return masters

        except Exception as e:
            logger.error(f"Ошибка получения мастеров: {e}")
            return []

    async def close(self):
        """Закрытие HTTP сессии"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("DIKIDI сессия закрыта")
