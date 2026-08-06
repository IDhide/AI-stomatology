"""
tests/test_orchestrator_booking.py
Парсинг служебных меток [ЗАЯВКА: ...] и [КОНЕЦ] в потоке ответа LLM.
"""
import pytest

from server.app.orchestrator import Conversation


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
        if False:  # делаем генератор без реального аудио
            yield b""


class _FakeLLMWithBookingMarker:
    """Имитирует LLM, который (по ошибке или нет) повторяет метку заявки
    даже в реплике-прощании — именно этот случай уронил бы её в TTS."""

    REPLY = (
        "Хорошего дня! "
        "[ЗАЯВКА: Имя=Мария; Телефон=89215551234; Время=после 18 вечера]"
    )

    async def stream(self, messages, *, tools=None):
        for word in self.REPLY.split():
            yield word + " "


def _conv(llm=None) -> Conversation:
    # Методы под тестом не трогают stt — реальный провайдер не нужен.
    return Conversation(stt=None, llm=llm, tts=_FakeTTS(), persona=_FakePersona())


def test_extract_booking_parses_full_marker_and_strips_it():
    conv = _conv()
    text = (
        "Хорошо, записываю вас. "
        "[ЗАЯВКА: Имя=Мария; Телефон=79215551234; Время=после 18 вечера; Что=чистка зубов]"
    )
    cleaned = conv._extract_booking(text)

    assert "[ЗАЯВКА" not in cleaned
    assert "Хорошо, записываю вас." in cleaned

    booking = conv.take_booking()
    assert booking is not None
    assert booking.name == "Мария"
    assert booking.phone_raw == "79215551234"
    assert booking.phone == "+7 921 555-12-34"
    assert booking.phone_valid is True
    assert booking.preferred_time == "после 18 вечера"
    assert booking.note == "чистка зубов"


def test_extract_booking_without_optional_note_field():
    conv = _conv()
    text = "[ЗАЯВКА: Имя=Иван; Телефон=89215551234; Время=утром]"
    conv._extract_booking(text)

    booking = conv.take_booking()
    assert booking is not None
    assert booking.note == ""


def test_extract_booking_no_marker_returns_text_unchanged():
    conv = _conv()
    text = "Просто обычная реплика без заявки."
    assert conv._extract_booking(text) == text
    assert conv.take_booking() is None


def test_take_booking_clears_state_after_first_call():
    conv = _conv()
    conv._extract_booking("[ЗАЯВКА: Имя=Пётр; Телефон=79215551234; Время=вечером]")

    first = conv.take_booking()
    second = conv.take_booking()

    assert first is not None
    assert second is None


def test_latest_marker_wins_when_patient_corrects_data():
    conv = _conv()
    conv._extract_booking("[ЗАЯВКА: Имя=Ольга; Телефон=79215551111; Время=утром]")
    conv._extract_booking("[ЗАЯВКА: Имя=Ольга; Телефон=79215552222; Время=вечером]")

    booking = conv.take_booking()
    assert booking.phone_raw == "79215552222"
    assert booking.preferred_time == "вечером"


def test_end_marker_and_booking_marker_coexist_in_same_chunk():
    conv = _conv()
    text = (
        "Хорошего дня! "
        "[ЗАЯВКА: Имя=Света; Телефон=79215551234; Время=завтра днём] [КОНЕЦ]"
    )
    stripped, is_end = conv._strip_end_marker(text)
    cleaned = conv._extract_booking(stripped)

    assert is_end is True
    assert "[ЗАЯВКА" not in cleaned
    assert "[КОНЕЦ]" not in cleaned
    assert "Хорошего дня!" in cleaned

    booking = conv.take_booking()
    assert booking is not None
    assert booking.name == "Света"


@pytest.mark.asyncio
async def test_greet_resets_booking_state_for_new_patient():
    conv = _conv()
    conv._extract_booking("[ЗАЯВКА: Имя=Кто-то; Телефон=79215551234; Время=утром]")
    assert conv._booking is not None

    async def sink(_chunk: bytes) -> None:
        pass

    await conv.greet(sink)

    assert conv.take_booking() is None


@pytest.mark.asyncio
async def test_farewell_never_speaks_the_booking_marker_aloud():
    """
    Регрессия: farewell() раньше вырезал только [КОНЕЦ], но не [ЗАЯВКА: ...].
    Если LLM повторит метку в реплике-прощании, её нельзя ни произносить
    вслух (TTS), ни возвращать как видимый текст.
    """
    conv = _conv(llm=_FakeLLMWithBookingMarker())
    conv.history.append({"role": "user", "content": "Спасибо, до свидания"})

    async def sink(_chunk: bytes) -> None:
        pass

    text = await conv.farewell(sink)

    assert "ЗАЯВКА" not in text
    assert all("ЗАЯВКА" not in spoken for spoken in conv.tts.spoken)

    booking = conv.take_booking()
    assert booking is not None
    assert booking.name == "Мария"
