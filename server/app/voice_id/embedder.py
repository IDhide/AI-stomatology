"""
Голосовой «отпечаток» через Resemblyzer.

Даёт эмбеддинг голоса (нормированный вектор) по накопленному за разговор
куску речи пациента. Вектор потом уходит в VoiceMemoryStore.match() для
поиска ближайшего совпадения.

ВАЖНО (см. план/README): это не биометрия военного класса. Короткие
реплики, шум регистратуры и изменчивость голоса дают заметную погрешность —
поэтому эмбеддинг строится не по одному слову, а по накопленному куску речи
(см. VOICE_MIN_SAMPLE_SECONDS в config.py), и решение об «узнавании»
принимается с мягким переспрашиванием, а не как факт (см. промпт).

Тяжёлая зависимость (resemblyzer → torch, ~200-300 МБ) грузится лениво:
если resemblyzer не установлен — модуль импортируется, но embedder
выключен, и система работает как раньше, без персонализации по голосу.
"""
from __future__ import annotations

import numpy as np
from loguru import logger

try:
    from resemblyzer import VoiceEncoder, preprocess_wav

    HAVE_RESEMBLYZER = True
except ImportError:  # pragma: no cover
    HAVE_RESEMBLYZER = False
    VoiceEncoder = None  # type: ignore
    preprocess_wav = None  # type: ignore

SAMPLE_RATE = 16000  # тот же формат, что везде в пайплайне (PCM16 mono 16k)

# Минимум РЕАЛЬНОЙ речи после VAD-чистки. Короче — отпечаток строится
# почти из шума и потом не совпадает даже с тем же человеком (разбор:
# «мусорный» отпечаток от 10.08 не совпадал с живым голосом на 0.6+,
# тогда как дубли одного голоса дают 0.14–0.18). Лучше пропустить попытку,
# чем записать мусор в базу.
MIN_VOICED_SECONDS = 2.0


def pcm16_to_float(audio: bytes) -> np.ndarray:
    """PCM16LE bytes → float32 в диапазоне [-1, 1], как ожидает Resemblyzer."""
    ints = np.frombuffer(audio, dtype=np.int16)
    return (ints.astype(np.float32) / 32768.0).copy()


class VoiceEmbedder:
    def __init__(self):
        self.encoder = None
        if not HAVE_RESEMBLYZER:
            logger.warning("resemblyzer не установлен — узнавание по голосу выключено")
            return
        try:
            self.encoder = VoiceEncoder()
            logger.success("VoiceEmbedder готов (Resemblyzer)")
        except Exception as e:
            logger.error(f"VoiceEncoder init: {e}")
            self.encoder = None

    @property
    def enabled(self) -> bool:
        return self.encoder is not None

    def embed(self, audio: bytes) -> list[float] | None:
        """
        Возвращает нормированный эмбеддинг накопленной речи пациента
        (bytes — PCM16 mono 16kHz) или None, если распознать не вышло
        (тишина/мусор после VAD-обрезки, модель не загружена и т.п.).
        """
        if not self.encoder:
            return None
        try:
            wav = pcm16_to_float(audio)
            processed = preprocess_wav(wav, source_sr=SAMPLE_RATE)
            voiced_seconds = processed.size / SAMPLE_RATE
            if voiced_seconds < MIN_VOICED_SECONDS:
                logger.info(
                    f"VoiceEmbedder: речи {voiced_seconds:.1f}с < {MIN_VOICED_SECONDS}с — "
                    "отпечаток не строим (иначе в базу уйдёт шум)"
                )
                return None
            embedding = self.encoder.embed_utterance(processed)
            return embedding.astype(np.float32).tolist()
        except Exception as e:
            logger.error(f"VoiceEmbedder.embed: {e}")
            return None
