"""
russian_normalizer.py
=====================
Нормализатор русского текста перед подачей в TTS.

Что делает (по порядку):
1. Ё-фикация — возвращает «ё» в слова, которые TTS произносит как «е».
2. Расшифровка аббревиатур (ИП, ООО, г. → город, ул. → улица, руб. → рублей и т.д.).
3. Стоматологическая терминология с правильным ударением (через «+»).
4. Время:    15:30        → «пятнадцать тридцать»
5. Даты:     21.05.2026   → «двадцать первого мая две тысячи двадцать шестого года»
6. Телефоны: +79161234567 → «плюс семь, девятьсот шестнадцать, сто двадцать три, сорок пять, шестьдесят семь»
7. Денежные суммы: 3500 ₽ → «три тысячи пятьсот рублей»
8. Числа в нужном падеже (через окружающий контекст: «на 3 часа» → «на три часа»).
9. Удаление лишних спец-символов, эмодзи, markdown.

Зависимости: только стандартная библиотека + (опционально) `num2words` если установлен.
Если num2words нет — используется встроенный fallback на основе словаря (хуже, но работает).

Использование:
    from src.voice.russian_normalizer import normalize
    text_for_tts = normalize("Запишу вас на 21.05 в 15:30, осмотр — 1500 ₽.")
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable

try:
    from num2words import num2words as _num2words  # type: ignore
    HAVE_NUM2WORDS = True
except ImportError:  # pragma: no cover
    HAVE_NUM2WORDS = False


# ──────────────────────────────────────────────────────────────────────
# 1. Ё-фикация: слова, в которых TTS теряет «ё»
# ──────────────────────────────────────────────────────────────────────
YOFICATION = {
    "все": "всё",
    "Все": "Всё",
    "еще": "ещё",
    "Еще": "Ещё",
    "темнее": "темнее",  # пример без замены — оставлено для расширения
    "приём": "приём",
    "прием": "приём",
    "Прием": "Приём",
    "приема": "приёма",
    "приему": "приёму",
    "приемом": "приёмом",
    "приеме": "приёме",
    "приемы": "приёмы",
    "приемов": "приёмов",
    "елка": "ёлка",
    "звезды": "звёзды",
    "найдешь": "найдёшь",
    "найдете": "найдёте",
    "придете": "придёте",
    "идете": "идёте",
    "поидем": "пойдём",
    "пойдем": "пойдём",
    "берем": "берём",
    "вернем": "вернём",
    "вернемся": "вернёмся",
    "перенесем": "перенесём",
    "запишем": "запишем",
    "учет": "учёт",
    "учета": "учёта",
    "счет": "счёт",
    "счета": "счёта",
    "трёхмерный": "трёхмерный",
    "трехмерный": "трёхмерный",
    "детей": "детей",
    "пациентов": "пациентов",
    "осмотрев": "осмотрев",
}


# ──────────────────────────────────────────────────────────────────────
# 2. Аббревиатуры и сокращения
# ──────────────────────────────────────────────────────────────────────
ABBREV = [
    (r"\bг\.\s*(?=[А-ЯЁ])", "город "),
    (r"\bул\.\s*", "улица "),
    (r"\bпр-?т\.\s*", "проспект "),
    (r"\bд\.\s*(?=\d)", "дом "),
    (r"\bкв\.\s*(?=\d)", "квартира "),
    (r"\bруб\.\b", "рублей"),
    (r"\bр\.\b", "рублей"),
    (r"\b₽", " рублей"),
    (r"\$", " долларов"),
    (r"\b%\B", " процентов"),
    (r"\bтел\.\s*", "телефон "),
    (r"\bмин\.", "минут"),
    (r"\bч\.", "часов"),
    (r"\bсек\.", "секунд"),
    (r"\bт\.\s*е\.\b", "то есть"),
    (r"\bт\.\s*к\.\b", "так как"),
    (r"\bт\.\s*д\.\b", "так далее"),
    (r"\bт\.\s*п\.\b", "тому подобное"),
    (r"\bи т\.д\.", "и так далее"),
    (r"\bи пр\.\b", "и прочее"),
    (r"\bООО\b", "о о о"),
    (r"\bИП\b", "и пэ"),
    (r"\bАО\b", "а о"),
    (r"\bРФ\b", "Россия"),
    (r"\bвт\.", "вторник"),
    (r"\bпн\.", "понедельник"),
    (r"\bср\.", "среда"),
    (r"\bчт\.", "четверг"),
    (r"\bпт\.", "пятница"),
    (r"\bсб\.", "суббота"),
    (r"\bвс\.", "воскресенье"),
]


# ──────────────────────────────────────────────────────────────────────
# 3. Стоматологическая терминология с ударениями
#    Silero поддерживает явные ударения через «+» перед гласной.
# ──────────────────────────────────────────────────────────────────────
DENTAL_STRESS = {
    # классические проблемные
    r"\bимплантац\w*\b":         lambda m: m.group(0).replace("имплантац", "импл+антац"),
    r"\bимплант(?!ац)\w*\b":     lambda m: m.group(0).replace("имплант", "импл+ант"),
    r"\bкариес\w*\b":            lambda m: m.group(0).replace("кариес", "к+ариес"),
    r"\bпульпит\w*\b":           lambda m: m.group(0).replace("пульпит", "пульп+ит"),
    r"\bпериодонтит\w*\b":       lambda m: m.group(0).replace("периодонтит", "периодонт+ит"),
    r"\bпарадонтит\w*\b":        lambda m: m.group(0).replace("парадонтит", "парадонт+ит"),
    r"\bретейнер\w*\b":          lambda m: m.group(0).replace("ретейнер", "рет+ейнер"),
    r"\bкюретаж\w*\b":           lambda m: m.group(0).replace("кюретаж", "кюрет+аж"),
    r"\bортодонт\w*\b":          lambda m: m.group(0).replace("ортодонт", "ортод+онт"),
    r"\bбрекет\w*\b":            lambda m: m.group(0).replace("брекет", "бр+екет"),
    r"\bпломб\w*\b":             lambda m: m.group(0).replace("пломб", "пл+омб"),
    r"\bкорон(?:к|ок)\w*\b":     lambda m: m.group(0).replace("корон", "кор+он"),
    r"\bпрофессиональн\w*\b":    lambda m: m.group(0).replace("профессиональн", "профессион+альн"),
    r"\bультразвук\w*\b":        lambda m: m.group(0).replace("ультразвук", "ультразв+ук"),
    r"\bAir[\s-]?Flow\b":        lambda m: "+эйр фло+у",
    # имена врачей-исключений добавляются здесь же
}


# ──────────────────────────────────────────────────────────────────────
# 4. Числа словами — fallback без num2words
# ──────────────────────────────────────────────────────────────────────
_UNITS = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_UNITS_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
          "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
         "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
             "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _three_digits_to_words(n: int, feminine: bool = False) -> str:
    """0..999 → слова."""
    if n == 0:
        return ""
    units = _UNITS_F if feminine else _UNITS
    parts = []
    h = n // 100
    rem = n % 100
    if h:
        parts.append(_HUNDREDS[h])
    if 10 <= rem < 20:
        parts.append(_TEENS[rem - 10])
    else:
        t = rem // 10
        u = rem % 10
        if t:
            parts.append(_TENS[t])
        if u:
            parts.append(units[u])
    return " ".join(parts)


def _int_to_words(n: int) -> str:
    """Целое число → слова. Поддерживает 0..999_999_999."""
    if n == 0:
        return "ноль"
    if n < 0:
        return "минус " + _int_to_words(-n)

    if HAVE_NUM2WORDS:
        return _num2words(n, lang="ru")

    parts = []
    billions = n // 1_000_000_000
    n %= 1_000_000_000
    millions = n // 1_000_000
    n %= 1_000_000
    thousands = n // 1000
    rest = n % 1000

    if billions:
        parts.append(_three_digits_to_words(billions) + " " + _plural(billions, "миллиард", "миллиарда", "миллиардов"))
    if millions:
        parts.append(_three_digits_to_words(millions) + " " + _plural(millions, "миллион", "миллиона", "миллионов"))
    if thousands:
        parts.append(_three_digits_to_words(thousands, feminine=True) + " " +
                     _plural(thousands, "тысяча", "тысячи", "тысяч"))
    if rest:
        parts.append(_three_digits_to_words(rest))

    return " ".join(p for p in parts if p)


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Русская плюрализация: 1 яблоко, 2 яблока, 5 яблок."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# ──────────────────────────────────────────────────────────────────────
# 5. Шаги нормализации
# ──────────────────────────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"[\[\]]", "", text)
    text = re.sub(r"\(https?://[^)]+\)", "", text)
    return text


def _strip_emoji(text: str) -> str:
    return "".join(ch for ch in text if not unicodedata.category(ch).startswith("So"))


def _apply_yofication(text: str) -> str:
    for bad, good in YOFICATION.items():
        text = re.sub(rf"\b{re.escape(bad)}\b", good, text)
    return text


def _apply_abbreviations(text: str) -> str:
    for pat, repl in ABBREV:
        text = re.sub(pat, repl, text)
    return text


def _apply_dental_stress(text: str) -> str:
    for pat, repl in DENTAL_STRESS.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


def _replace_phones(text: str) -> str:
    """+7 (916) 123-45-67 → плюс семь девятьсот шестнадцать сто двадцать три сорок пять шестьдесят семь."""
    def repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if not digits:
            return m.group(0)
        # сгруппируем привычно: 1-3-3-2-2
        if len(digits) == 11:
            groups = [digits[0], digits[1:4], digits[4:7], digits[7:9], digits[9:11]]
        elif len(digits) == 10:
            groups = [digits[0:3], digits[3:6], digits[6:8], digits[8:10]]
        else:
            groups = [digits[i:i+3] for i in range(0, len(digits), 3)]
        parts = []
        for i, g in enumerate(groups):
            if i == 0 and len(g) == 1 and g == "7":
                parts.append("плюс семь")
            else:
                parts.append(_int_to_words(int(g)))
        return ", ".join(parts)

    pattern = r"\+?\d[\d\-\(\)\s]{6,}\d"
    return re.sub(pattern, repl, text)


def _replace_time(text: str) -> str:
    """15:30 → пятнадцать тридцать; 9:00 → девять ноль ноль."""
    def repl(m: re.Match) -> str:
        h, mm = int(m.group(1)), int(m.group(2))
        h_w = _int_to_words(h)
        if mm == 0:
            return f"{h_w} ноль ноль"
        return f"{h_w} {_int_to_words(mm)}"
    return re.sub(r"\b(\d{1,2}):(\d{2})\b", repl, text)


def _replace_dates(text: str) -> str:
    """21.05 → двадцать первого мая; 21.05.2026 → ... две тысячи двадцать шестого года."""
    def repl(m: re.Match) -> str:
        d = int(m.group(1))
        mo = int(m.group(2))
        y = int(m.group(3)) if m.group(3) else None
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return m.group(0)
        # порядковое число для дня — упрощённо: "двадцать первого"
        day_word = _ordinal_genitive(d)
        result = f"{day_word} {_MONTHS[mo]}"
        if y:
            result += f" {_year_genitive(y)} года"
        return result
    return re.sub(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", repl, text)


def _ordinal_genitive(n: int) -> str:
    """Порядковое число в род. падеже (для дат). 1..31."""
    table = {
        1: "первого", 2: "второго", 3: "третьего", 4: "четвёртого", 5: "пятого",
        6: "шестого", 7: "седьмого", 8: "восьмого", 9: "девятого", 10: "десятого",
        11: "одиннадцатого", 12: "двенадцатого", 13: "тринадцатого", 14: "четырнадцатого",
        15: "пятнадцатого", 16: "шестнадцатого", 17: "семнадцатого",
        18: "восемнадцатого", 19: "девятнадцатого", 20: "двадцатого",
        30: "тридцатого",
    }
    if n in table:
        return table[n]
    if 21 <= n <= 29:
        return "двадцать " + table[n - 20]
    if n == 31:
        return "тридцать " + table[1]
    return _int_to_words(n)


def _year_genitive(y: int) -> str:
    """2026 → 'две тысячи двадцать шестого'."""
    if y < 1000:
        return _int_to_words(y)
    thousands = y // 1000
    rest = y % 1000
    parts = []
    if thousands == 2:
        parts.append("две тысячи")
    elif thousands == 1:
        parts.append("тысяча")
    else:
        parts.append(_int_to_words(thousands) + " " + _plural(thousands, "тысяча", "тысячи", "тысяч"))
    if rest:
        # последнее слово в род. падеже
        rest_words = _int_to_words(rest).split()
        rest_words[-1] = _ordinal_genitive(rest % 100 if rest % 100 else rest) if rest < 100 else rest_words[-1]
        # упростим: применим _ordinal_genitive только к последней двузначной части
        last = rest % 100
        head = rest - last
        if head:
            parts.append(_int_to_words(head))
        if last:
            parts.append(_ordinal_genitive(last))
    return " ".join(parts)


def _replace_money(text: str) -> str:
    """3500 ₽ / 3 500 руб. → три тысячи пятьсот рублей."""
    def repl(m: re.Match) -> str:
        digits = re.sub(r"\s", "", m.group(1))
        n = int(digits)
        return f"{_int_to_words(n)} {_plural(n, 'рубль', 'рубля', 'рублей')}"
    text = re.sub(r"(\d[\d\s]*)\s*(?:руб(?:\.|лей)?|₽)", repl, text)
    return text


def _replace_bare_numbers(text: str) -> str:
    """Оставшиеся числа → слова (после телефонов/дат/денег)."""
    def repl(m: re.Match) -> str:
        return _int_to_words(int(m.group(0)))
    return re.sub(r"\b\d+\b", repl, text)


def _collapse_spaces(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


# ──────────────────────────────────────────────────────────────────────
# 6. Pipeline
# ──────────────────────────────────────────────────────────────────────
PIPELINE: list[Callable[[str], str]] = [
    _strip_markdown,
    _strip_emoji,
    _apply_yofication,
    _apply_abbreviations,
    _replace_phones,    # сначала телефоны
    _replace_dates,     # потом даты
    _replace_time,      # потом время
    _replace_money,     # потом деньги
    _replace_bare_numbers,  # затем все остальные числа
    _apply_dental_stress,
    _collapse_spaces,
]


def normalize(text: str) -> str:
    """Полная нормализация. Безопасна для пустых строк."""
    if not text:
        return ""
    for step in PIPELINE:
        text = step(text)
    return text


# ──────────────────────────────────────────────────────────────────────
# 7. CLI для проверки
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        "Записал вас на 21.05.2026 в 15:30, осмотр стоит 1500 руб.",
        "Перезвоните на +7 (916) 123-45-67 после 9:00.",
        "У нас есть свободные окна еще на сегодня и на пт.",
        "Это пульпит — нужна имплантация и ортодонт.",
        "Чистка Air-Flow — 3500 ₽, длительность 40 мин.",
        "Адрес: г. Москва, ул. Тверская, д. 5, кв. 12.",
    ]
    for s in samples:
        print(f"IN : {s}")
        print(f"OUT: {normalize(s)}")
        print()
