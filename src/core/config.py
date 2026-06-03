"""
core/config.py
==============
Загрузка конфигурации из YAML + .env.
Модели намеренно «открытые» (extra='allow'), чтобы новые секции не ломали
обратную совместимость с уже написанным кодом.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class CameraConfig(_Loose):
    device_index: int = 0
    rtsp_url: str = ""
    resolution: dict = {"width": 1280, "height": 720}
    fps: int = 15
    detection: dict = {
        "face_confidence": 0.7,
        "motion_threshold": 25,
        "cooldown_seconds": 2,
        "presence_lost_after": 3.0,
    }


class VoiceConfig(_Loose):
    stt: dict = Field(default_factory=dict)
    tts: dict = Field(default_factory=dict)


class LLMConfig(_Loose):
    provider: str = "ollama"
    model: str = "smile-ru"
    fallback_model: str = "qwen2.5:7b-instruct-q4_K_M"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.4
    max_tokens: int = 512
    num_ctx: int = 4096
    # system_prompt теперь опционально — основной живёт в config/prompts.yaml
    system_prompt: str = ""


class DikidiConfig(_Loose):
    api_key: str = ""
    token: str = ""
    company_id: str = ""
    base_url: str = "https://api.dikidi.net"
    timeout: int = 15
    retry_attempts: int = 3


class UIConfig(_Loose):
    window: dict = Field(default_factory=dict)
    circle: dict = Field(default_factory=dict)
    idle_video: dict = Field(default_factory=dict)


class TimeoutsConfig(_Loose):
    idle_return: int = 10
    goodbye_delay: int = 3
    max_conversation: int = 300
    warmup_after_face: float = 0.5


class LoggingConfig(_Loose):
    level: str = "INFO"
    console: bool = True
    file: dict = Field(default_factory=dict)
    conversations: dict = Field(default_factory=dict)


class AppConfig(_Loose):
    name: str = "Smile.AI"
    version: str = "0.2.0"
    debug: bool = False
    clinic_name: str = "Клиника Smile"
    address: str = ""


class DentalConfig(_Loose):
    enable_humor: bool = True
    humor_probability: float = 0.45
    min_turns_between_jokes: int = 3
    working_hours: dict = Field(default_factory=dict)
    alert_on_urgent: bool = True
    alert_channel: str = "none"


class Config(_Loose):
    app: AppConfig = Field(default_factory=AppConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    dikidi: DikidiConfig = Field(default_factory=DikidiConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    dental: DentalConfig = Field(default_factory=DentalConfig)


def load_config(config_path: str | None = None) -> Config:
    """Загрузка конфигурации из YAML и переменных окружения."""
    load_dotenv()
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # .env переопределяет
    dikidi = data.setdefault("dikidi", {})
    if os.getenv("DIKIDI_TOKEN"):
        dikidi["token"] = os.getenv("DIKIDI_TOKEN")
    if os.getenv("DIKIDI_API_KEY"):
        dikidi["api_key"] = os.getenv("DIKIDI_API_KEY")
    if os.getenv("DIKIDI_COMPANY_ID"):
        dikidi["company_id"] = os.getenv("DIKIDI_COMPANY_ID")
    cam = data.setdefault("camera", {})
    if os.getenv("RTSP_URL"):
        cam["rtsp_url"] = os.getenv("RTSP_URL")
    llm = data.setdefault("llm", {})
    if os.getenv("OLLAMA_HOST"):
        llm["base_url"] = os.getenv("OLLAMA_HOST")
    if os.getenv("OLLAMA_MODEL"):
        llm["model"] = os.getenv("OLLAMA_MODEL")

    return Config(**data)
