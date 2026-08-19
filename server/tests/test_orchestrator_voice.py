"""
tests/test_orchestrator_voice.py
Персонализация диалога при распознавании голоса.
"""
import pytest

from server.app.orchestrator import Conversation
from server.app.voice_id.store import VoiceMatch


class _FakePersona:
    prompts: dict = {}
    system: str = "ты тестовая персона"

    def greeting(self, *, returning: bool = False, name: str | None = None) -> str:
        return "Здравствуйте!"

    def farewell(self) -> str:
        return "До свидания!"


class _FakeTTS:
    def __init__(self):
        self.spoken: list[str] = []

    async def stream(self, text: str):
        self.spoken.append(text)
        if False:
            yield b""


class _FakeSTT:
    async def transcribe(self, audio: bytes) -> str | None:
        return "привет"


class _FakeLLM:
    def __init__(self, *sentences: str):
        self.sentences = list(sentences)

    async def stream(self, messages, *, tools=None):
        for s in self.sentences:
            yield s + " "


def _conv(llm=None) -> Conversation:
    return Conversation(stt=_FakeSTT(), llm=llm, tts=_FakeTTS(), persona=_FakePersona())


@pytest.mark.asyncio
async def test_high_confidence_voice_match_prepends_greeting():
    conv = _conv(llm=_FakeLLM("Чем могу помочь?"))
    conv.set_voice_match(VoiceMatch(
        patient_id=1,
        name="Анна",
        phone="+7 921 555-12-34",
        distance=0.15,  # similarity 85%
        is_new=False,
        confidence="high",
    ))

    spoken = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert len(spoken) == 1
    assert spoken[0] == "Приятно вас снова видеть, Анна! чем могу помочь?"


@pytest.mark.asyncio
async def test_voice_greeting_not_repeated_in_subsequent_replies():
    conv = _conv(llm=_FakeLLM("Чем могу помочь?", "Запишем вас на завтра."))
    conv.set_voice_match(VoiceMatch(
        patient_id=1,
        name="Анна",
        phone=None,
        distance=0.10,
        is_new=False,
        confidence="high",
    ))

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    # первый ответ
    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)
    assert "Приятно вас снова видеть" in spoken[0]

    # второй ответ — приветствие не повторяется
    spoken.clear()
    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)
    assert "Приятно вас снова видеть" not in spoken[0]


@pytest.mark.asyncio
async def test_low_confidence_voice_match_does_not_force_greeting():
    conv = _conv(llm=_FakeLLM("Чем могу помочь?"))
    conv.set_voice_match(VoiceMatch(
        patient_id=1,
        name="Анна",
        phone=None,
        distance=0.20,  # similarity 80%
        is_new=False,
        confidence="low",
    ))

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert "Приятно вас снова видеть" not in spoken[0]
    assert spoken[0] == "Чем могу помочь?"


@pytest.mark.asyncio
async def test_voice_match_new_patient_no_greeting():
    conv = _conv(llm=_FakeLLM("Чем могу помочь?"))
    conv.set_voice_match(VoiceMatch(
        patient_id=None,
        name=None,
        phone=None,
        distance=2.0,
        is_new=True,
    ))

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert "Приятно вас снова видеть" not in spoken[0]


@pytest.mark.asyncio
async def test_voice_greeting_not_prepended_mid_dialog():
    """Матч пришёл посреди разговора — механическое приветствие не вклеиваем,
    имя подаёт промпт через контекст (13.08: «снова видеть» на 10-й реплике)."""
    conv = _conv(llm=_FakeLLM("Запишем вас на завтра."))
    # диалог уже идёт: приветствие + два ответа ассистента в истории
    conv.history.append({"role": "assistant", "content": "Здравствуйте!"})
    conv.history.append({"role": "user", "content": "Хочу на чистку"})
    conv.history.append({"role": "assistant", "content": "Хорошо, когда удобно?"})
    conv.history.append({"role": "user", "content": "Завтра вечером"})
    conv.set_voice_match(VoiceMatch(
        patient_id=1,
        name="Илья",
        phone=None,
        distance=0.10,
        is_new=False,
        confidence="high",
    ))

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert spoken[0] == "Запишем вас на завтра."


