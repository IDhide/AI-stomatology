"""
Ручной прогон диалоговых сценариев против РЕАЛЬНОГО Grok (тратит токены!).

STT и TTS замоканы: реплики пациента заданы текстом, озвучка пропускается.
Проверяем «ум» Оливии: ответы, метки [ЗАЯВКА: ...] и [КОНЕЦ].

Запуск из папки server/:
    ../.venv/bin/python scripts/probe_grok.py            # все сценарии
    ../.venv/bin/python scripts/probe_grok.py pain price # только выбранные
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.orchestrator import Conversation  # noqa: E402
from app.persona import Persona  # noqa: E402
from app.providers.llm_grok import GrokLLM  # noqa: E402


class ScriptSTT:
    """Отдаёт реплики пациента по очереди, игнорируя аудио."""

    def __init__(self, lines: list[str]):
        self._lines = list(lines)

    async def transcribe(self, audio: bytes) -> str:
        return self._lines.pop(0) if self._lines else ""


class NullTTS:
    async def stream(self, text: str):
        return
        yield  # noqa: unreachable — нужен для async-генератора


SCENARIOS: dict[str, list[str]] = {
    "booking": [
        "Здравствуйте, хочу записаться на чистку зубов",
        "Мария",
        "Завтра после шести вечера",
        "Восемь девять два один пять пять пять двенадцать тридцать четыре",
        "Да, всё верно",
        "Спасибо, до свидания",
    ],
    "pain": [
        "У меня очень сильно болит зуб слева снизу, второй день уже",
        "Да, записывайте, меня зовут Игорь",
    ],
    "price": [
        "Сколько у вас стоят виниры?",
        "А это с работой врача уже или отдельно платить?",
        "Понятно, спасибо, я подумаю",
    ],
    "garbage": [
        "Ага ну это самое как его там короче",
        "Простите, я хотел узнать, лечите ли вы детей",
    ],
    "filler_poka": [
        "Ну я пока подумаю насчёт записи",
        "А во сколько вы завтра открываетесь?",
    ],
    "offtopic": [
        "Слушай, а кто выиграет чемпионат мира по футболу?",
        "А ты сама за кого болеешь?",
        "Ладно. А сколько стоит пломба?",
    ],
    # Подбор времени по демо-расписанию DIKIDI: завтра занято 12:00–13:00,
    # 14:00–15:30 и 17:00–18:00; сегодня — 15:00–16:00, 16:30–17:30, 18:00–19:00.
    "pick_time": [
        "Здравствуйте, хочу записаться на завтра на десять утра",
        "А на тринадцать ноль-ноль тогда",
        "Меня зовут Олег, телефон восемь девять два один пять пять пять двенадцать тридцать четыре",
        "Да, верно",
        "Спасибо, до свидания",
    ],
}


async def run_scenario(name: str, lines: list[str]) -> None:
    cfg = get_settings()
    llm = GrokLLM(
        api_key=cfg.xai_api_key,
        base_url=cfg.grok_base_url,
        model=cfg.grok_model,
        temperature=cfg.llm_temperature,
        max_tokens=cfg.llm_max_tokens,
    )
    persona = Persona(cfg.prompts_path)
    conv = Conversation(ScriptSTT(lines), llm, NullTTS(), persona)

    # Демо-расписание DIKIDI в контекст — как на киоске при появлении пациента
    from app.dikidi_readonly import DikidiReadOnly

    dikidi = DikidiReadOnly(demo=True)
    bookings = await dikidi.today_bookings()
    free = await dikidi.free_slots(days=cfg.dikidi_days_ahead)
    conv.set_context(DikidiReadOnly.format_for_prompt(bookings, dikidi.available, free_slots=free))

    print(f"\n{'═' * 70}\nСЦЕНАРИЙ: {name}\n{'═' * 70}")
    greeting = await conv.greet(lambda chunk: asyncio.sleep(0))
    print(f"🤖(приветствие) {greeting}")

    async def sink(chunk: bytes) -> None:
        pass

    for _ in lines:
        before = len(conv.history)
        heard = await conv.handle_utterance(b"\x00" * 32000, sink)
        if not heard:
            print("👤 (не расслышала)")
            continue
        for msg in conv.history[before:]:
            icon = "👤" if msg["role"] == "user" else "🤖"
            print(f"{icon} {msg['content']}")
        if conv.ended:
            print("── [КОНЕЦ]: Оливия завершила диалог")
            break

    booking = conv.take_booking()
    if booking:
        print(f"── [ЗАЯВКА]: {booking}")
    await llm.aclose()


async def main() -> None:
    names = sys.argv[1:] or list(SCENARIOS)
    for name in names:
        if name not in SCENARIOS:
            print(f"нет сценария {name!r}, есть: {', '.join(SCENARIOS)}")
            continue
        await run_scenario(name, SCENARIOS[name])


if __name__ == "__main__":
    asyncio.run(main())
