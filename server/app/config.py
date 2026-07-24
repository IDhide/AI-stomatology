"""
Конфигурация серверного backend'а.

Все секреты и переключатели читаются из переменных окружения (.env).
Провайдеры (STT/LLM/TTS) выбираются строкой — это и есть слой абстракции:
поменять Grok на Claude или ElevenLabs на Silero можно, не трогая оркестратор.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Выбор провайдеров ────────────────────────────────────────────
    # "grok" | "claude" | "mock"
    llm_provider: str = Field(default="grok", alias="LLM_PROVIDER")
    # "elevenlabs" | "whisper" | "mock"
    stt_provider: str = Field(default="elevenlabs", alias="STT_PROVIDER")
    # "elevenlabs" | "mock"
    tts_provider: str = Field(default="elevenlabs", alias="TTS_PROVIDER")

    # ── Grok (xAI, OpenAI-совместимый API) ──────────────────────────
    xai_api_key: str = Field(default="", alias="XAI_API_KEY")
    grok_base_url: str = Field(default="https://api.x.ai/v1", alias="GROK_BASE_URL")
    # Для голоса нужна БЫСТРАЯ модель без reasoning: grok-4 «думает» перед
    # ответом десятки секунд — пациент столько ждать не будет
    grok_model: str = Field(default="grok-4-1-fast-non-reasoning", alias="GROK_MODEL")
    llm_temperature: float = Field(default=0.4, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=400, alias="LLM_MAX_TOKENS")

    # ── ElevenLabs (STT Scribe + TTS Flash) ─────────────────────────
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    tts_voice_id: str = Field(default="", alias="ELEVENLABS_VOICE_ID")
    tts_model: str = Field(default="eleven_flash_v2_5", alias="ELEVENLABS_TTS_MODEL")
    stt_model: str = Field(default="scribe_v1", alias="ELEVENLABS_STT_MODEL")
    # PCM 16k — удобно для браузера (WebAudio) и минимальной задержки
    tts_output_format: str = Field(default="pcm_16000", alias="ELEVENLABS_OUTPUT_FORMAT")

    # ── DIKIDI (только чтение записей) ──────────────────────────────
    dikidi_api_key: str = Field(default="", alias="DIKIDI_API_KEY")
    dikidi_company_id: str = Field(default="", alias="DIKIDI_COMPANY_ID")
    dikidi_base_url: str = Field(default="https://api.dikidi.net", alias="DIKIDI_BASE_URL")
    # true — подмешивать демо-записи, когда DIKIDI не подключён (только для теста!)
    dikidi_demo: bool = Field(default=False, alias="DIKIDI_DEMO")

    # ── Supabase (память + pgvector для лиц) ────────────────────────
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_key: str = Field(default="", alias="SUPABASE_KEY")

    # ── Диалоговая логика ───────────────────────────────────────────
    # Через сколько секунд молчания завершаем разговор (из ТЗ — 10 сек)
    silence_end_seconds: float = Field(default=10.0, alias="SILENCE_END_SECONDS")
    # Порог совпадения лица (косинусное сходство), из ТЗ 0.90–0.95
    face_match_threshold: float = Field(default=0.42, alias="FACE_MATCH_THRESHOLD")
    # «Здоровались недавно» — не приветствуем повторно N минут
    regreet_minutes: int = Field(default=45, alias="REGREET_MINUTES")

    prompts_path: str = Field(default="config/prompts.yaml", alias="PROMPTS_PATH")
    # Папка с логами разговоров (создаётся при первом запуске)
    conversations_dir: str = Field(default="data/conversations", alias="CONVERSATIONS_DIR")

    @property
    def has_grok(self) -> bool:
        return bool(self.xai_api_key)

    @property
    def has_elevenlabs(self) -> bool:
        return bool(self.elevenlabs_api_key)

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
