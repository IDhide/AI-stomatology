"""
accent.py
=========
Простановка ударений в русском тексте через RUAccent — для естественной,
безошибочной речи Silero.

RUAccent помечает ударную гласную знаком «+» ПЕРЕД ней (например «сл+ово»,
«удар+ением») и расставляет «ё». Это ровно тот формат, который принимает
Silero, поэтому текст с ударениями отдаётся в apply_tts с put_accent=False
(ударения уже стоят), а встроенный акцентор Silero не используется.

Если RUAccent недоступен или упал — функция возвращает None, и вызывающий код
откатывается на встроенный put_accent Silero (тоже рабочий, чуть менее точный).

Переменные окружения:
  RUACCENT_ENABLED — 1|0 (по умолчанию 1)
  RUACCENT_MODEL   — размер модели омографов: turbo3.1 | turbo | tiny | big
                     (по умолчанию turbo3.1 — хорошее качество, умеренный вес)
  RUACCENT_TINY    — 1|0 облегчённый режим без тяжёлой модели (по умолчанию 0)
"""
from __future__ import annotations

import os

from loguru import logger

_accentizer = None
_accent_error: str | None = None


def _enabled() -> bool:
    return os.getenv("RUACCENT_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def _get_accentizer():
    """Ленивая загрузка RUAccent (один раз на процесс)."""
    global _accentizer, _accent_error
    if _accentizer is not None:
        return _accentizer
    if _accent_error is not None:
        return None
    if not _enabled():
        _accent_error = "отключён (RUACCENT_ENABLED=0)"
        return None

    try:
        from ruaccent import RUAccent  # type: ignore
    except Exception as e:
        _accent_error = f"ruaccent не установлен ({e})"
        logger.warning(f"RUAccent недоступен: {_accent_error}. Ударения — встроенные Silero.")
        return None

    try:
        acc = RUAccent()
        size = os.getenv("RUACCENT_MODEL", "turbo3.1").strip() or "turbo3.1"
        tiny = os.getenv("RUACCENT_TINY", "0").strip().lower() in ("1", "true", "yes", "on")
        logger.info(f"RUAccent: загружаю модель ударений ({size}, tiny={tiny})…")
        acc.load(omograph_model_size=size, use_dictionary=True, tiny_mode=tiny)
        _accentizer = acc
        logger.success("RUAccent готов (точная простановка ударений)")
        return _accentizer
    except Exception as e:
        _accent_error = f"не удалось загрузить RUAccent ({e})"
        logger.warning(f"RUAccent: {_accent_error}. Ударения — встроенные Silero.")
        return None


def accentize(text: str) -> str | None:
    """Текст с ударениями (+перед гласной) и «ё», либо None при недоступности."""
    if not text or not text.strip():
        return None
    acc = _get_accentizer()
    if acc is None:
        return None
    try:
        return acc.process_all(text)
    except Exception as e:
        logger.warning(f"RUAccent: ошибка простановки ударений: {e}")
        return None
