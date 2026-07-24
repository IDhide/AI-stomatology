"""
Стриминговый оркестратор одного разговора.

Главная идея (то, чего не было в старой версии): ЭТАПЫ ПЕРЕКРЫВАЮТСЯ.
Как только LLM выдал первое законченное предложение — мы сразу шлём его
в TTS и начинаем проигрывать, пока LLM ещё думает над остатком реплики.

    STT ─► LLM(поток токенов) ─► нарезка на предложения ─► TTS(поток) ─► колонка
                                        ▲ первый звук ~1–1.5 с

Один экземпляр = один диалог с одним пациентом (хранит историю).
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable

from loguru import logger

from .persona import Persona
from .providers.base import LLMProvider, STTProvider, TTSProvider

# Конец предложения: точка/!/?/… + пробел. Нарезаем, чтобы отдавать в TTS
# по фразам, а не по словам (иначе просодия рвётся).
_SENTENCE_END = re.compile(r"([.!?…]+)(\s+|$)")

# Пациент прощается — чтобы завершить диалог локально, даже если LLM лежит
_FAREWELL_RE = re.compile(
    r"\b(до свидания|до встречи|всего доброго|всего хорошего|пока|прощайте)\b",
    re.IGNORECASE,
)

AudioSink = Callable[[bytes], Awaitable[None]]


class Conversation:
    def __init__(
        self,
        stt: STTProvider,
        llm: LLMProvider,
        tts: TTSProvider,
        persona: Persona,
        *,
        max_history_pairs: int = 8,
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.persona = persona
        self.max_history_pairs = max_history_pairs
        self.history: list[dict[str, str]] = []
        self._greeted = False
        self._extra_context = ""
        self.ended = False  # LLM поставил метку [КОНЕЦ] — диалог завершён

    def set_context(self, text: str) -> None:
        """Дополнительный блок для system-промпта (например, записи DIKIDI)."""
        self._extra_context = text.strip()

    # ── публичные точки входа ────────────────────────────────────────
    async def greet(self, sink: AudioSink, *, name: str | None = None) -> str:
        """Первая инициатива системы — приветствие (из ТЗ)."""
        self.ended = False
        text = self.persona.greeting(returning=self._greeted, name=name)
        self._greeted = True
        await self._speak(text, sink)
        self.history.append({"role": "assistant", "content": text})
        return text

    async def farewell(self, sink: AudioSink) -> str:
        """
        Прощание при уходе пациента. Если был разговор — прощание генерирует
        LLM с учётом контекста (персональное, не однотипное); иначе шаблон.
        """
        text = ""
        if self.history:
            try:
                messages = [
                    {"role": "system", "content": self.persona.system},
                    *self.history,
                    {"role": "user", "content":
                        "[Пациент отходит от стойки. Попрощайся ОДНОЙ короткой "
                        "тёплой фразой по итогам разговора, без вопросов.]"},
                ]
                parts = [p async for p in self.llm.stream(messages)]
                text = self._strip_end_marker("".join(parts))[0].strip()
            except Exception:
                logger.warning("LLM недоступен для прощания — шаблон")
        if not text:
            text = self.persona.farewell()
        await self._speak(text, sink)
        return text

    # метка, которой LLM сигналит «диалог завершён» (не произносится)
    _END_MARKER = re.compile(r"\s*\[\s*КОНЕЦ\s*\]\s*", re.IGNORECASE)

    def _strip_end_marker(self, text: str) -> tuple[str, bool]:
        if self._END_MARKER.search(text):
            return self._END_MARKER.sub(" ", text).strip(), True
        return text, False

    async def handle_utterance(
        self,
        audio: bytes,
        sink: AudioSink,
        *,
        on_transcript: Callable[[str], Awaitable[None]] | None = None,
        on_reply_text: Callable[[str], Awaitable[None]] | None = None,
    ) -> str | None:
        """
        Полный цикл на одну реплику пациента:
        аудио → текст → LLM(поток) → TTS(поток) → sink.
        Возвращает распознанный текст пациента (или None, если тишина).
        """
        user_text = await self.stt.transcribe(audio)
        if not user_text:
            logger.debug("STT: пусто, пропускаю")
            return None

        logger.info(f"👤 {user_text}")
        if on_transcript:
            await on_transcript(user_text)

        self.history.append({"role": "user", "content": user_text})

        reply_parts: list[str] = []
        try:
            async for sentence in self._llm_sentences():
                sentence, is_end = self._strip_end_marker(sentence)
                if is_end:
                    self.ended = True
                if not sentence:
                    continue
                reply_parts.append(sentence)
                if on_reply_text:
                    await on_reply_text(sentence)
                await self._speak(sentence, sink)
        except Exception as e:
            # LLM упал даже после ретраев — Оливия не молчит.
            logger.error(f"LLM недоступен ({type(e).__name__}) — запасное поведение")
            if _FAREWELL_RE.search(user_text):
                # пациент прощается — прощаемся шаблоном и завершаем диалог,
                # чтобы киоск не завис в разговоре при лежащем API
                fallback = self.persona.farewell()
                self.ended = True
            else:
                fallback = (self.persona.prompts.get("fallback_error")
                            or "Прошу прощения, у меня небольшая заминка со "
                               "связью. Повторите, пожалуйста, ещё раз.").strip()
            if on_reply_text:
                await on_reply_text(fallback)
            await self._speak(fallback, sink)
            reply_parts = [fallback]

        reply = " ".join(reply_parts).strip()
        if reply:
            self.history.append({"role": "assistant", "content": reply})
            self._trim()
        logger.info(f"🤖 {reply}")
        return user_text

    # ── внутреннее ───────────────────────────────────────────────────
    async def _llm_sentences(self) -> AsyncIterator[str]:
        """
        Стримит токены LLM и отдаёт их наружу законченными предложениями,
        чтобы TTS звучал естественно и начинался как можно раньше.
        """
        system = self.persona.system
        if self._extra_context:
            system = f"{system}\n\n{self._extra_context}"
        messages = [{"role": "system", "content": system}, *self.history]
        buffer = ""
        async for piece in self.llm.stream(messages):
            buffer += piece
            while True:
                m = _SENTENCE_END.search(buffer)
                if not m:
                    break
                cut = m.end()
                sentence = buffer[:cut].strip()
                buffer = buffer[cut:]
                if sentence:
                    yield sentence
        tail = buffer.strip()
        if tail:
            yield tail

    async def _speak(self, text: str, sink: AudioSink) -> None:
        # Ошибка синтеза не должна убивать разговор: текст уже ушёл на экран
        # субтитрами, история сохранится — просто без звука этой фразы.
        try:
            async for chunk in self.tts.stream(text):
                await sink(chunk)
        except Exception as e:
            logger.error(f"TTS не смог озвучить фразу: {e}")

    def _trim(self) -> None:
        # оставляем system за скобками (он не в history); режем историю
        max_msgs = self.max_history_pairs * 2
        if len(self.history) > max_msgs:
            self.history = self.history[-max_msgs:]
