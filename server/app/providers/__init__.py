"""
Фабрика провайдеров.

build_providers() читает конфиг и отдаёт (stt, llm, tts). Если для
выбранного провайдера нет ключа — молча падает на mock, чтобы разработка
на MacBook не блокировалась отсутствием секретов.
"""
from __future__ import annotations

from loguru import logger

from ..config import Settings
from .base import LLMProvider, STTProvider, TTSProvider
from .mock import MockLLM, MockSTT, MockTTS


def build_stt(cfg: Settings) -> STTProvider:
    if cfg.stt_provider == "elevenlabs" and cfg.has_elevenlabs:
        from .stt_elevenlabs import ElevenLabsSTT

        logger.info("STT: ElevenLabs Scribe")
        return ElevenLabsSTT(cfg.elevenlabs_api_key, model=cfg.stt_model)
    logger.warning("STT: mock (нет ключа ElevenLabs)")
    return MockSTT()


def build_llm(cfg: Settings) -> LLMProvider:
    if cfg.llm_provider == "grok" and cfg.has_grok:
        from .llm_grok import GrokLLM

        logger.info(f"LLM: Grok ({cfg.grok_model})")
        return GrokLLM(
            api_key=cfg.xai_api_key,
            base_url=cfg.grok_base_url,
            model=cfg.grok_model,
            temperature=cfg.llm_temperature,
            max_tokens=cfg.llm_max_tokens,
        )
    logger.warning("LLM: mock (нет ключа XAI)")
    return MockLLM()


def build_tts(cfg: Settings) -> TTSProvider:
    if cfg.tts_provider == "elevenlabs" and cfg.has_elevenlabs and cfg.tts_voice_id:
        from .tts_elevenlabs import ElevenLabsTTS

        logger.info(f"TTS: ElevenLabs {cfg.tts_model}")
        return ElevenLabsTTS(
            api_key=cfg.elevenlabs_api_key,
            voice_id=cfg.tts_voice_id,
            model=cfg.tts_model,
            output_format=cfg.tts_output_format,
        )
    logger.warning("TTS: mock (нет ключа ElevenLabs или voice_id)")
    return MockTTS()


def build_providers(cfg: Settings) -> tuple[STTProvider, LLMProvider, TTSProvider]:
    return build_stt(cfg), build_llm(cfg), build_tts(cfg)
