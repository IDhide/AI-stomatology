"""
STT-провайдер на ElevenLabs Scribe.

Клиент (браузер) сам детектит конец фразы (VAD + AEC) и присылает уже
нарезанную реплику одним куском PCM16. Мы упаковываем её в WAV и шлём в
Scribe /v1/speech-to-text. Это надёжно и с низкой задержкой: реплика
короткая, распознаётся быстро.

Стриминговый realtime-STT можно добавить позже как отдельный класс с тем
же интерфейсом STTProvider — оркестратор менять не придётся.
"""
from __future__ import annotations

import io
import wave

import httpx
from loguru import logger

from .base import STTProvider


def _pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16 bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class ElevenLabsSTT(STTProvider):
    def __init__(self, api_key: str, model: str = "scribe_v1", language: str = "rus"):
        self.api_key = api_key
        self.model = model
        self.language = language
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    # Минимальная длительность реплики: короче — не тратим запрос,
    # ElevenLabs всё равно ответит 400 audio_too_short.
    MIN_SECONDS = 0.5

    async def transcribe(self, audio: bytes, sample_rate: int = 16000) -> str:
        if not audio:
            return ""
        duration = len(audio) / 2 / sample_rate  # PCM16 → 2 байта на сэмпл
        if duration < self.MIN_SECONDS:
            logger.debug(f"STT: реплика {duration:.2f}с слишком короткая — пропускаю")
            return ""

        wav_bytes = _pcm16_to_wav(audio, sample_rate)
        files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
        data = {"model_id": self.model, "language_code": self.language}
        headers = {"xi-api-key": self.api_key}

        resp = await self._client.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            files=files,
            data=data,
            headers=headers,
        )
        if resp.status_code != 200:
            # Не валим пайплайн: слишком короткое/тихое аудио — просто тишина
            logger.error(f"ElevenLabs STT {resp.status_code}: {resp.text[:300]}")
            return ""

        return (resp.json().get("text") or "").strip()

    async def aclose(self) -> None:
        await self._client.aclose()
