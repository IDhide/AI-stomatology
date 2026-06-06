"""
tts.py
======
Серверный синтез речи (TTS). Отдаёт WAV в браузер.

Два движка (выбор через TTS_ENGINE):
  • silero  — естественный человеческий женский голос (по умолчанию).
              Русские голоса Silero v4 (baya/xenia/kseniya) звучат живо,
              с интонацией и правильными ударениями. Работает на CPU,
              полностью локально (важно для медицины — ничего не уходит наружу).
  • piper    — лёгкий запасной движок (ru_RU/irina), если нет torch.

Зачем сервер, а не браузер: голос Web Speech API зависит от ОС/браузера
(в Firefox роботичный), нет контроля над тембром. Серверный движок даёт
одинаковый красивый голос в любом браузере.

Переменные окружения:
  TTS_ENGINE          — silero | piper (по умолчанию silero)
  ── Silero ──
  SILERO_SPEAKER      — голос: baya | xenia | kseniya | eugene | aidar
                        (по умолчанию baya — тёплый женский тембр)
  SILERO_SAMPLE_RATE  — 8000 | 24000 | 48000 (по умолчанию 48000, max качество)
  SILERO_MODEL_DIR    — куда скачать модель (по умолчанию /app/models/silero)
  ── Piper (запасной) ──
  PIPER_VOICE_DIR     — каталог моделей Piper
  PIPER_SPEAKER       — номер голоса (по умолчанию 0)
  PIPER_LENGTH        — коэффициент длительности (1.0 норм, >1 медленнее)
"""
from __future__ import annotations

import io
import os
import re
import urllib.request
import wave
from pathlib import Path

from loguru import logger

_load_error: str | None = None


def _engine() -> str:
    return os.getenv("TTS_ENGINE", "silero").strip().lower()


# ════════════════════════════════════════════════════════════════════
#  Silero — естественный женский голос
# ════════════════════════════════════════════════════════════════════
_silero_model = None
_SILERO_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"


def _silero_dir() -> Path:
    return Path(os.getenv("SILERO_MODEL_DIR", "/app/models/silero"))


def _get_silero():
    """Ленивая загрузка Silero (один раз на процесс)."""
    global _silero_model, _load_error
    if _silero_model is not None:
        return _silero_model
    if _load_error is not None:
        return None
    try:
        import torch  # type: ignore
    except Exception as e:
        _load_error = f"torch не установлен ({e})"
        logger.warning(f"TTS Silero недоступен: {_load_error}")
        return None

    d = _silero_dir()
    d.mkdir(parents=True, exist_ok=True)
    model_path = d / "v4_ru.pt"
    if not model_path.exists() or model_path.stat().st_size < 1_000_000:
        logger.info("Silero: скачиваю модель v4_ru (~50 МБ)…")
        try:
            torch.hub.download_url_to_file(_SILERO_URL, str(model_path))
            logger.success(f"Silero: модель загружена ({model_path.stat().st_size // 1024 // 1024} МБ)")
        except Exception as e:
            _load_error = f"не удалось скачать модель Silero: {e}"
            logger.error(f"TTS: {_load_error}")
            return None

    try:
        logger.info("TTS: загружаю Silero v4_ru…")
        torch.set_num_threads(int(os.getenv("TORCH_NUM_THREADS", "4") or 4))
        model = torch.package.PackageImporter(str(model_path)).load_pickle("tts_models", "model")
        model.to("cpu")
        _silero_model = model
        logger.success("TTS готов (Silero, голос — живой женский)")
        return _silero_model
    except Exception as e:
        _load_error = f"не удалось загрузить Silero ({e})"
        logger.error(f"TTS: {_load_error}")
        return None


