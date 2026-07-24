"""
tts.py
======
Серверный синтез речи (TTS). Отдаёт WAV в браузер.

Движки (выбор через TTS_ENGINE):
  • fishaudio — КЛОНИРОВАНИЕ голоса (Fish Speech / OpenAudio S1, open-source).
              Очень живой, эмоциональный голос, отличный русский. Работает
              отдельным локальным сервером (без облака и API-ключей), web
              обращается к нему по HTTP. Лучшее качество; рекомендуется GPU
              (~4 ГБ VRAM), на CPU работает, но медленно. Лицензия Apache 2.0.
  • xtts    — КЛОНИРОВАНИЕ голоса (Coqui XTTS v2). Лёгкий (467M, ~2 ГБ VRAM),
              быстрый (на RTX 3060 ×5-10 realtime, на CPU ~1× realtime),
              русский язык, клонирование из 10-сек референса. Рекомендуется
              для киоска на 3060/Ryzen 5. Лицензия CPML (non-commercial —
              уточните у Coqui для коммерческого использования).
  • qwen     — Qwen3-TTS CustomVoice (1.7B, открытые веса, GPU ~8–12 ГБ VRAM).
              Лучшее качество русского на сегодня, готовые тембры БЕЗ образца
              голоса. Тембр — QWEN_SPEAKER. Рекомендуется для RTX 3060 12 ГБ.
              Apache 2.0. Ударения определяет сама модель (не RUAccent).
  • qwen3vc — КЛОНИРОВАНИЕ голоса (Qwen3-TTS-VC, 1.7B, ~4 ГБ VRAM). Высокое
              качество, но нужен образец голоса + расшифровка. Apache 2.0.
  • silero  — естественный человеческий женский голос (по умолчанию).
              Русские голоса Silero v4 (baya/xenia/kseniya), CPU, локально.
  • piper    — лёгкий запасной движок (ru_RU/irina), если нет torch.

Зачем сервер, а не браузер: голос Web Speech API зависит от ОС/браузера
(в Firefox роботичный), нет контроля над тембром. Серверный движок даёт
одинаковый красивый голос в любом браузере.

Переменные окружения:
  TTS_ENGINE          — fishaudio | xtts | qwen | qwen3vc | silero | piper
                        (по умолчанию silero)
  ── Fish Speech / OpenAudio (клонирование голоса, локальный сервер) ──
  FISH_API_URL        — адрес локального сервера Fish Speech
                        (по умолчанию http://fish-speech:8080)
  FISH_REF_AUDIO      — путь к образцу голоса (wav/mp3, 10–15 с чистой речи)
  FISH_REF_TEXT       — точная расшифровка образца (что произнесено в нём)
  FISH_REF_TEXT_FILE  — либо файл с расшифровкой (альтернатива FISH_REF_TEXT)
  FISH_TEMPERATURE    — «живость»/вариативность (по умолчанию 0.7)
  FISH_TOP_P          — отсечение по вероятности (по умолчанию 0.7)
  FISH_REP_PENALTY    — штраф за повторы (по умолчанию 1.2)
  FISH_TIMEOUT        — таймаут запроса к серверу, сек (по умолчанию 60)
  ── XTTS v2 (клонирование голоса, GPU/CPU) ──
  XTTS_REF_AUDIO      — путь к образцу голоса (wav, 10–15 с чистой речи)
  XTTS_DEVICE         — cuda | cpu (по умолчанию: cuda если доступна, иначе cpu)
  XTTS_LANGUAGE       — язык (по умолчанию ru)
  XTTS_MODEL_DIR      — куда скачать модель (~1.8 ГБ)
  ── Qwen3-TTS CustomVoice (готовые тембры, GPU) ──
  QWEN_SPEAKER        — тембр: Vivian | Serena | Ono_Anna | Sohee (женские),
                        Ryan | Aiden | Uncle_Fu | Dylan | Eric (мужские)
                        (по умолчанию Vivian — женский)
  QWEN_CV_MODEL       — модель CustomVoice (по умолчанию 1.7B-CustomVoice).
                        Отдельно от QWEN_TTS_MODEL (та — для клонирования qwen3vc)
  QWEN_LANGUAGE       — язык речи (по умолчанию Russian)
  QWEN_DEVICE         — cuda:0 | cpu (по умолчанию cuda:0)
  QWEN_ATTN           — sdpa | flash_attention_2 | eager (по умолчанию sdpa)
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
import threading
import urllib.request
import wave
from collections import OrderedDict
from pathlib import Path

from loguru import logger

# Раздельные ошибки на каждый движок — чтобы падение одного не блокировало другие.
_fish_error: str | None = None
_qwen_error: str | None = None
_xtts_error: str | None = None
_silero_error: str | None = None
_piper_error: str | None = None


def _engine() -> str:
    return os.getenv("TTS_ENGINE", "silero").strip().lower()


# Поддерживаемые форматы образца голоса (по приоритету: wav надёжнее всего).
_VOICE_REF_EXTS = (".wav", ".flac", ".mp3", ".ogg", ".m4a")


def _resolve_voice_ref(path: str) -> str:
    """Вернуть путь к образцу голоса. Если указанного файла нет — поискать
    рядом файл с тем же именем, но другим расширением (напр. задан
    reference.wav, а лежит reference.mp3). Так образец «просто находится»."""
    path = (path or "").strip()
    if path and Path(path).exists():
        return path
    if not path:
        return ""
    p = Path(path)
    for ext in _VOICE_REF_EXTS:
        cand = p.with_suffix(ext)
        if cand.exists():
            return str(cand)
    return path  # ничего не нашли — вернём как было (для понятной ошибки)


# ════════════════════════════════════════════════════════════════════
#  Fish Speech / OpenAudio S1 — клонирование голоса (локальный сервер)
# ════════════════════════════════════════════════════════════════════
#  Тяжёлая модель крутится отдельным контейнером (как Ollama), а web
#  обращается к ней по HTTP — образ киоска остаётся лёгким. Полностью
#  локально: ни облака, ни API-ключей.
_fish_ref_cache: tuple[bytes, str] | None = None


def _fish_api_url() -> str:
    return os.getenv("FISH_API_URL", "http://fish-speech:8080").rstrip("/")


def _fish_reference() -> tuple[bytes | None, str]:
    """Образец голоса (байты аудио + расшифровка) для клонирования.

    Читаем один раз и кэшируем — файл на каждый запрос дёргать незачем.
    Если образца нет — вернём (None, ""), Fish озвучит дефолтным голосом.
    """
    global _fish_ref_cache
    if _fish_ref_cache is not None:
        return _fish_ref_cache

    audio_path = os.getenv("FISH_REF_AUDIO", "").strip()
    ref_text = os.getenv("FISH_REF_TEXT", "").strip()
    if not ref_text:
        f = os.getenv("FISH_REF_TEXT_FILE", "").strip()
        if f and Path(f).exists():
            ref_text = Path(f).read_text(encoding="utf-8").strip()

    if audio_path and Path(audio_path).exists():
        try:
            data = Path(audio_path).read_bytes()
            _fish_ref_cache = (data, ref_text)
            logger.info(f"Fish Speech: образец голоса загружен ({len(data) // 1024} КБ)")
            return _fish_ref_cache
        except Exception as e:
            logger.warning(f"Fish Speech: не удалось прочитать образец {audio_path}: {e}")
    return None, ""


def _fish_health() -> bool:
    """Доступен ли сервер Fish Speech (короткий пинг корня)."""
    global _fish_error
    try:
        import requests  # type: ignore
    except Exception as e:
        _fish_error = f"requests не установлен ({e})"
        return False
    base = _fish_api_url()
    try:
        # requests не бросает на 4xx/5xx — любой HTTP-ответ значит, что
        # сервер поднят и слушает. Падаем только на отказе соединения.
        requests.get(f"{base}/", timeout=3)
        _fish_error = None
        return True
    except Exception as e:
        _fish_error = f"сервер недоступен по {base} ({e})"
        return False


def _fishaudio_synthesize(text: str) -> tuple[bytes, str | None]:
    try:
        import ormsgpack  # type: ignore
        import requests  # type: ignore
    except Exception as e:
        return b"", f"ormsgpack/requests не установлены ({e})"

    audio, ref_text = _fish_reference()
    req: dict = {
        "text": text,
        "format": "wav",
        "references": [],
        "chunk_length": int(os.getenv("FISH_CHUNK_LENGTH", "200") or 200),
        "top_p": float(os.getenv("FISH_TOP_P", "0.7") or 0.7),
        "repetition_penalty": float(os.getenv("FISH_REP_PENALTY", "1.2") or 1.2),
        "temperature": float(os.getenv("FISH_TEMPERATURE", "0.7") or 0.7),
        "max_new_tokens": int(os.getenv("FISH_MAX_TOKENS", "1024") or 1024),
        "streaming": False,
        "use_memory_cache": "on",
    }
    # Клонирование голоса из образца (если он есть)
    if audio is not None:
        req["references"] = [{"audio": audio, "text": ref_text}]

    try:
        resp = requests.post(
            f"{_fish_api_url()}/v1/tts",
            data=ormsgpack.packb(req),
            headers={"content-type": "application/msgpack"},
            timeout=float(os.getenv("FISH_TIMEOUT", "60") or 60),
        )
        resp.raise_for_status()
        if not resp.content:
            return b"", "сервер вернул пустой ответ"
        return resp.content, None
    except Exception as e:
        logger.exception("Fish Speech synthesize error")
        return b"", f"synth_failed: {e}"


# ════════════════════════════════════════════════════════════════════
#  XTTS v2 (Coqui) — клонирование голоса из 10-сек референса (GPU/CPU)
# ════════════════════════════════════════════════════════════════════
_xtts_model = None


def _xtts_device() -> str:
    explicit = os.getenv("XTTS_DEVICE", "").strip().lower()
    if explicit:
        return explicit
    try:
        import torch  # type: ignore
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _get_xtts():
    """Ленивая загрузка XTTS v2. Voice cloning — без расшифровки, только аудио."""
    global _xtts_model, _xtts_error
    if _xtts_model is not None:
        return _xtts_model
    if _xtts_error is not None:
        return None

    ref_audio = _resolve_voice_ref(os.getenv("XTTS_REF_AUDIO", ""))
    if not ref_audio or not Path(ref_audio).exists():
        _xtts_error = f"XTTS_REF_AUDIO не найден ({ref_audio or 'не задан'})"
        logger.error(f"TTS XTTS: {_xtts_error}")
        return None

    # CPML: первый запуск требует согласия — обходим через env.
    os.environ.setdefault("COQUI_TOS_AGREED", "1")

    try:
        from TTS.api import TTS  # type: ignore
    except Exception as e:
        _xtts_error = f"coqui-tts не установлен ({e})"
        logger.warning(f"TTS XTTS недоступен: {_xtts_error}. Установите: pip install coqui-tts")
        return None

    device = _xtts_device()
    model_name = os.getenv("XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
    try:
        logger.info(f"TTS: загружаю XTTS v2 {model_name} ({device})…")
        model = TTS(model_name, progress_bar=False)
        model.to(device)
        _xtts_model = model
        logger.success(f"TTS готов (XTTS v2 — клонированный голос, {device})")
        return _xtts_model
    except Exception as e:
        _xtts_error = f"не удалось загрузить XTTS v2 ({e})"
        logger.exception(f"TTS: {_xtts_error}")
        _free_cuda()
        return None


def _xtts_synthesize(text: str) -> tuple[bytes, str | None]:
    import numpy as np  # идёт с torch
    model = _get_xtts()
    if model is None:
        return b"", _xtts_error or "xtts_unavailable"

    ref_audio = _resolve_voice_ref(os.getenv("XTTS_REF_AUDIO", ""))
    language = os.getenv("XTTS_LANGUAGE", "ru").strip() or "ru"

    try:
        wav = model.tts(text=text, speaker_wav=ref_audio, language=language)
        wav = np.asarray(wav, dtype="float32")
        pcm16 = (np.clip(wav, -1.0, 1.0) * 32767).astype("<i2")
        try:
            sr = int(model.synthesizer.output_sample_rate)
        except Exception:
            sr = 24000
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm16.tobytes())
        return buf.getvalue(), None
    except Exception as e:
        logger.exception("XTTS synthesize error")
        return b"", f"synth_failed: {e}"


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
#  Qwen3-TTS CustomVoice — готовые тембры (без образца), GPU
# ════════════════════════════════════════════════════════════════════
#  Открытые веса Qwen3-TTS-12Hz-1.7B-CustomVoice: топовое качество русского,
#  десятки тембров «из коробки». Не требует образца голоса — выбираем тембр
#  (QWEN_SPEAKER) и язык (QWEN_LANGUAGE). На RTX 3060 12 ГБ 1.7B помещается.
_qwen_cv_model = None
_qwen_cv_error: str | None = None
# Лок сериализует загрузку модели: прогрев и первый запрос браузера иначе
# грузят 1.7B одновременно → две копии в VRAM → CUDA out of memory.
_qwen_cv_lock = threading.Lock()

# Женские тембры из набора Qwen3-TTS (язык тембра ≠ язык речи — модель
# говорит по-русски любым тембром). Мужские: Uncle_Fu, Dylan, Eric, Ryan, Aiden.
_QWEN_CV_FEMALE = ("Vivian", "Serena", "Ono_Anna", "Sohee")


def _get_qwen_cv():
    """Ленивая загрузка Qwen3-TTS CustomVoice (готовые тембры, без образца)."""
    global _qwen_cv_model, _qwen_cv_error
    if _qwen_cv_model is not None:
        return _qwen_cv_model
    if _qwen_cv_error is not None:
        return None

    # Сериализуем загрузку: пока один поток грузит модель, остальные ждут и
    # затем переиспользуют её (без второй копии в VRAM → без OOM).
    with _qwen_cv_lock:
        if _qwen_cv_model is not None:
            return _qwen_cv_model
        if _qwen_cv_error is not None:
            return None
        return _load_qwen_cv()


def _load_qwen_cv():
    """Собственно загрузка (вызывается под _qwen_cv_lock)."""
    global _qwen_cv_model, _qwen_cv_error
    try:
        import torch  # type: ignore
        from qwen_tts import Qwen3TTSModel  # type: ignore
    except Exception as e:
        _qwen_cv_error = f"qwen-tts/torch не установлены ({e})"
        logger.warning(f"TTS Qwen недоступен: {_qwen_cv_error}. Установите: pip install qwen-tts")
        return None

    model_name = os.getenv("QWEN_CV_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
    # CustomVoice-метод есть только у моделей CustomVoice; модель -Base (для
    # клонирования) его не поддерживает. Защита от залежавшегося QWEN_TTS_MODEL.
    if "customvoice" not in model_name.lower():
        logger.warning(f"Qwen CustomVoice: модель '{model_name}' не CustomVoice — "
                       "переключаюсь на Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
        model_name = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    device = os.getenv("QWEN_DEVICE", "cuda:0")
    attn = os.getenv("QWEN_ATTN", "sdpa")  # sdpa не требует сборки flash-attn
    dtype = torch.bfloat16 if "cuda" in device else torch.float32

    # Цепочка попыток: выбранный attn → eager (минимум памяти) при сбое/OOM.
    attempts = [attn]
    if attn != "eager":
        attempts.append("eager")

    last_exc: Exception | None = None
    for attempt_attn in attempts:
        try:
            logger.info(f"TTS: загружаю Qwen3-TTS CustomVoice {model_name} "
                        f"({device}, attn={attempt_attn})…")
            _qwen_cv_model = Qwen3TTSModel.from_pretrained(
                model_name, device_map=device, dtype=dtype,
                attn_implementation=attempt_attn,
            )
            # Ускорение матмулов на Ampere (RTX 3060): TF32 + автоподбор cuDNN.
            # Заметно быстрее без потери качества на слух.
            try:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                torch.backends.cudnn.benchmark = True
            except Exception:
                pass
            break
        except Exception as e:
            last_exc = e
            logger.warning(f"Qwen CustomVoice: загрузка с attn={attempt_attn} не удалась ({e})")
            _free_cuda()

    if _qwen_cv_model is None:
        _qwen_cv_error = f"не удалось загрузить Qwen3-TTS CustomVoice ({last_exc})"
        logger.error(f"TTS: {_qwen_cv_error}")
        return None

    logger.success(f"TTS готов (Qwen3-TTS CustomVoice — тембр "
                   f"{os.getenv('QWEN_SPEAKER', 'Vivian')})")
    return _qwen_cv_model


def _qwen_cv_synthesize(text: str) -> tuple[bytes, str | None]:
    model = _get_qwen_cv()
    if model is None:
        return b"", _qwen_cv_error or "qwen_unavailable"
    import numpy as np

    language = os.getenv("QWEN_LANGUAGE", "Russian").strip() or "Russian"
    speaker = os.getenv("QWEN_SPEAKER", "Vivian").strip() or "Vivian"
    try:
        wavs, sr = model.generate_custom_voice(
            text=text, language=language, speaker=speaker,
        )
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
        logger.exception("Qwen CustomVoice synthesize error")
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


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _silero_say(model, text, speaker, sample_rate, rate, put_accent=True, put_yo=True):
    """Один вызов Silero. При заданном SILERO_RATE — через SSML (мягче/медленнее
    для ASMR-подачи), с безопасным откатом на обычный синтез. put_accent=False,
    если ударения уже расставлены RUAccent."""
    if rate:
        ssml = f'<speak><prosody rate="{rate}">{_xml_escape(text)}</prosody></speak>'
        try:
            return model.apply_tts(
                ssml_text=ssml, speaker=speaker, sample_rate=sample_rate,
                put_accent=put_accent, put_yo=put_yo,
            )
        except Exception:
            pass  # SSML не поддержан — обычный путь ниже
    return model.apply_tts(
        text=text, speaker=speaker, sample_rate=sample_rate,
        put_accent=put_accent, put_yo=put_yo,
    )


def _silero_synthesize(text: str) -> tuple[bytes, str | None]:
    model = _get_silero()
    if model is None:
        return b"", _silero_error or "silero_unavailable"
    import numpy as np  # идёт вместе с torch

    speaker = os.getenv("SILERO_SPEAKER", "baya").strip() or "baya"
    sample_rate = int(os.getenv("SILERO_SAMPLE_RATE", "48000") or 48000)
    rate = os.getenv("SILERO_RATE", "").strip()  # напр. slow / x-slow / 90%

    # Точные ударения через RUAccent. Получилось — отдаём Silero готовый текст
    # с «+» перед ударными и «ё»; не получилось — встроенный акцентор Silero.
    from .accent import accentize
    accented = accentize(text)
    if accented:
        src_text, put_accent, put_yo = accented, False, False
    else:
        src_text, put_accent, put_yo = text, True, True

    try:
        chunks = []
        for piece in _split_for_silero(src_text):
            audio = _silero_say(model, piece, speaker, sample_rate, rate, put_accent, put_yo)
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
def engine_info() -> dict:
    """Диагностика: какой движок выбран, что загружено, какие ошибки."""
    return {
        "engine": _engine(),
        "loaded": {
            "fishaudio": _fish_error is None and _engine() == "fishaudio",
            "xtts": _xtts_model is not None,
            "qwen": _qwen_cv_model is not None,
            "qwen3vc": _qwen_model is not None,
            "silero": _silero_model is not None,
            "piper": _piper_voice is not None,
        },
        "errors": {
            "fishaudio": _fish_error,
            "xtts": _xtts_error,
            "qwen": _qwen_cv_error,
            "qwen3vc": _qwen_error,
            "silero": _silero_error,
            "piper": _piper_error,
        },
    }


def is_available() -> bool:
    """Доступен хоть какой-то движок? (нужно для /api/tts/status)."""
    eng = _engine()
    if eng == "fishaudio" and _fish_health():
        return True
    if eng == "xtts" and _get_xtts() is not None:
        return True
    if eng == "qwen" and _get_qwen_cv() is not None:
        return True
    if eng == "qwen3vc" and _get_qwen() is not None:
        return True
    if eng == "piper" and _get_piper() is not None:
        return True
    if eng == "silero" and _get_silero() is not None:
        return True
    # фолбэк: лишь бы какой-то голос был
    return _get_silero() is not None or _get_piper() is not None


# ── Кэш готовых WAV ────────────────────────────────────────────────
# Киоск повторяет одни и те же фразы (приветствие, прощание, «назовите имя…»).
# Кэшируем синтез по тексту — повтор отдаётся мгновенно, без работы GPU.
_WAV_CACHE: OrderedDict[str, bytes] = OrderedDict()
_WAV_CACHE_MAX = int(os.getenv("TTS_CACHE_SIZE", "256") or 256)
_wav_cache_lock = threading.Lock()


def _cache_key(text: str) -> str:
    # ключ учитывает движок и голос — при их смене кэш не пересекается
    return "|".join((
        _engine(),
        os.getenv("QWEN_SPEAKER", ""),
        os.getenv("SILERO_SPEAKER", ""),
        text,
    ))


def synthesize(text: str) -> tuple[bytes, str | None]:
    """Синтез речи с кэшем → (WAV-байты, ошибка). Повторные фразы — мгновенно."""
    if not text or not text.strip():
        return b"", "empty_text"
    key = _cache_key(text.strip())
    with _wav_cache_lock:
        hit = _WAV_CACHE.get(key)
        if hit is not None:
            _WAV_CACHE.move_to_end(key)  # LRU: освежаем
            return hit, None
    audio, err = _synthesize_impl(text)
    if not err and audio:
        with _wav_cache_lock:
            _WAV_CACHE[key] = audio
            _WAV_CACHE.move_to_end(key)
            while len(_WAV_CACHE) > _WAV_CACHE_MAX:
                _WAV_CACHE.popitem(last=False)  # выкидываем самый старый
    return audio, err


def warmup() -> None:
    """Прогрев: один реальный синтез, чтобы первый ответ пациенту не платил
    за автоподбор cuDNN/первую CUDA-аллокацию. Заодно кэширует приветствие."""
    try:
        synthesize("Здравствуйте! Меня зовут Оливия.")
        logger.success("TTS прогрет реальным синтезом (первый ответ будет быстрым)")
    except Exception:
        logger.exception("TTS warmup synth error")


def _synthesize_impl(text: str) -> tuple[bytes, str | None]:
    """Синтезирует речь → (WAV-байты, ошибка).

    Цепочка фолбэков: при сбое выбранного движка пробуем следующий,
    чтобы голос звучал даже если, например, клонирующий движок не
    влез в GPU.
    """
    if not text or not text.strip():
        return b"", "empty_text"
    # числа/деньги/время/сокращения → произносимые слова (для всех движков)
    from .text_norm import normalize_ru
    text = normalize_ru(text)
    eng = _engine()

    if eng == "fishaudio":
        audio, err = _fishaudio_synthesize(text)
        if not err:
            return audio, None
        logger.warning(f"TTS: Fish Speech упал ({err}), фолбэк → Silero")
        audio, err2 = _silero_synthesize(text)
        if not err2:
            return audio, None
        return _piper_synthesize(text)

    if eng == "xtts":
        audio, err = _xtts_synthesize(text)
        if not err:
            return audio, None
        logger.warning(f"TTS: XTTS упал ({err}), фолбэк → Silero")
        audio, err2 = _silero_synthesize(text)
        if not err2:
            return audio, None
        return _piper_synthesize(text)

    if eng == "qwen":
        audio, err = _qwen_cv_synthesize(text)
        if not err:
            return audio, None
        logger.warning(f"TTS: Qwen CustomVoice упал ({err}), фолбэк → Silero")
        audio, err2 = _silero_synthesize(text)
        if not err2:
            return audio, None
        return _piper_synthesize(text)

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
