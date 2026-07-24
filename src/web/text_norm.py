"""
text_norm.py
============
Нормализация русского текста перед синтезом речи (TTS).

Зачем: модель произносит ровно то, что видит. «28500 руб» она скажет как
«двадцать восемь тысяч пятьсот руб» (буквально «руб»), «16:00» — как
«шестнадцать двоеточие ноль ноль». Чтобы Оливия говорила по-человечески,
переводим числа, деньги, время, проценты и сокращения в слова с
правильными падежными окончаниями.

Применяется ко всем TTS-движкам централизованно в tts.synthesize().
"""
from __future__ import annotations

import re

try:
    from num2words import num2words
    _HAS_N2W = True
except Exception:  # pragma: no cover
    _HAS_N2W = False


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Русское согласование: 1 рубль, 2 рубля, 5 рублей."""
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    r = n % 10
    if r == 1:
        return one
    if 2 <= r <= 4:
        return few
    return many


def _n2w(n) -> str:
    """Число → слова (русский). Без num2words — оставляем цифры."""
    if _HAS_N2W:
        try:
            return num2words(int(n), lang="ru")
        except Exception:
            return str(n)
    return str(n)


# Сокращения → полные слова. Неоднозначные (г. = год/город, ч. = час/что)
# намеренно не трогаем, чтобы не ошибаться.
_ABBR = {
    r"\bт\.\s*е\.": "то есть",
    r"\bт\.\s*д\.": "так далее",
    r"\bт\.\s*п\.": "тому подобное",
    r"\bт\.\s*к\.": "так как",
    r"\bи\s+пр\.": "и прочее",
    r"\bнапр\.": "например",
    r"\bтыс\.": "тысяч",
    r"\bмлн\.?": "миллионов",
    r"\bруб\.": "рублей",
    r"\bкоп\.": "копеек",
    r"\bмин\.": "минут",
    r"\bсек\.": "секунд",
}


def _money(m: re.Match) -> str:
    n = int(m.group(1))
    return f"{_n2w(n)} {_plural(n, 'рубль', 'рубля', 'рублей')}"


def _percent(m: re.Match) -> str:
    n = int(m.group(1))
    return f"{_n2w(n)} {_plural(n, 'процент', 'процента', 'процентов')}"


def _time(m: re.Match) -> str:
    h, mi = int(m.group(1)), int(m.group(2))
    hh = f"{_n2w(h)} {_plural(h, 'час', 'часа', 'часов')}"
    if mi == 0:
        return hh
    return f"{hh} {_n2w(mi)} {_plural(mi, 'минута', 'минуты', 'минут')}"


def _no(m: re.Match) -> str:
    n = int(m.group(1))
    return f"номер {_n2w(n)}"


def _merge_thousands(text: str) -> str:
    """«28 500» → «28500» (пробел/неразрывный пробел как разделитель тысяч)."""
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"(\d)[   ](\d{3})\b", r"\1\2", text)
    return text


def normalize_ru(text: str) -> str:
    """Переводит числа/деньги/время/сокращения в произносимые слова."""
    if not text:
        return text
    t = _merge_thousands(text)
    # № 1 → номер один
    t = re.sub(r"№\s*(\d+)", _no, t)
    # время ЧЧ:ММ
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", _time, t)
    # деньги: число + ₽ / руб / рублей
    t = re.sub(r"\b(\d+)\s*(?:₽|руб(?:\.|лей|ля|ль)?|р\.)", _money, t, flags=re.IGNORECASE)
    # проценты
    t = re.sub(r"\b(\d+)\s*%", _percent, t)
    # сокращения
    for pat, repl in _ABBR.items():
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    # оставшиеся числа → слова
    t = re.sub(r"\d+", lambda m: _n2w(m.group(0)), t)
    # лишние пробелы
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t
