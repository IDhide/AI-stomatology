"""
knowledge_base.py
=================
База знаний стоматологической клиники: процедуры, цены, длительности,
противопоказания, синонимы для поиска.

Цены и длительности — ориентировочные (Москва, средний+ сегмент, 2026 год);
их нужно заменить актуальными при деплое. Все ответы по цене должны
включать формулировку «от» — итоговая стоимость определяется после осмотра.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Procedure:
    code: str                          # внутренний код (e.g. "th_caries_mid")
    name: str                          # каноническое название
    synonyms: tuple[str, ...]          # как пациенты называют это в речи
    duration_min: int                  # средняя длительность приёма, минут
    price_from_rub: int                # ориентировочная цена «от», ₽
    specialty: str                     # к какому врачу: терапевт/ортопед/...
    description: str                   # 1–2 предложения для пациента
    contraindications: tuple[str, ...] = field(default_factory=tuple)
    pediatric: bool = False            # делается ли детям

    def short_for_voice(self) -> str:
        """Короткое описание для озвучивания."""
        return (
            f"{self.name}: длительность около {self.duration_min} минут, "
            f"стоимость от {self.price_from_rub} рублей. {self.description}"
        )


# ──────────────────────────────────────────────────────────────────────
# Каталог процедур (можно загружать из YAML; здесь — встроенный default)
# ──────────────────────────────────────────────────────────────────────
KB: tuple[Procedure, ...] = (
    # ─── Терапия ───
    Procedure(
        code="consult",
        name="Консультация стоматолога",
        synonyms=("консультация", "осмотр", "посмотреть", "проверить", "профилактический осмотр"),
        duration_min=30,
        price_from_rub=1000,
        specialty="терапевт",
        description="Осмотр полости рта, диагностика, план лечения и расчёт стоимости.",
    ),
    Procedure(
        code="caries_simple",
        name="Лечение кариеса (простой случай)",
        synonyms=("кариес", "пломба", "запломбировать", "дырка в зубе", "поставить пломбу"),
        duration_min=45,
        price_from_rub=4500,
        specialty="терапевт",
        description="Удаление поражённых тканей и установка светоотверждаемой пломбы.",
    ),
    Procedure(
        code="caries_deep",
        name="Лечение глубокого кариеса",
        synonyms=("глубокий кариес", "большая дырка"),
        duration_min=60,
        price_from_rub=6500,
        specialty="терапевт",
        description="Глубокое поражение с подкладкой и реставрацией.",
    ),
    Procedure(
        code="pulpitis",
        name="Лечение пульпита (1 канал)",
        synonyms=("пульпит", "нерв", "ноет зуб", "острая боль", "удалить нерв"),
        duration_min=90,
        price_from_rub=8500,
        specialty="терапевт",
        description="Эндодонтическое лечение: депульпирование и пломбирование канала.",
        contraindications=("обострение общих заболеваний",),
    ),
    Procedure(
        code="periodontitis",
        name="Лечение периодонтита",
        synonyms=("периодонтит", "флюс", "опухла десна", "гной"),
        duration_min=90,
        price_from_rub=9500,
        specialty="терапевт",
        description="Лечение воспаления у корня. Может потребоваться несколько визитов.",
    ),

    # ─── Гигиена и эстетика ───
    Procedure(
        code="hygiene_ultrasonic",
        name="Профессиональная гигиена (ультразвук + Air Flow)",
        synonyms=("чистка", "гигиена", "профессиональная чистка", "снять камни", "ультразвуковая чистка"),
        duration_min=60,
        price_from_rub=5500,
        specialty="гигиенист",
        description="Снятие камня и налёта, полировка, фторирование. Рекомендуется раз в полгода.",
    ),
    Procedure(
        code="whitening",
        name="Отбеливание зубов (офисное)",
        synonyms=("отбеливание", "белые зубы", "осветлить"),
        duration_min=90,
        price_from_rub=22000,
        specialty="терапевт",
        description="Аппаратное офисное отбеливание. Перед процедурой нужна гигиена.",
        contraindications=("беременность", "кормление", "возраст до 18", "выраженный кариес"),
    ),

    # ─── Хирургия ───
    Procedure(
        code="extraction_simple",
        name="Удаление зуба (простое)",
        synonyms=("удалить зуб", "вырвать зуб", "удаление"),
        duration_min=30,
        price_from_rub=3000,
        specialty="хирург",
        description="Удаление зуба под местной анестезией.",
    ),
    Procedure(
        code="extraction_complex",
        name="Сложное удаление (восьмёрка/ретенция)",
        synonyms=("удалить восьмёрку", "удалить зуб мудрости", "сложное удаление"),
        duration_min=60,
        price_from_rub=7500,
        specialty="хирург",
        description="Удаление с разрезом десны/распилом. Требует ОПТГ-снимка.",
    ),
    Procedure(
        code="implant",
        name="Установка импланта",
        synonyms=("имплант", "имплантация", "вживить зуб", "вкрутить имплант"),
        duration_min=90,
        price_from_rub=45000,
        specialty="имплантолог",
        description="Установка титанового импланта. Сначала консультация и КТ.",
        contraindications=("сахарный диабет в декомпенсации", "онкология", "беременность"),
    ),

    # ─── Ортодонтия ───
    Procedure(
        code="braces_consult",
        name="Консультация ортодонта",
        synonyms=("ортодонт", "прикус", "брекеты", "выравнивание", "элайнеры"),
        duration_min=45,
        price_from_rub=1500,
        specialty="ортодонт",
        description="Оценка прикуса, расчёт плана лечения брекетами или элайнерами.",
    ),
    Procedure(
        code="braces_metal",
        name="Брекет-система металлическая (1 челюсть)",
        synonyms=("металлические брекеты", "брекеты на верх", "брекеты на низ"),
        duration_min=90,
        price_from_rub=55000,
        specialty="ортодонт",
        description="Фиксация брекетов на одну челюсть. Лечение длится 12–24 мес.",
    ),

    # ─── Детская стоматология ───
    Procedure(
        code="pediatric_consult",
        name="Консультация детского стоматолога",
        synonyms=("ребёнок", "детский стоматолог", "посмотреть ребёнка"),
        duration_min=30,
        price_from_rub=1200,
        specialty="детский стоматолог",
        description="Адаптация ребёнка, осмотр, рекомендации родителям.",
        pediatric=True,
    ),
    Procedure(
        code="pediatric_seal",
        name="Герметизация фиссур (1 зуб)",
        synonyms=("герметизация", "запечатать фиссуры", "профилактика"),
        duration_min=20,
        price_from_rub=1500,
        specialty="детский стоматолог",
        description="Профилактика кариеса жевательных зубов у детей.",
        pediatric=True,
    ),
)


# ──────────────────────────────────────────────────────────────────────
# Поиск
# ──────────────────────────────────────────────────────────────────────
def find_procedure(query: str) -> Optional[Procedure]:
    """Грубый поиск по названию/синонимам. Возвращает первую находку."""
    if not query:
        return None
    q = query.lower().strip()
    # exact match по synonym/name
    for p in KB:
        if q in p.name.lower() or q in (s.lower() for s in p.synonyms):
            return p
    # частичное совпадение
    for p in KB:
        if any(s.lower() in q or q in s.lower() for s in p.synonyms):
            return p
        if any(w in p.name.lower() for w in q.split() if len(w) > 3):
            return p
    return None


def list_procedures(specialty: Optional[str] = None,
                    pediatric: Optional[bool] = None) -> list[Procedure]:
    """Список процедур с фильтрами."""
    items = list(KB)
    if specialty:
        items = [p for p in items if p.specialty == specialty]
    if pediatric is not None:
        items = [p for p in items if p.pediatric == pediatric]
    return items


# ──────────────────────────────────────────────────────────────────────
# Часы работы и врачи — переопределяются из конфига
# ──────────────────────────────────────────────────────────────────────
DEFAULT_WORKING_HOURS = {
    "mon": ("09:00", "21:00"),
    "tue": ("09:00", "21:00"),
    "wed": ("09:00", "21:00"),
    "thu": ("09:00", "21:00"),
    "fri": ("09:00", "21:00"),
    "sat": ("10:00", "20:00"),
    "sun": ("10:00", "18:00"),
}


if __name__ == "__main__":
    for q in ["кариес", "флюс", "ребёнка посмотреть", "имплант", "белые зубы"]:
        p = find_procedure(q)
        print(f"{q!r:30} → {p.name if p else 'не найдено'}")
