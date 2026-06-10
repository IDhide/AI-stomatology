"""
tts.py
======
Серверный синтез речи (TTS). Отдаёт WAV в браузер.

Движки (выбор через TTS_ENGINE):
  • qwen3vc — КЛОНИРОВАНИЕ голоса из образца (Qwen3-TTS-VC). Говорит голосом
              из вашего референс-аудио: живая интонация, ударения, мягкий тембр.
              Требует GPU (CUDA). Полностью локально (важно для медицины).
  • silero  — естественный человеческий женский голос (по умолчанию).
              Русские голоса Silero v4 (baya/xenia/kseniya), CPU, локально.
  • piper    — лёгкий запасной движок (ru_RU/irina), если нет torch.

Зачем сервер, а не браузер: голос Web Speech API зависит от ОС/браузера
(в Firefox роботичный), нет контроля над тембром. Серверный движок даёт
одинаковый красивый голос в любом браузере.

Переменные окружения:
  TTS_ENGINE          — qwen3vc | silero | piper (по умолчанию silero)
  ── Qwen3-TTS-VC (клонирование голоса, GPU) ──
  QWEN_REF_AUDIO      — путь к образцу голоса (wav/mp3, 10–15 с чистой речи)
  QWEN_REF_TEXT       — точная расшифровка образца (что произнесено в нём)
  QWEN_REF_TEXT_FILE  — либо файл с расшифровкой (альтернатива QWEN_REF_TEXT)
  QWEN_TTS_MODEL      — модель (по умолчанию Qwen/Qwen3-TTS-12Hz-1.7B-Base)
  QWEN_DEVICE         — cuda:0 | cuda | cpu (по умолчанию cuda:0)
  QWEN_LANGUAGE       — язык синтеза (по умолчанию Russian)
  QWEN_ATTN           — flash_attention_2 | sdpa | eager (по умолчанию sdpa)
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

# Раздельные ошибки на каждый движок — чтобы падение одного не блокировало другие.
_qwen_error: str | None = None
_silero_error: str | None = None
_piper_error: str | None = None


def _engine() -> str:
    return os.getenv("TTS_ENGINE", "silero").strip().lower()


# ════════════════════════════════════════════════════════════════════
#  Qwen3-TTS-VC — клонирование голоса из образца (GPU)
# ════════════════════════════════════════════════════════════════════
_qwen_model = None
_qwen_prompt = None  # переиспользуемый voice-clone prompt (извлекаем тембр один раз)


def _qwen_ref_text() -> str:
    txt = os.getenv("QWEN_REF_TEXT", "").strip()
    if txt:
        return txt
    f = os.getenv("QWEN_REF_TEXT_FILE", "").strip()
    if f and Path(f).exists():
        return Path(f).read_text(encoding="utf-8").strip()
    return ""


def _free_cuda():
    """Освободить GPU-память после неудачной загрузки модели."""
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def _get_qwen():
    """Ленивая загрузка Qwen3-TTS-VC и подготовка voice-clone prompt."""
    global _qwen_model, _qwen_prompt, _qwen_error
    if _qwen_model is not None:
        return _qwen_model
    if _qwen_error is not None:
        return None

    ref_audio = os.getenv("QWEN_REF_AUDIO", "").strip()
    ref_text = _qwen_ref_text()
    if not ref_audio or not Path(ref_audio).exists():
        _qwen_error = f"QWEN_REF_AUDIO не найден ({ref_audio or 'не задан'})"
        logger.error(f"TTS Qwen: {_qwen_error}")
        return None
    if not ref_text:
        _qwen_error = "QWEN_REF_TEXT/QWEN_REF_TEXT_FILE не заданы (нужна расшифровка образца)"
        logger.error(f"TTS Qwen: {_qwen_error}")
        return None

    try:
        import torch  # type: ignore
        from qwen_tts import Qwen3TTSModel  # type: ignore
    except Exception as e:
        _qwen_error = f"qwen-tts/torch не установлены ({e})"
        logger.warning(f"TTS Qwen недоступен: {_qwen_error}. Установите: pip install qwen-tts")
        return None

    model_name = os.getenv("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    device = os.getenv("QWEN_DEVICE", "cuda:0")
    attn = os.getenv("QWEN_ATTN", "sdpa")
    dtype = torch.bfloat16 if "cuda" in device else torch.float32

    # Цепочка попыток: сначала выбранный attn, потом eager (минимум памяти).
    # При OOM/нехватке памяти повторяем на eager. Если и это не лезет — сдаёмся
    # и фолбэк (Silero) подхватится выше в synthesize().
    attempts = [attn]
    if attn != "eager":
        attempts.append("eager")

    last_exc: Exception | None = None
    for attempt_attn in attempts:
        try:
            logger.info(f"TTS: загружаю Qwen3-TTS-VC {model_name} ({device}, attn={attempt_attn})…")
            model = Qwen3TTSModel.from_pretrained(
                model_name, device_map=device, dtype=dtype,
                attn_implementation=attempt_attn,
            )
            _qwen_model = model
            break
        except Exception as e:
            last_exc = e
            logger.warning(f"Qwen: загрузка с attn={attempt_attn} не удалась ({e})")
            # подчищаем недо-загруженные тензоры с GPU перед следующей попыткой
            _free_cuda()

    if _qwen_model is None:
        _qwen_error = f"не удалось загрузить Qwen3-TTS-VC ({last_exc})"
        logger.error(f"TTS: {_qwen_error}")
        return None

    # извлекаем тембр из образца ОДИН раз — дальше переиспользуем
    if hasattr(_qwen_model, "create_voice_clone_prompt"):
        try:
            _qwen_prompt = _qwen_model.create_voice_clone_prompt(
                ref_audio=ref_audio, ref_text=ref_text,
            )
            logger.success("Qwen: voice-clone prompt готов (тембр извлечён из образца)")
        except Exception as e:
            logger.warning(f"Qwen: create_voice_clone_prompt не удался ({e}), "
                           "буду передавать образец каждый раз")
            _qwen_prompt = None
    logger.success("TTS готов (Qwen3-TTS-VC — клонированный голос)")
    return _qwen_model


def _qwen_synthesize(text: str) -> tuple[bytes, str | None]:
    model = _get_qwen()
    if model is None:
        return b"", _qwen_error or "qwen_unavailable"
    import numpy as np

    language = os.getenv("QWEN_LANGUAGE", "Russian")
    ref_audio = os.getenv("QWEN_REF_AUDIO", "").strip()
    ref_text = _qwen_ref_text()
    try:
        kwargs: dict = {"text": text, "language": language}
        if _qwen_prompt is not None:
            kwargs["voice_clone_prompt"] = _qwen_prompt
        else:
            kwargs["ref_audio"] = ref_audio
            kwargs["ref_text"] = ref_text
        wavs, sr = model.generate_voice_clone(**kwargs)
        wav = np.asarray(wavs[0], dtype="float32")
        pcm16 = (np.clip(wav, -1.0, 1.0) * 32767).astype("<i2")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sr))
            wf.writeframes(pcm16.tobytes())
        return buf.getvalue(), None
    except Exception as e:
        logger.exception("Qwen synthesize error")
        return b"", f"synth_failed: {e}"


# ════════════════════════════════════════════════════════════════════
#  Silero — естественный женский голос
# ════════════════════════════════════════════════════════════════════
_silero_model = None
_SILERO_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"


def _silero_dir() -> Path:
    return Path(os.getenv("SILERO_MODEL_DIR", "/app/models/silero"))


def _get_silero():
    """Ленивая загрузка Silero (один раз на процесс)."""
    global _silero_model, _silero_error
    if _silero_model is not None:
        return _silero_model
    if _silero_error is not None:
        return None
    try:
        import torch  # type: ignore
    except Exception as e:
        _silero_error = f"torch не установлен ({e})"
        logger.warning(f"TTS Silero недоступен: {_silero_error}")
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
            _silero_error = f"не удалось скачать модель Silero: {e}"
            logger.error(f"TTS: {_silero_error}")
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
        _silero_error = f"не удалось загрузить Silero ({e})"
        logger.error(f"TTS: {_silero_error}")
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
        return b"", _silero_error or "silero_unavailable"
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
    global _piper_voice, _piper_error
    if _piper_voice is not None:
        return _piper_voice
    if _piper_error is not None:
        return None
    try:
        from piper import PiperVoice  # type: ignore
    except Exception as e:
        _piper_error = f"piper-tts не установлен ({e})"
        logger.warning(f"TTS Piper недоступен: {_piper_error}")
        return None

    explicit = os.getenv("PIPER_VOICE", "").strip()
    onnx = Path(explicit) if explicit else None
    if onnx is None or not onnx.exists():
        onnx = _download_piper()
    if onnx is None or not onnx.exists():
        _piper_error = "модель Piper не найдена"
        logger.error(f"TTS: {_piper_error}")
        return None
    try:
        logger.info(f"TTS: загружаю Piper {onnx.name}…")
        _piper_voice = PiperVoice.load(str(onnx))
        logger.success("TTS готов (Piper)")
        return _piper_voice
    except Exception as e:
        _piper_error = f"не удалось загрузить Piper ({e})"
        logger.error(f"TTS: {_piper_error}")
        return None


def _piper_synthesize(text: str) -> tuple[bytes, str | None]:
    voice = _get_piper()
    if voice is None:
        return b"", _piper_error or "piper_unavailable"
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
    """Доступен хоть какой-то движок? (нужно для /api/tts/status)."""
    eng = _engine()
    # пробуем выбранный движок, потом фолбэки — лишь бы голос был
    if eng == "qwen3vc" and _get_qwen() is not None:
        return True
    if eng == "piper" and _get_piper() is not None:
        return True
    if eng == "silero" and _get_silero() is not None:
        return True
    # фолбэк: что-то из остальных
    return _get_silero() is not None or _get_piper() is not None


def synthesize(text: str) -> tuple[bytes, str | None]:
    """Синтезирует речь → (WAV-байты, ошибка).

    Цепочка фолбэков: при сбое выбранного движка пробуем следующий, чтобы
    голос звучал даже если, например, Qwen не влез в GPU.
    """
    if not text or not text.strip():
        return b"", "empty_text"
    eng = _engine()

    if eng == "qwen3vc":
        audio, err = _qwen_synthesize(text)
        if not err:
            return audio, None
        logger.warning(f"TTS: Qwen упал ({err}), фолбэк → Silero")
        audio, err2 = _silero_synthesize(text)
        if not err2:
            return audio, None
        return _piper_synthesize(text)

    if eng == "piper":
        audio, err = _piper_synthesize(text)
        if not err:
            return audio, None
        logger.warning(f"TTS: Piper упал ({err}), фолбэк → Silero")
        return _silero_synthesize(text)

    # silero (по умолчанию)
    audio, err = _silero_synthesize(text)
    if not err:
        return audio, None
    logger.warning(f"TTS: Silero упал ({err}), фолбэк → Piper")
    return _piper_synthesize(text)
