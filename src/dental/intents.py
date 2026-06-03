"""
intents.py
==========
Лёгкий быстрый классификатор намерений (без LLM) на ключевых словах и
регулярках. Запускается ДО обращения к LLM и:
- ловит дешёвые случаи (приветствие/прощание/уточнение цены/часы работы),
- даёт сигнал «острая боль» для триажа,
- даёт LLM подсказку, какие инструменты вызывать.

Это сильно экономит время отклика — на «здравствуйте» и «до свидания»
ассистент отвечает за 0.1 с, не дожидаясь Ollama.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    GREETING       = "greeting"
    FAREWELL       = "farewell"
    THANKS         = "thanks"
    BOOK           = "book"            # хочу записаться
    CANCEL         = "cancel"          # отменить запись
    RESCHEDULE     = "reschedule"      # перенести
    ASK_PRICE      = "ask_price"
    ASK_HOURS      = "ask_hours"
    ASK_ADDRESS    = "ask_address"
    ASK_DOCTOR     = "ask_doctor"
    ASK_FREE_SLOT  = "ask_free_slot"
    URGENT_PAIN    = "urgent_pain"     # острая боль
    PEDIATRIC      = "pediatric"       # про ребёнка
    SMALLTALK      = "smalltalk"
    UNKNOWN        = "unknown"


@dataclass
class IntentMatch:
    intent: Intent
    confidence: float
    matched: str | None = None


# ──────────────────────────────────────────────────────────────────────
# Паттерны (порядок важен: первые — самые приоритетные)
# ──────────────────────────────────────────────────────────────────────
PATTERNS: list[tuple[Intent, list[str]]] = [
    (Intent.URGENT_PAIN, [
        r"\bостра[яй]\s*боль",
        r"\bочень\s*болит",
        r"\bсильно\s*болит",
        r"\bне\s*могу\s*терпеть",
        r"\bфлюс\b",
        r"\bопух(?:ло|ла)\b",
        r"\bкровотечен",
        r"\bвыбил\s*зуб",
        r"\bтравм[аы]",
        r"\bгной\b",
    ]),
    (Intent.PEDIATRIC, [
        r"\bребён?нк[аеу]\b",
        r"\bдетс(?:кий|кого|кому)\b",
        r"\bсын(?:а|у|ом)?\b",
        r"\bдочь\b|\bдочк[еиу]\b",
    ]),
    (Intent.GREETING, [
        r"^\s*(?:здравствуй(?:те)?|добрый\s*(?:день|вечер|утро)|приветствую|привет)\b",
        r"\bдобрый\s*день\b",
    ]),
    (Intent.FAREWELL, [
        r"\bдо\s*свидания\b",
        r"\bпока\b",
        r"\bвсего\s*доброго\b",
        r"\bвсё,?\s*спасибо\b",
        r"\bпойду\b",
    ]),
    (Intent.THANKS, [
        r"\bспасибо\b",
        r"\bблагодар",
    ]),
    (Intent.CANCEL, [
        r"\bотмен(?:ить|и|ите|ю)\b",
        r"\bне\s*приду\b",
        r"\bотказ(?:аться|ываюсь)\b",
    ]),
    (Intent.RESCHEDULE, [
        r"\bперенест(?:и|е)\b",
        r"\bперенесите?\b",
        r"\bпоменять\s*время\b",
    ]),
    (Intent.BOOK, [
        r"\bзапиш(?:и|ите|усь)\b",
        r"\bзапис(?:аться|ать|ь)\b",
        r"\bхоч[уе]\s*на\s*приём\b",
        r"\bна\s*осмотр\b",
    ]),
    (Intent.ASK_FREE_SLOT, [
        r"\bсвободн[ыо]",
        r"\bкогда\s*можно\b",
        r"\bкакое\s*(?:есть\s*)?время\b",
        r"\bкакие\s*окна\b",
        r"\bближайш",
    ]),
    (Intent.ASK_PRICE, [
        r"\bсколько\s*стоит\b",
        r"\bсколько\s*будет\b",
        r"\bцен[аы]\b",
        r"\bстоимость\b",
        r"\bпрайс\b",
    ]),
    (Intent.ASK_HOURS, [
        r"\bв\s*како[ме]\s*час[уе]\s*работа",
        r"\bчасы\s*работы\b",
        r"\bдо\s*скольких\s*работа",
        r"\bкогда\s*вы\s*открыт",
        r"\bвыходн(?:ой|ые)\b",
    ]),
    (Intent.ASK_ADDRESS, [
        r"\bгде\s*вы\s*находит",
        r"\bадрес\b",
        r"\bкак\s*до\s*вас\s*добрать",
        r"\bметро\b",
    ]),
    (Intent.ASK_DOCTOR, [
        r"\bкто\s*врач\b",
        r"\bкакой\s*врач\b",
        r"\bкто\s*будет\s*принимать\b",
        r"\bопыт\s*врача\b",
        r"\bстаж\s*врача\b",
    ]),
    (Intent.SMALLTALK, [
        r"\bкак\s*дел[аи]\b",
        r"\bпогод[аеу]\b",
        r"\bтебя\s*зовут\b",
        r"\bкак\s*тебя\b",
    ]),
]


def classify_intent(text: str) -> IntentMatch:
    """Возвращает наиболее вероятный intent. UNKNOWN если ничего не подошло."""
    if not text:
        return IntentMatch(Intent.UNKNOWN, 0.0)
    t = text.lower()

    for intent, patterns in PATTERNS:
        for pat in patterns:
            m = re.search(pat, t)
            if m:
                # «уверенность» — грубая эвристика по длине совпадения
                conf = min(1.0, 0.6 + 0.05 * len(m.group(0)))
                return IntentMatch(intent, conf, m.group(0))
    return IntentMatch(Intent.UNKNOWN, 0.0)


if __name__ == "__main__":
    samples = [
        "Здравствуйте",
        "У меня очень болит зуб, не могу терпеть",
        "Сколько стоит чистка?",
        "Можно записать ребёнка к стоматологу?",
        "Перенесите мою запись на завтра",
        "До свидания",
        "Я хотел бы узнать ваш адрес",
        "Какие окна свободны на пятницу?",
    ]
    for s in samples:
        m = classify_intent(s)
        print(f"{s!r:55} → {m.intent.value:15} conf={m.confidence:.2f}  ({m.matched})")
