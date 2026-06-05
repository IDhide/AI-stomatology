"""
stt.py
======
Серверное распознавание речи (STT) для браузеров без Web Speech API
(в первую очередь Firefox). Браузер пишет аудио через MediaRecorder и шлёт
его на /api/stt; здесь оно превращается в текст.

Движок — faster-whisper (CTranslate2, без torch). Модель скачивается с
HuggingFace при первом запросе и кэшируется. Если библиотека/модель
недоступны — возвращаем понятную ошибку, а UI переключается на ввод текстом.

Переменные окружения:
  STT_MODEL    — размер модели: tiny | base | small | medium  (по умолчанию small)
  STT_DEVICE   — cpu | cuda                                    (по умолчанию cpu)
  STT_COMPUTE  — int8 | int8_float16 | float16 | float32       (по умолчанию int8)
"""
from __future__ import annotations

import os
import tempfile

from loguru import logger

_model = None
_load_error: str | None = None


def _get_model():
    """Ленивая загрузка модели (один раз на процесс)."""
    global _model, _load_error
    if _model is not None:
        return _model
    if _load_error is not None:
        return None
    try:
        from faster_whisper import WhisperModel
    except Exception as e:  # библиотека не установлена
        _load_error = f"faster-whisper не установлен ({e})"
        logger.warning(f"STT недоступен: {_load_error}. "
                       "Установите: pip install -r requirements-stt.txt")
        return None
    try:
        size = os.getenv("STT_MODEL", "small")
        device = os.getenv("STT_DEVICE", "cpu")
        compute = os.getenv("STT_COMPUTE", "int8")
        logger.info(f"STT: загружаю faster-whisper '{size}' ({device}/{compute})…")
        _model = WhisperModel(size, device=device, compute_type=compute)
        logger.success("STT готов")
        return _model
    except Exception as e:
        _load_error = f"не удалось загрузить модель ({e})"
        logger.error(f"STT: {_load_error}")
        return None


def is_available() -> bool:
    return _get_model() is not None


def transcribe(audio_bytes: bytes, suffix: str = ".webm") -> tuple[str, str | None]:
    """
    Распознать аудио (webm/opus/ogg/wav). Возвращает (текст, ошибка).
    Декодирование делает PyAV внутри faster-whisper, системный ffmpeg не нужен.
    """
    model = _get_model()
    if model is None:
        return "", _load_error or "stt_unavailable"
    if not audio_bytes:
        return "", "empty_audio"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            segments, _info = model.transcribe(
                tmp_path, language="ru", vad_filter=True, beam_size=5
            )
        except Exception:
            # VAD требует onnxruntime — если его нет, пробуем без него
            segments, _info = model.transcribe(tmp_path, language="ru", beam_size=5)
        text = " ".join(s.text.strip() for s in segments).strip()
        return text, None
    except Exception as e:
        logger.exception("STT transcribe error")
        return "", f"transcribe_failed: {e}"
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