def _split_for_silero(text: str, limit: int = 900) -> list[str]:
    """Silero ограничивает длину одного вызова — режем по предложениям."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?…])\s+", text):
        if len(cur) + len(sent) + 1 > limit and cur:
            parts.append(cur.strip())
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur.strip())
    return parts or [text[:limit]]


def _silero_synthesize(text: str) -> tuple[bytes, str | None]:
    model = _get_silero()
    if model is None:
        return b"", _load_error or "silero_unavailable"
    import numpy as np  # идёт вместе с torch

    speaker = os.getenv("SILERO_SPEAKER", "baya").strip() or "baya"
    sample_rate = int(os.getenv("SILERO_SAMPLE_RATE", "48000") or 48000)

    try:
        chunks = []
        for piece in _split_for_silero(text):
            audio = model.apply_tts(
                text=piece,
                speaker=speaker,
                sample_rate=sample_rate,
                put_accent=True,   # автоматическая расстановка ударений
                put_yo=True,       # ё → правильное произношение
            )
            chunks.append(audio.numpy())
        wav = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        pcm16 = (np.clip(wav, -1.0, 1.0) * 32767).astype("<i2")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())
        return buf.getvalue(), None
    except Exception as e:
        logger.exception("Silero synthesize error")
        return b"", f"synth_failed: {e}"


# ════════════════════════════════════════════════════════════════════
#  Piper — лёгкий запасной движок (ru_RU/irina)
# ════════════════════════════════════════════════════════════════════
_piper_voice = None
_PIPER_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "ru/ru_RU/irina/medium"
)
_PIPER_FILES = {
    "ru_RU-irina-medium.onnx": f"{_PIPER_BASE}/ru_RU-irina-medium.onnx?download=true",
    "ru_RU-irina-medium.onnx.json": f"{_PIPER_BASE}/ru_RU-irina-medium.onnx.json?download=true",
}


def _piper_dir() -> Path:
    return Path(os.getenv("PIPER_VOICE_DIR", "/app/models/piper"))


def _download_piper() -> Path | None:
    if os.getenv("PIPER_DOWNLOAD", "true").lower() not in ("true", "1", "yes"):
        return None
    d = _piper_dir()
    d.mkdir(parents=True, exist_ok=True)
    onnx = d / "ru_RU-irina-medium.onnx"
    for name, url in _PIPER_FILES.items():
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


def _get_piper():
    global _piper_voice, _load_error
    if _piper_voice is not None:
        return _piper_voice
    if _load_error is not None:
        return None
    try:
        from piper import PiperVoice  # type: ignore
    except Exception as e:
        _load_error = f"piper-tts не установлен ({e})"
        logger.warning(f"TTS Piper недоступен: {_load_error}")
        return None

    explicit = os.getenv("PIPER_VOICE", "").strip()
    onnx = Path(explicit) if explicit else None
    if onnx is None or not onnx.exists():
        onnx = _download_piper()
    if onnx is None or not onnx.exists():
        _load_error = "модель Piper не найдена"
        logger.error(f"TTS: {_load_error}")
        return None
    try:
        logger.info(f"TTS: загружаю Piper {onnx.name}…")
        _piper_voice = PiperVoice.load(str(onnx))
        logger.success("TTS готов (Piper)")
        return _piper_voice
    except Exception as e:
        _load_error = f"не удалось загрузить Piper ({e})"
        logger.error(f"TTS: {_load_error}")
        return None


def _piper_synthesize(text: str) -> tuple[bytes, str | None]:
    voice = _get_piper()
    if voice is None:
        return b"", _load_error or "piper_unavailable"
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
        logger.exception("Piper synthesize error")
        return b"", f"synth_failed: {e}"


# ════════════════════════════════════════════════════════════════════
#  Публичный API
# ════════════════════════════════════════════════════════════════════
def is_available() -> bool:
    if _engine() == "piper":
        return _get_piper() is not None
    return _get_silero() is not None


def synthesize(text: str) -> tuple[bytes, str | None]:
    """Синтезирует речь → (WAV-байты, ошибка)."""
    if not text or not text.strip():
        return b"", "empty_text"
    if _engine() == "piper":
        return _piper_synthesize(text)
    return _silero_synthesize(text)
