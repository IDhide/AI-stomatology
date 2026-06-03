"""
triage.py
=========
Триаж пациента по жалобе. Определяет:
- urgency: urgent / planned / cosmetic / pediatric / consult
- к какому специалисту направить
- какой приоритет при подборе слота (раньше/обычный/любой)
- нужно ли предупредить дежурного врача (флаг alert)

Логика — на ключевых словах. Это намеренно: критичные кейсы должны
обрабатываться детерминированно, а не на «авось LLM поймёт».
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Urgency(str, Enum):
    URGENT    = "urgent"      # острая боль, флюс, травма → сегодня
    PLANNED   = "planned"     # обычная запись
    COSMETIC  = "cosmetic"    # эстетика, без боли
    PEDIATRIC = "pediatric"   # детский кейс
    CONSULT   = "consult"     # просто хочет проконсультироваться


@dataclass
class TriageResult:
    urgency: Urgency
    specialty: str            # терапевт / хирург / ортодонт / ...
    priority: int             # 0 = асап, 1 = сегодня, 2 = на этой неделе, 3 = любое
    alert: bool               # сигналить дежурному
    reason: str               # короткое объяснение (для логов и LLM)


URGENT_KEYWORDS = [
    "острая боль", "очень болит", "сильно болит", "невыносимо",
    "не могу терпеть", "флюс", "опух", "опухло", "кровотеч",
    "выбил зуб", "сломал зуб", "травма", "гной", "температур",
    "не могу есть", "не могу спать",
]

COSMETIC_KEYWORDS = [
    "отбеливание", "белые зубы", "виниры", "винир", "эстетик",
    "красивая улыбка", "люминиры",
]

ORTHO_KEYWORDS = [
    "брекеты", "элайнер", "прикус", "выровнять", "кривые зубы",
    "ортодонт",
]

SURGERY_KEYWORDS = [
    "удалить", "удаление", "восьмёрк", "зуб мудрости", "вырвать",
    "имплант", "имплантац",
]

HYGIENE_KEYWORDS = [
    "чистка", "гигиен", "снять камни", "налёт", "air flow", "эйрфлоу",
]

PEDIATRIC_KEYWORDS = [
    "ребёнок", "ребенок", "ребёнка", "ребенка", "ребёнку", "ребенку",
    "детск", "сын", "доч", "молочный зуб", "молочные зубы",
]


def _has_any(text: str, words: list[str]) -> bool:
    t = text.lower()
    return any(re.search(rf"\b{re.escape(w)}", t) for w in words)


def triage(text: str) -> TriageResult:
    """Главная функция триажа."""
    if not text:
        return TriageResult(Urgency.CONSULT, "терапевт", 3, False, "Пустая жалоба")

    t = text.lower()
    # 1. Острая боль — самый высокий приоритет, перебивает всё
    if _has_any(t, URGENT_KEYWORDS):
        spec = "хирург" if _has_any(t, ["флюс", "опух", "гной", "травма", "выбил", "сломал"]) else "терапевт"
        return TriageResult(
            urgency=Urgency.URGENT,
            specialty=spec,
            priority=0,
            alert=True,
            reason="Признаки острой боли/воспаления",
        )

    # 2. Ребёнок
    if _has_any(t, PEDIATRIC_KEYWORDS):
        return TriageResult(
            urgency=Urgency.PEDIATRIC,
            specialty="детский стоматолог",
            priority=2,
            alert=False,
            reason="Пациент — ребёнок",
        )

    # 3. Косметика/эстетика
    if _has_any(t, COSMETIC_KEYWORDS):
        return TriageResult(
            urgency=Urgency.COSMETIC,
            specialty="терапевт",  # или эстетист — зависит от клиники
            priority=3,
            alert=False,
            reason="Эстетическая процедура",
        )

    # 4. Ортодонтия
    if _has_any(t, ORTHO_KEYWORDS):
        return TriageResult(
            urgency=Urgency.PLANNED,
            specialty="ортодонт",
            priority=3,
            alert=False,
            reason="Ортодонтический запрос",
        )

    # 5. Хирургия / импланты
    if _has_any(t, SURGERY_KEYWORDS):
        return TriageResult(
            urgency=Urgency.PLANNED,
            specialty="хирург",
            priority=2,
            alert=False,
            reason="Хирургический запрос",
        )

    # 6. Гигиена
    if _has_any(t, HYGIENE_KEYWORDS):
        return TriageResult(
            urgency=Urgency.PLANNED,
            specialty="гигиенист",
            priority=3,
            alert=False,
            reason="Профессиональная гигиена",
        )

    # 7. Дефолт — обычная консультация у терапевта
    return TriageResult(
        urgency=Urgency.CONSULT,
        specialty="терапевт",
        priority=2,
        alert=False,
        reason="Консультация общего профиля",
    )


def explain_for_patient(r: TriageResult) -> str:
    """Короткое объяснение пациенту голосом."""
    if r.urgency == Urgency.URGENT:
        return ("Понимаю, ситуация срочная. Постараюсь найти вам ближайшее окно "
                "сегодня и предупрежу дежурного врача.")
    if r.urgency == Urgency.PEDIATRIC:
        return "Запишу к детскому стоматологу, у нас принимает специалист по работе с детьми."
    if r.urgency == Urgency.COSMETIC:
        return "Для эстетических процедур сначала нужна короткая консультация — подберём план."
    if r.specialty == "ортодонт":
        return "По брекетам и элайнерам — это к ортодонту, начнём с консультации."
    if r.specialty == "хирург":
        return "Запишу к хирургу. Заранее посмотрим снимок, если у вас есть."
    if r.specialty == "гигиенист":
        return "Профессиональную гигиену проводит гигиенист, занимает около часа."
    return "Запишу на консультацию к терапевту, врач посмотрит и составит план."


if __name__ == "__main__":
    samples = [
        "У меня очень болит зуб со вчерашнего дня",
        "Хочу отбеливание",
        "Запишите ребёнка к стоматологу",
        "Хочу поставить брекеты",
        "Удалите мне восьмёрку",
        "Хочу записаться на чистку",
        "Просто хочу провериться",
        "Опухла десна, температура",
    ]
    for s in samples:
        r = triage(s)
        print(f"{s!r:55} → {r.urgency.value:9} {r.specialty:20} prio={r.priority} alert={r.alert}")
