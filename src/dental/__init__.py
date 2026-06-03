"""Стоматологический «мозг» ассистента: знания, триаж, интенты, юмор."""
from .knowledge_base import KB, find_procedure, list_procedures
from .triage import triage, Urgency
from .intents import classify_intent, Intent
from .humor import maybe_joke, JOKE_CATALOG
from .faq import FAQ, lookup_faq

__all__ = [
    "KB", "find_procedure", "list_procedures",
    "triage", "Urgency",
    "classify_intent", "Intent",
    "maybe_joke", "JOKE_CATALOG",
    "FAQ", "lookup_faq",
]