@pytest.mark.asyncio
async def test_voice_greeting_no_duplicate_punctuation_variant():
    """LLM сама начала с приветствия, но с «.» вместо «!» — не дублируем."""
    conv = _conv(llm=_FakeLLM("Приятно вас снова видеть, Анна. Чем могу помочь?"))
    conv.set_voice_match(VoiceMatch(
        patient_id=1,
        name="Анна",
        phone=None,
        distance=0.10,
        is_new=False,
        confidence="high",
    ))

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert spoken[0].lower().count("приятно вас снова видеть") == 1


@pytest.mark.asyncio
async def test_repeat_greeting_stripped_in_first_reply():
    """19.08: приветствие уже прозвучало шаблоном при появлении пациента,
    человек ответил «здравствуйте», а LLM поздоровалась заново
    («Здравствуйте. Меня зовут Оливия. Чем могу помочь?») — двойное
    приветствие срезается детерминированно, остаётся только суть."""
    conv = _conv(llm=_FakeLLM("Здравствуйте. Меня зовут Оливия. Чем могу помочь?"))
    conv._greeted = True
    conv.history.append({"role": "assistant", "content": "Здравствуйте! Я Оливия."})

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert spoken == ["Чем могу помочь?"]


@pytest.mark.asyncio
async def test_greeting_kept_when_no_presence_greeting():
    """Presence-приветствия не было (пациент заговорил первым) — приветствие
    LLM НЕ срезаем, это единственное."""
    conv = _conv(llm=_FakeLLM("Здравствуйте! Чем могу помочь?"))

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert spoken == ["Здравствуйте!", "Чем могу помочь?"]


@pytest.mark.asyncio
async def test_name_answer_not_stripped_mid_dialog():
    """Посреди диалога «Меня зовут Оливия» — легитимный ответ на вопрос
    «как вас зовут», срезать нельзя."""
    conv = _conv(llm=_FakeLLM("Меня зовут Оливия."))
    conv._greeted = True
    conv.history.append({"role": "assistant", "content": "Здравствуйте!"})
    conv.history.append({"role": "user", "content": "Сколько стоит чистка?"})
    conv.history.append({"role": "assistant", "content": "Пять тысяч."})
    conv.history.append({"role": "user", "content": "А как вас зовут?"})

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert spoken == ["Меня зовут Оливия."]


@pytest.mark.asyncio
async def test_strip_then_voice_greeting_prepended():
    """Пациент узнан по голосу, LLM при этом снова поздоровалась: повторное
    «здравствуйте» срезаем, персональное приветствие вклеиваем."""
    conv = _conv(llm=_FakeLLM("Здравствуйте! Чем могу помочь?"))
    conv._greeted = True
    conv.history.append({"role": "assistant", "content": "Здравствуйте! Я Оливия."})
    conv.set_voice_match(VoiceMatch(
        patient_id=1, name="Илья", phone=None,
        distance=0.10, is_new=False, confidence="high",
    ))

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert spoken == ["Приятно вас снова видеть, Илья! чем могу помочь?"]


@pytest.mark.asyncio
async def test_llm_greeting_stripped_mid_dialog():
    """LLM нарушила промпт и сама поздоровалась посреди диалога —
    фраза срезается детерминированно, имя остаётся только из контекста."""
    conv = _conv(llm=_FakeLLM("Приятно вас снова видеть, Илья. На завтра есть окна в семь."))
    conv.history.append({"role": "assistant", "content": "Здравствуйте!"})
    conv.history.append({"role": "user", "content": "Хочу на чистку"})
    conv.history.append({"role": "assistant", "content": "Когда удобно?"})
    conv.set_voice_match(VoiceMatch(
        patient_id=1, name="Илья", phone=None,
        distance=0.10, is_new=False, confidence="high",
    ))

    spoken: list[str] = []
    async def sink(chunk: bytes) -> None:
        pass
    async def _transcript(t: str) -> None:
        pass
    async def _reply(t: str) -> None:
        spoken.append(t)

    await conv.handle_utterance(b"\x00\x00", sink, on_transcript=_transcript, on_reply_text=_reply)

    assert "снова видеть" not in spoken[0].lower()
    assert spoken[0].startswith("На завтра есть окна")
