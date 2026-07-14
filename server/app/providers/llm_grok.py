"""
LLM-провайдер на Grok (xAI).

xAI отдаёт OpenAI-совместимый эндпоинт /chat/completions, поэтому
используем обычный httpx со stream=True и парсим SSE-чанки.

Чтобы заменить Grok на другую OpenAI-совместимую модель — достаточно
поменять base_url/model/api_key в конфиге. Для Claude пишется отдельный
провайдер (llm_claude.py) с тем же интерфейсом LLMProvider.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
from loguru import logger

from .base import LLMProvider


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

    async def stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
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

        async with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
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

    async def aclose(self) -> None:
        await self._client.aclose()
