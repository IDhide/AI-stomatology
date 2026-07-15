"""
Mock-провайдеры — чтобы поднять и потыкать систему на MacBook БЕЗ ключей.

Логика пайплайна, WebSocket, визуал и синхронизация анимации работают
полностью; вместо реальных API — заглушки. Как только в .env появятся
ключи — фабрика подставит реальные провайдеры автоматически.
"""
from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import AsyncIterator

from .base import LLMProvider, STTProvider, TTSProvider


class MockSTT(STTProvider):
    async def transcribe(self, audio: bytes, sample_rate: int = 16000) -> str:
        await asyncio.sleep(0.2)
        return "Здравствуйте, хочу записаться к стоматологу"


class MockLLM(LLMProvider):
    async def stream(self, messages, *, tools=None) -> AsyncIterator[str]:
        reply = (
            "Здравствуйте! Конечно, помогу записаться. "
            "У нас есть свободное время сегодня в пятнадцать часов. "
            "Подскажите, вас это устроит?"
        )
        for word in reply.split():
            await asyncio.sleep(0.03)
            yield word + " "


class MockTTS(TTSProvider):
    """Генерит синусоиду с «речевой» огибающей — чтобы шар пульсировал."""

    SAMPLE_RATE = 16000

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        duration = min(4.0, max(1.0, len(text) * 0.06))
        total = int(self.SAMPLE_RATE * duration)
        block = self.SAMPLE_RATE // 20  # 50 мс
        i = 0
        while i < total:
            n = min(block, total - i)
            samples = bytearray()
            for k in range(n):
                t = (i + k) / self.SAMPLE_RATE
                env = 0.5 + 0.5 * math.sin(t * 6.0)  # «слоги»
                val = int(env * 16000 * math.sin(2 * math.pi * 180 * t))
                samples += struct.pack("<h", max(-32768, min(32767, val)))
            yield bytes(samples)
            i += n
            await asyncio.sleep(0.05)
