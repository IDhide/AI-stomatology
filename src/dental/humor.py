"""
humor.py
========
Лёгкий стоматологический юмор для администратора-ассистента.

Принципы:
- Юмор НИКОГДА не за счёт пациента, не про боль, не про деньги, не про страх.
- Шутка появляется только если ситуация однозначно лёгкая:
  * intent ∈ {GREETING, BOOK на гигиену/осмотр, SMALLTALK, THANKS}
  * triage.urgency ∈ {CONSULT, PLANNED, COSMETIC}  и triage.priority >= 2
  * в последних N репликах нет тревожных слов (боль, страх, паника, срочно).
- На каждые 3-4 реплики — максимум одна шутка.
- Шутки короткие (до 15 слов), безопасные, проверены на «можно ли это сказать
  90-летней бабушке и 8-летнему ребёнку».

Каталог разделён по контексту, чтобы шутка не звучала случайно.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .intents import Intent
from .triage import TriageResult, Urgency


@dataclass(frozen=True)
class Joke:
    text: str
    context: str            # greeting / booking / hygiene / smalltalk / farewell / waiting
    safe_for_kids: bool = True


# ──────────────────────────────────────────────────────────────────────
# Каталог. Тон: лёгкая, тёплая, профессиональная самоирония.
# ──────────────────────────────────────────────────────────────────────
JOKE_CATALOG: tuple[Joke, ...] = (
    # Приветствие
    Joke("У нас тут уютно — даже зубные щётки улыбаются.", "greeting"),
    Joke("Добро пожаловать! Здесь, кстати, единственное место, где «скажите 'а'» — это вежливая просьба.", "greeting"),
    Joke("Заходите, у нас всё по-доброму: ни одного зуба сегодня не пострадало.", "greeting"),

    # Запись на гигиену / осмотр
    Joke("Профилактика — это как сериал: лучше смотреть по одной серии в полгода, чем весь сезон сразу.", "hygiene"),
    Joke("Чистка раз в полгода — и ваши зубы будут улыбаться даже на фото в паспорте.", "hygiene"),
    Joke("Зубная щётка — друг, нить — лучший друг, а мы с врачом — давние знакомые, которые рады встрече раз в полгода.", "hygiene"),

    # Small talk
    Joke("Говорят, у дантистов лучшее чувство юмора — нам по работе положено быть терпеливыми.", "smalltalk"),
    Joke("Я администратор и немного робот, но улыбаться умею не хуже наших врачей.", "smalltalk"),

    # При прощании
    Joke("До встречи! Передавайте привет зубной щётке — она вас ждёт.", "farewell"),
    Joke("Всего доброго! И помните: яблоко в день — врачу подарок, два раза в год к стоматологу — двойной подарок.", "farewell"),

    # Когда пациент благодарит
    Joke("Пожалуйста! Моя работа — чтобы у вас было поменьше поводов меня вспоминать.", "thanks"),
)

# Триггерные слова — если они есть в недавней истории, юмор НЕ выдаём.
ANXIETY_WORDS = {
    "боль", "болит", "боюсь", "страшно", "страх", "паник", "ужас",
    "плохо", "тревож", "не могу", "ноет", "опух", "кровь", "флюс",
    "срочно", "беда", "помогите",
}


def _has_anxiety(history: list[str]) -> bool:
    """True если в последних репликах пользователя есть «тревожные» слова."""
    blob = " ".join(history).lower()
    return any(w in blob for w in ANXIETY_WORDS)


def maybe_joke(
    intent: Intent,
    triage_result: TriageResult | None,
    user_history: list[str] | None = None,
    last_joke_turns_ago: int = 999,
    rng: random.Random | None = None,
) -> str | None:
    """
    Возвращает текст шутки либо None.

    Параметры:
      intent: что хочет пациент.
      triage_result: результат триажа (может быть None).
      user_history: последние N реплик пациента (для проверки тревожности).
      last_joke_turns_ago: сколько ходов назад была последняя шутка (≥3 — норм).
      rng: для воспроизводимости в тестах.
    """
    rng = rng or random.Random()

    # 1. Не шутим чаще, чем раз в 3 хода
    if last_joke_turns_ago < 3:
        return None

    # 2. Не шутим если в недавнем диалоге была тревога
    if user_history and _has_anxiety(user_history):
        return None

    # 3. Не шутим при срочных и эстетика-без-улыбки кейсах
    if triage_result and triage_result.urgency in (Urgency.URGENT,):
        return None
    if triage_result and triage_result.alert:
        return None

    # 4. Выбираем контекст по intent
    context_map = {
        Intent.GREETING: "greeting",
        Intent.THANKS:   "thanks",
        Intent.FAREWELL: "farewell",
        Intent.SMALLTALK: "smalltalk",
        Intent.BOOK:      "hygiene",   # шутим только если запись на «лёгкое» — фильтр ниже
    }
    ctx = context_map.get(intent)
    if not ctx:
        return None

    # Если intent=BOOK, шутить можно только когда триаж=plan/cosmetic/consult
    if intent == Intent.BOOK and triage_result and triage_result.urgency not in (
        Urgency.PLANNED, Urgency.CONSULT
    ):
        return None

    # 5. Случайно, но не всегда — иначе ассистент превратится в стендап-комика.
    if rng.random() > 0.45:
        return None

    candidates = [j.text for j in JOKE_CATALOG if j.context == ctx]
    if not candidates:
        return None
    return rng.choice(candidates)


if __name__ == "__main__":
    from .intents import classify_intent
    from .triage import triage

    rng = random.Random(42)
    cases = [
        "Здравствуйте",
        "У меня очень болит зуб, помогите",
        "Хочу записаться на чистку",
        "Спасибо большое",
        "До свидания",
    ]
    for c in cases:
        intent = classify_intent(c).intent
        tri = triage(c)
        j = maybe_joke(intent, tri, user_history=[c], last_joke_turns_ago=10, rng=rng)
        print(f"{c!r:45} → {j!r}")
