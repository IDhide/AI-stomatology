"""
tests/test_dental.py
Проверка dental-модулей: intents, triage.
"""
import pytest
from src.dental.intents import classify_intent, Intent
from src.dental.triage import triage, Urgency, TriageResult


def test_classify_intent_appointment():
    result = classify_intent("Хочу записаться к врачу")
    assert result is not None
    assert result.intent == Intent.BOOK


def test_classify_intent_greeting():
    result = classify_intent("Здравствуйте")
    assert result.intent == Intent.GREETING


def test_classify_intent_empty():
    """Пустая строка не падает."""
    result = classify_intent("")
    assert result is not None


def test_triage_urgent_pain():
    """Острая боль → urgent."""
    result = triage("У меня сильно болит зуб, не могу терпеть")
    assert isinstance(result, TriageResult)
    assert result.urgency == Urgency.URGENT
    assert result.alert is True


def test_triage_planned():
    """Плановая запись → не urgent."""
    result = triage("Хочу записаться на профилактический осмотр")
    assert isinstance(result, TriageResult)
    assert result.urgency != Urgency.URGENT


def test_triage_cosmetic():
    """Эстетический запрос (отбеливание) → cosmetic."""
    result = triage("Хочу сделать отбеливание зубов")
    assert isinstance(result, TriageResult)
    assert result.urgency == Urgency.COSMETIC


def test_triage_returns_triageresult():
    """triage всегда возвращает TriageResult."""
    result = triage("просто интересуюсь")
    assert isinstance(result, TriageResult)
    assert result.urgency is not None
    assert result.priority is not None
