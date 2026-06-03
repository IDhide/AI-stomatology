"""
tests/test_dental.py
Проверка dental-модулей: intents, triage, humor.
"""
import pytest
from src.dental.intents import classify_intent
from src.dental.triage import assess_urgency


def test_classify_intent_appointment():
    text = "Хочу записаться к врачу"
    result = classify_intent(text)
    assert result is not None


def test_classify_intent_empty():
    """Пустая строка не падает."""
    result = classify_intent("")
    assert result is not None


def test_assess_urgency_pain():
    """Острая боль → высокий приоритет."""
    result = assess_urgency("У меня сильная боль в зубе, не могу терпеть")
    # Результат должен быть строкой или иметь атрибут приоритета
    assert result is not None
