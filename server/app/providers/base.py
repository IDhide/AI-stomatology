"""
Абстракции провайдеров — сердце слоя, который делает стек сменяемым.

Оркестратор знает только про эти три интерфейса. Конкретные реализации
(Grok, ElevenLabs, Whisper, mock) подставляются фабрикой в __init__.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class STTProvider(ABC):
    """Речь → текст."""

    @abstractmethod
    async def transcribe(self, audio: bytes, sample_rate: int = 16000) -> str:
        """Распознать одну реплику (PCM16 mono) и вернуть текст."""
        ...


class LLMProvider(ABC):
    """Текст → текст, потоково по токенам."""

    @abstractmethod
    def stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """
        Отдаёт кусочки ответа по мере генерации.
        messages — в формате OpenAI ([{role, content}, ...]).
        """
        ...


class TTSProvider(ABC):
    """Текст → аудио, потоково по чанкам PCM16."""

    @abstractmethod
    def stream(self, text: str) -> AsyncIterator[bytes]:
        """Отдаёт аудио-чанки (PCM16 mono) по мере синтеза."""
        ...
