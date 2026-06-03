"""
Text-to-Speech для русского языка
==================================
Silero TTS v4_ru + предварительная нормализация русского текста.

Ключевая идея: 90% «робота» в Silero — не из-за модели, а из-за того, что
ей подают сырой текст с цифрами/датами/ё-без-точек. Прогон через
`russian_normalizer.normalize()` убирает почти все артефакты.

Speakers v4_ru: aidar, baya, eugene, kseniya, xenia, random.
Рекомендация для администратора-женщины: `xenia` (мягкий приятный голос).

Поддерживает синхронизацию с UI: вызывает `ui.start_speaking()` / `stop_speaking()`,
а ещё может слать амплитудные кадры для пульсации «говорящего круга».
"""
from __future__ import annotations

import asyncio
import threading

import numpy as np
import sounddevice as sd
from loguru import logger

try:
    import torch
    HAVE_TORCH = True
except ImportError:  # pragma: no cover
    HAVE_TORCH = False

from .russian_normalizer import normalize


class TextToSpeech:
    """Silero TTS с нормализатором русского текста."""

    DEFAULT_SR = 48000

    def __init__(self, config: dict):
        if not HAVE_TORCH:
            raise RuntimeError("torch не установлен. pip install torch")

        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.sample_rate = int(config.get("sample_rate", self.DEFAULT_SR))
        self.speaker = config.get("speaker", "xenia")
        self.put_accent = bool(config.get("put_accent", True))
        self.put_yo = bool(config.get("put_yo", True))

        logger.info(f"Загрузка Silero TTS v4_ru, speaker={self.speaker}, device={self.device}")
        # v4 быстрее и натуральнее, чем v3
        self.model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-models",
            model="silero_tts",
            language="ru",
            speaker="v4_ru",
            trust_repo=True,
        )
        self.model.to(self.device)

        # Для синхронизации с UI «говорящий круг»
        self._stop_event = threading.Event()
        logger.success("TTS инициализирован")

    # ------------------------------------------------------------------
    async def speak(self, text: str, ui_display=None) -> None:
        """
        Озвучивает реплику. Перед синтезом — нормализация русского текста.
        Во время воспроизведения дёргает анимацию UI.
        """
        if not text or not text.strip():
            return

        normalized = normalize(text)
        if normalized != text:
            logger.debug(f"Normalized: '{text}' → '{normalized}'")

        logger.info(f"🔊 Произношу: {normalized}")
        try:
            audio = await asyncio.to_thread(self._synthesize, normalized)
        except Exception as e:
            logger.error(f"Ошибка синтеза: {e}. Пробую без ударений.")
            try:
                audio = await asyncio.to_thread(self._synthesize, normalized, fallback=True)
            except Exception as e2:
                logger.error(f"Повторная ошибка синтеза: {e2}")
                return

        if ui_display:
            ui_display.start_speaking_animation()

        try:
            await self._play(audio, ui_display=ui_display)
        finally:
            if ui_display:
                ui_display.stop_speaking_animation()

    # ------------------------------------------------------------------
    def _synthesize(self, text: str, fallback: bool = False) -> np.ndarray:
        kwargs = dict(
            text=text,
            speaker=self.speaker,
            sample_rate=self.sample_rate,
        )
        if not fallback:
            kwargs["put_accent"] = self.put_accent
            kwargs["put_yo"] = self.put_yo
        audio_t = self.model.apply_tts(**kwargs)
        return audio_t.cpu().numpy().astype(np.float32)

    # ------------------------------------------------------------------
    async def _play(self, audio: np.ndarray, ui_display=None) -> None:
        """
        Играет аудио блоками и одновременно шлёт амплитуду в UI,
        чтобы круг пульсировал в такт речи.
        """
        block = self.sample_rate // 20  # 50 мс
        self._stop_event.clear()
        loop = asyncio.get_event_loop()
        done = asyncio.Event()
        idx = {"i": 0}

        def cb(outdata, frames, time_info, status):
            i = idx["i"]
            end = i + frames
            chunk = audio[i:end]
            if chunk.shape[0] < frames:
                outdata[: chunk.shape[0], 0] = chunk
                outdata[chunk.shape[0]:, 0] = 0.0
                loop.call_soon_threadsafe(done.set)
                raise sd.CallbackStop
            else:
                outdata[:, 0] = chunk
                if ui_display is not None and hasattr(ui_display, "set_amplitude"):
                    amp = float(np.abs(chunk).mean())
                    loop.call_soon_threadsafe(ui_display.set_amplitude, amp)
            idx["i"] = end

        stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            blocksize=block,
            dtype="float32",
            callback=cb,
        )
        with stream:
            await done.wait()

    def stop(self) -> None:
        """Прерывает текущее воспроизведение (мягко)."""
        self._stop_event.set()
        sd.stop()
