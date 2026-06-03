"""
Speech-to-Text для русского языка
==================================
faster-whisper large-v3 + Silero-VAD + стоматологический лексикон.

Почему так:
- faster-whisper в 4× быстрее обычного whisper при той же точности.
- Silero-VAD режет тишину/«эээ», что критично: иначе Whisper галлюцинирует.
- initial_prompt со стоматологическими терминами поднимает recall на терминах.
- post_correct() правит частые ошибки распознавания.

Для RTX 3060 12GB рекомендуется:
    model_size = "large-v3"
    compute_type = "int8_float16"
    device = "cuda"
    beam_size = 5

Деградация: при OOM/CPU автоматически падает на "medium" → "small".
"""
from __future__ import annotations

import asyncio
from typing import Optional

import numpy as np
import sounddevice as sd
from loguru import logger

try:
    from faster_whisper import WhisperModel
    HAVE_FASTER_WHISPER = True
except ImportError:  # pragma: no cover
    HAVE_FASTER_WHISPER = False
    WhisperModel = None  # type: ignore

try:
    import torch
    HAVE_TORCH = True
except ImportError:  # pragma: no cover
    HAVE_TORCH = False

from .dental_lexicon import build_initial_prompt, post_correct


class SpeechToText:
    """Production STT для русской речи в стоматологии."""

    SAMPLE_RATE = 16000  # Whisper и Silero-VAD оба ждут 16 kHz
    CHANNELS = 1

    def __init__(self, config: dict):
        if not HAVE_FASTER_WHISPER:
            raise RuntimeError(
                "faster-whisper не установлен. pip install faster-whisper"
            )

        self.config = config
        self.language = config.get("language", "ru")
        self.beam_size = config.get("beam_size", 5)
        self.no_speech_threshold = config.get("no_speech_threshold", 0.6)

        device = config.get("device", "cuda")
        compute_type = config.get("compute_type", "int8_float16" if device == "cuda" else "int8")
        model_size = config.get("model", "large-v3")

        logger.info(f"Загрузка faster-whisper: model={model_size}, device={device}, ct={compute_type}")
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as e:
            logger.warning(f"Не удалось загрузить {model_size} на {device}: {e}. Падаю на medium/cpu.")
            self.model = WhisperModel("medium", device="cpu", compute_type="int8")

        # Silero-VAD — для онлайн-детекции конца фразы
        self.vad_model = None
        self.vad_utils = None
        if HAVE_TORCH and config.get("use_vad", True):
            try:
                self.vad_model, self.vad_utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    trust_repo=True,
                )
                logger.success("Silero-VAD загружен")
            except Exception as e:
                logger.warning(f"Silero-VAD не загрузился, fallback на энергетический VAD: {e}")

        # Подготовим initial_prompt с именами врачей из конфига
        self.initial_prompt = build_initial_prompt(
            doctor_names=config.get("doctor_names", [])
        )

        self.silence_ms = config.get("silence_ms", 700)
        self.max_record_sec = config.get("max_record_sec", 25)
        self.min_record_sec = config.get("min_record_sec", 0.4)

        logger.success("STT инициализирован")

    # ------------------------------------------------------------------
    async def listen(self, timeout: int = 25) -> str:
        """Записывает реплику пациента и возвращает распознанный текст."""
        logger.info("🎤 Слушаю...")
        audio = await self._record_until_silence(timeout)
        if audio is None or audio.size < self.SAMPLE_RATE * self.min_record_sec:
            logger.info("Слишком короткая запись — пропускаю")
            return ""

        text = await asyncio.to_thread(self._transcribe, audio)
        if not text:
            return ""

        corrected = post_correct(text)
        if corrected != text:
            logger.info(f"Post-correction: '{text}' → '{corrected}'")
        logger.success(f"📝 Распознано: {corrected}")
        return corrected

    # ------------------------------------------------------------------
    def _transcribe(self, audio: np.ndarray) -> str:
        segments, info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            initial_prompt=self.initial_prompt,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": self.silence_ms},
            condition_on_previous_text=False,   # критично: иначе модель «занашивает»
            no_speech_threshold=self.no_speech_threshold,
            temperature=0.0,
            word_timestamps=False,
        )
        parts = [seg.text for seg in segments]
        text = "".join(parts).strip()
        if info and info.language_probability < 0.5:
            logger.warning(f"Низкая уверенность в языке: {info.language_probability:.2f}")
        return text

    # ------------------------------------------------------------------
    async def _record_until_silence(self, timeout: int) -> Optional[np.ndarray]:
        """Запись с детекцией конца фразы по Silero-VAD (или энергии — fallback)."""
        chunks: list[np.ndarray] = []
        chunk_size = 512  # 32 ms @ 16 kHz — оптимум для Silero-VAD
        silence_chunks_needed = max(1, int(self.silence_ms / 32))
        silent_in_a_row = 0
        speech_started = False

        q: asyncio.Queue[np.ndarray] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def cb(indata, frames, time_info, status):
            if status:
                logger.debug(f"sd status: {status}")
            loop.call_soon_threadsafe(q.put_nowait, indata.copy())

        stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            blocksize=chunk_size,
            dtype="float32",
            callback=cb,
        )

        with stream:
            start = loop.time()
            while True:
                if loop.time() - start > timeout:
                    logger.info("Таймаут записи")
                    break
                try:
                    chunk = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                chunks.append(chunk.flatten())
                is_speech = self._is_speech(chunk.flatten())

                if is_speech:
                    speech_started = True
                    silent_in_a_row = 0
                elif speech_started:
                    silent_in_a_row += 1
                    if silent_in_a_row >= silence_chunks_needed:
                        logger.debug("Конец фразы (VAD)")
                        break

                if (loop.time() - start) > self.max_record_sec:
                    logger.debug("Достигнут лимит длительности")
                    break

        if not chunks:
            return None
        return np.concatenate(chunks).astype(np.float32)

    # ------------------------------------------------------------------
    def _is_speech(self, chunk: np.ndarray) -> bool:
        """Silero-VAD если есть, иначе энергетический детектор."""
        if self.vad_model is not None and HAVE_TORCH:
            tensor = torch.from_numpy(chunk)
            prob = self.vad_model(tensor, self.SAMPLE_RATE).item()
            return prob > 0.5
        # fallback: RMS
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        return rms > 0.01
