"""
Загрузка персоны ассистента (Оливия) из config/prompts.yaml.

Переиспользуем уже написанный заказчиком системный промпт и готовые
шаблоны приветствий/прощаний — не дублируем.
"""
from __future__ import annotations

import pathlib
import random

import yaml
from loguru import logger

_DEFAULT_SYSTEM = (
    "Ты — Оливия, администратор стоматологической клиники. Говоришь по-русски, "
    "тёпло, на «вы», короткими фразами без markdown. Каждую реплику мягко "
    "заканчивай вопросом и веди пациента к записи на бесплатную консультацию."
)


class Persona:
    def __init__(self, prompts_path: str = "config/prompts.yaml"):
        self.prompts = self._load(pathlib.Path(prompts_path))
        self.system = (self.prompts.get("system") or _DEFAULT_SYSTEM).strip()

    def _load(self, path: pathlib.Path) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"prompts.yaml не найден ({path}) — использую дефолт")
            return {}

    def greeting(self, *, returning: bool = False, name: str | None = None) -> str:
        if returning:
            text = (self.prompts.get("greeting_returning")
                    or "Рада снова вас слышать. Чем могу помочь?").strip()
        else:
            # случайный вариант — приветствие не звучит однотипно
            variants = self.prompts.get("greetings") or []
            if variants:
                text = random.choice(variants).strip()
            else:
                text = (self.prompts.get("greeting")
                        or "Здравствуйте! Чем могу помочь?").strip()
        if name:
            # «Добрый день, Анна! ...» — персональное обращение из ТЗ
            text = f"{name}, {text[0].lower()}{text[1:]}" if text else text
        return text

    def farewell(self) -> str:
        return (self.prompts.get("farewell") or "До свидания, всего доброго!").strip()
