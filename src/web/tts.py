"""
tts.py
======
Серверный синтез речи (TTS) на Piper. Отдаёт WAV в браузер.

Зачем сервер, а не браузер: голос Web Speech API зависит от ОС/браузера
(в Firefox для русского часто роботичный, нет контроля над тембром/скоростью),
плюс в Chrome STT шёл в Google. С серверным Piper:
  • одинаковый голос в любом браузере
  • полностью локально (приватность, медицина — это важно)
  • быстро на CPU (~0.5–1.5 с на короткую реплику)

Pипер берёт голосовую модель .onnx + .onnx.json. Русская модель:
  https://huggingface.co/rhasspy/piper-voices  → ru/ru_RU/dmitri/medium

Переменные окружения:
  PIPER_VOICE       — путь к .onnx (если задан) или имя модели
  PIPER_VOICE_DIR   — каталог, куда скачивать (по умолчанию /app/models/piper)
  PIPER_DOWNLOAD    — true|false (по умолчанию true — скачиваем при первом запросе)
  PIPER_SPEAKER     — номер голоса для многоголосых моделей (по умолчанию 0)
  PIPER_LENGTH      — коэффициент длительности (1.0 норм, >1 медленнее)
"""
from __future__ import annotations

import io
import os
import urllib.request
import wave
from pathlib import Path

from loguru import logger

_voice = None
_load_error: str | None = None

# Русский голос Piper: dmitri / medium (~63 МБ + json ~ КБ)
_VOICE_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "ru/ru_RU/dmitri/medium"
)
_VOICE_FILES = {
    "ru_RU-dmitri-medium.onnx": f"{_VOICE_BASE}/ru_RU-dmitri-medium.onnx?download=true",
    "ru_RU-dmitri-medium.onnx.json": f"{_VOICE_BASE}/ru_RU-dmitri-medium.onnx.json?download=true",
}


def _voice_dir() -> Path:
    return Path(os.getenv("PIPER_VOICE_DIR", "/app/models/piper"))


def _download_voice() -> Path | None:
    """Скачиваем модель в кэш, если её нет. Возвращаем путь к .onnx."""
    if os.getenv("PIPER_DOWNLOAD", "true").lower() not in ("true", "1", "yes"):
        return None
    d = _voice_dir()
    d.mkdir(parents=True, exist_ok=True)
    onnx = d / "ru_RU-dmitri-medium.onnx"
    for name, url in _VOICE_FILES.items():
        dst = d / name
        if dst.exists() and dst.stat().st_size > 1000:
            continue
        logger.info(f"Piper: скачиваю {name}…")
        try:
            urllib.request.urlretrieve(url, dst)
            logger.success(f"Piper: {name} ({dst.stat().st_size // 1024} КБ)")
        except Exception as e:
            logger.error(f"Piper: не удалось скачать {name}: {e}")
            return None
    return onnx if onnx.exists() else None


def _get_voice():
    """Ленивая загрузка модели (один раз на процесс)."""
    global _voice, _load_error
    if _voice is not None:
        return _voice
    if _load_error is not None:
        return None
    try:
        from piper import PiperVoice  # type: ignore
    except Exception as e:
        _load_error = f"piper-tts не установлен ({e})"
        logger.warning(f"TTS недоступен: {_load_error}. Установите: pip install piper-tts")
        return None

    # путь к модели: явный, либо скачиваем по умолчанию
    explicit = os.getenv("PIPER_VOICE", "").strip()
    onnx = Path(explicit) if explicit else None
    if onnx is None or not onnx.exists():
        onnx = _download_voice()
    if onnx is None or not onnx.exists():
        _load_error = "модель Piper не найдена и не скачана"
        logger.error(f"TTS: {_load_error}")
        return None

    try:
        logger.info(f"TTS: загружаю Piper {onnx.name}…")
        _voice = PiperVoice.load(str(onnx))
        logger.success("TTS готов")
        return _voice
    except Exception as e:
        _load_error = f"не удалось загрузить голос ({e})"
        logger.error(f"TTS: {_load_error}")
        return None


def is_available() -> bool:
    return _get_voice() is not None


def synthesize(text: str) -> tuple[bytes, str | None]:
    """Синтезирует речь → возвращает (WAV-байты, ошибка)."""
    voice = _get_voice()
    if voice is None:
        return b"", _load_error or "tts_unavailable"
    if not text or not text.strip():
        return b"", "empty_text"

    try:
        from piper.config import SynthesisConfig
        cfg = SynthesisConfig(
            speaker_id=int(os.getenv("PIPER_SPEAKER", "0") or 0),
            length_scale=float(os.getenv("PIPER_LENGTH", "1.0") or 1.0),
        )
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf, syn_config=cfg)
        return buf.getvalue(), None
    except Exception as e:
        logger.exception("TTS synthesize error")
        return b"", f"synth_failed: {e}"
