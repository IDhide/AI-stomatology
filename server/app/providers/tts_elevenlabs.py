"""
TTS-провайдер на ElevenLabs Flash v2.5 (streaming).

Используем HTTP streaming-эндпоинт /text-to-speech/{voice}/stream:
он начинает отдавать аудио почти сразу, не дожидаясь синтеза всей фразы.
Формат по умолчанию — pcm_16000 (сырой PCM16 mono @ 16 kHz), который
браузер проигрывает через WebAudio без перекодирования.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from loguru import logger

from .base import TTSProvider


class ElevenLabsTTS(TTSProvider):
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model: str = "eleven_flash_v2_5",
        output_format: str = "pcm_16000",
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.output_format = output_format
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        if not text.strip():
            return

        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
            f"?output_format={self.output_format}"
        )
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self.model,
            "language_code": "ru",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.75,
                "speed": 1.0,
            },
        }

        async with self._client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                logger.error(f"ElevenLabs TTS {resp.status_code}: {body[:300]!r}")
                if resp.status_code == 402:
                    logger.error(
                        "402 = тариф Free не позволяет использовать голоса из Voice "
                        "Library через API. Решение: возьмите premade-голос (вкладка "
                        "Voices → Default в ElevenLabs) ИЛИ перейдите на план Starter."
                    )
                resp.raise_for_status()
            async for chunk in resp.aiter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk

    async def aclose(self) -> None:
        await self._client.aclose()
