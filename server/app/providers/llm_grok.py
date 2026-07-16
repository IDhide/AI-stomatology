"""
LLM-провайдер на Grok (xAI).

xAI отдаёт OpenAI-совместимый эндпоинт /chat/completions, поэтому
используем обычный httpx со stream=True и парсим SSE-чанки.

Чтобы заменить Grok на другую OpenAI-совместимую модель — достаточно
поменять base_url/model/api_key в конфиге. Для Claude пишется отдельный
провайдер (llm_claude.py) с тем же интерфейсом LLMProvider.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
from loguru import logger

from .base import LLMProvider


class _TransientError(Exception):
    """Временный сбой xAI (5xx/429/сеть) — можно повторить запрос."""


class GrokLLM(LLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.x.ai/v1",
        model: str = "grok-4",
        temperature: float = 0.4,
        max_tokens: int = 400,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    RETRIES = 3          # попытки при временных сбоях xAI
    RETRY_DELAYS = (0.4, 1.0)

    async def stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """
        Стрим с ретраями: 503/429/сетевые сбои xAI повторяются до 3 раз.
        Повторяем только если ещё ничего не отдали наружу (иначе получился
        бы дублированный текст).
        """
        for attempt in range(self.RETRIES):
            yielded = False
            try:
                async for piece in self._stream_once(messages, tools):
                    yielded = True
                    yield piece
                return
            except _TransientError as e:
                if yielded or attempt == self.RETRIES - 1:
                    raise
                delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                logger.warning(f"Grok недоступен ({e}), повтор через {delay}с "
                               f"[{attempt + 1}/{self.RETRIES}]")
                await asyncio.sleep(delay)

    async def _stream_once(
        self,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> AsyncIterator[str]:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code == 429 or resp.status_code >= 500:
                    body = await resp.aread()
                    logger.error(f"Grok {resp.status_code}: {body[:200]!r}")
                    raise _TransientError(f"HTTP {resp.status_code}")
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error(f"Grok {resp.status_code}: {body[:300]!r}")
                    resp.raise_for_status()

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        yield piece
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                httpx.RemoteProtocolError) as e:
            raise _TransientError(type(e).__name__) from e

    async def aclose(self) -> None:
        await self._client.aclose()
