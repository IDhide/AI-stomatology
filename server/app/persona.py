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

    def _pick(self, list_key: str, key: str, default: str) -> str:
        """Случайный вариант из списка; если списка нет — одиночный шаблон."""
        variants = self.prompts.get(list_key) or []
        if variants:
            return random.choice(variants).strip()
        return (self.prompts.get(key) or default).strip()

    @staticmethod
    def _apply_daypart(text: str, hour: int) -> str:
        """«Добрый день» подгоняем под реальное время суток — иначе в два
        часа ночи киоск говорит «добрый день» (27.08, заметил заказчик)."""
        if "Добрый день" not in text:
            return text
        if 5 <= hour < 12:
            return text.replace("Добрый день", "Доброе утро")
        if 12 <= hour < 18:
            return text
        if 18 <= hour < 23:
            return text.replace("Добрый день", "Добрый вечер")
        return text.replace("Добрый день", "Здравствуйте")

    def greeting(self, *, returning: bool = False, name: str | None = None,
                 hour: int | None = None) -> str:
        if returning:
            text = self._pick("greetings_returning", "greeting_returning",
                              "Рада снова вас слышать. Чем могу помочь?")
        else:
            # случайный вариант — приветствие не звучит однотипно
            text = self._pick("greetings", "greeting",
                              "Здравствуйте! Чем могу помочь?")
        if hour is not None:
            text = self._apply_daypart(text, hour)
        if name:
            # «Добрый день, Анна! ...» — персональное обращение из ТЗ
            text = f"{name}, {text[0].lower()}{text[1:]}" if text else text
        return text

    def farewell(self) -> str:
        # случайный вариант — прощание не штампуется одной фразой
        return self._pick("farewells", "farewell", "До свидания, всего доброго!")

    def fallback(self) -> str:
        # «не расслышала» — тоже вариативно, иначе при плохой слышимости
        # пациент слышит одну и ту же фразу по кругу
        return self._pick("fallbacks", "fallback",
                          "Простите, я вас не расслышала. Повторите, пожалуйста?")
