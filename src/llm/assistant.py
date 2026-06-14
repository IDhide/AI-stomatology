"""
assistant.py
============
LLM-ассистент для стоматологического ресепшена.

Сценарий обработки одной реплики:
1. STT уже отдал текст пациента.
2. classify_intent() — лёгкая русская классификация.
3. lookup_faq() — если совпало, отвечаем без LLM (быстро и без галлюцинаций).
4. triage() — острая боль / детский / плановый / косметика → влияет на промпт.
5. Если случай простой (приветствие/прощание/благодарность) — отдаём
   готовый шаблон + опционально шутку.
6. Иначе — Ollama с system из prompts.yaml + tool-calling.
7. ToolDispatcher вызывает DIKIDI/KB, результат идёт второй итерацией в LLM
   («ты получил такие данные — теперь ответь пациенту»).
8. Финальный текст уходит в TTS через нормализатор.

История разговора: последние 8 пар реплик.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import random
from dataclasses import dataclass
from typing import Any

import requests
import yaml
from loguru import logger

from ..dental.faq import lookup_faq
from ..dental.humor import maybe_joke
from ..dental.intents import Intent, classify_intent
from ..dental.triage import Urgency, triage
from .tools import ToolDispatcher, extract_tool_calls


@dataclass
class AssistantConfig:
    base_url: str
    model: str
    fallback_model: str = "qwen2.5:7b-instruct-q4_K_M"
    temperature: float = 0.4
    num_ctx: int = 4096
    max_tokens: int = 512
    prompts_path: str = "config/prompts.yaml"
    enable_humor: bool = True
    humor_min_turns: int = 3


class LLMAssistant:
    """Главный мозг ассистента."""

    def __init__(self, config: AssistantConfig | Any, dikidi_client):
        # поддерживаем как датакласс, так и pydantic-конфиг
        self.cfg = config
        self.base_url = getattr(config, "base_url", "http://localhost:11434")
        self.model = getattr(config, "model", "smile-ru")
        self.fallback_model = getattr(config, "fallback_model", "qwen2.5:7b-instruct-q4_K_M")
        self.temperature = float(getattr(config, "temperature", 0.4))
        self.num_ctx = int(getattr(config, "num_ctx", 4096))
        self.max_tokens = int(getattr(config, "max_tokens", 512))
        self.enable_humor = bool(getattr(config, "enable_humor", True))
        self.humor_min_turns = int(getattr(config, "humor_min_turns", 3))

        prompts_path = pathlib.Path(getattr(config, "prompts_path", "config/prompts.yaml"))
        self.prompts = self._load_prompts(prompts_path)
        self.system_prompt = self._build_system_prompt()

        self.history: list[dict[str, str]] = []
        self.user_history: list[str] = []   # для humor-фильтра
        self._turns_since_joke = 999
        self._rng = random.Random()

        self.dispatcher = ToolDispatcher(dikidi_client)
        self._check_connection()
        logger.success(f"LLMAssistant готов: model={self.model}")

    # ------------------------------------------------------------------
    def _load_prompts(self, path: pathlib.Path) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"prompts.yaml не найден: {path}. Использую дефолты.")
            return {}

    def _build_system_prompt(self) -> str:
        # Только персона. Блок инструментов больше НЕ добавляем: Оливия сама не
        # записывает (направляет к администратору), а огромный список tool-схем
        # раздувал промпт за пределы контекста — он обрезался, и Оливия теряла
        # роль (markdown, бессвязные ответы). Короткий промпт = роль на месте + быстро.
        return self.prompts.get(
            "system",
            "Ты — Оливия, администратор стоматологической клиники, говоришь по-русски.",
        ).strip()

    # ------------------------------------------------------------------
    def _check_connection(self) -> None:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            tags = r.json().get("models", [])
            names = {t.get("name", "") for t in tags}
            if self.model not in names and not any(n.startswith(self.model + ":") for n in names):
                logger.warning(
                    f"Модель '{self.model}' не найдена в Ollama. "
                    f"Доступны: {sorted(names)[:5]}. Падаю на {self.fallback_model}."
                )
                self.model = self.fallback_model
        except Exception as e:
            logger.error(f"Ollama недоступна: {e}")
            raise

    # ------------------------------------------------------------------
    async def get_response(self, user_text: str, *_compat) -> str:
        """
        Главная точка входа. _compat — позволяет вызвать со старой сигнатурой
        get_response(text, dikidi_client) без падения.
        """
        if not user_text or not user_text.strip():
            return self.prompts.get("fallback", "Простите, я вас не расслышала. Повторите, пожалуйста.")

        # 1. Лёгкая классификация
        intent_match = classify_intent(user_text)
        intent = intent_match.intent
        tri = triage(user_text)
        logger.info(f"intent={intent.value} conf={intent_match.confidence:.2f} | urgency={tri.urgency.value} | spec={tri.specialty}")

        # 2. FAQ fast-path
        faq_answer = lookup_faq(user_text)
        if faq_answer:
            self._push(user_text, faq_answer)
            return self._with_optional_joke(faq_answer, intent, tri)

        # 3. Готовые шаблоны для приветствия/прощания/благодарности
        canned = self._canned_reply(intent, tri)
        if canned:
            self._push(user_text, canned)
            return self._with_optional_joke(canned, intent, tri)

        # 4. Полноценный вызов LLM с tool-calling
        try:
            text = await self._llm_turn(user_text, tri)
        except Exception:
            logger.exception("LLM error")
            text = self.prompts.get(
                "fallback_long",
                "Прошу прощения, мне нужна минутка. Я уточню и вернусь к вам.",
            )

        if text.strip().upper().startswith("ИГНОР"):
            return "ИГНОР"

        self._push(user_text, text)
        return self._with_optional_joke(text, intent, tri)

    # ------------------------------------------------------------------
    def _canned_reply(self, intent: Intent, tri) -> str | None:
        if intent == Intent.GREETING:
            key = "greeting_returning" if self.history else "greeting"
            return self.prompts.get(key) or "Здравствуйте! Чем могу помочь?"
        if intent == Intent.FAREWELL:
            key = "farewell_after_pain" if tri.urgency == Urgency.URGENT else "farewell"
            return self.prompts.get(key) or "До свидания, всего доброго."
        if intent == Intent.THANKS:
            return "Пожалуйста, всегда рады помочь."
        if intent == Intent.URGENT_PAIN:
            return self.prompts.get(
                "acknowledge_urgent",
                "Понимаю, ситуация срочная. Сейчас найду ближайшее окно и предупрежу врача.",
            )
        if intent == Intent.PEDIATRIC and tri.urgency != Urgency.URGENT:
            return self.prompts.get(
                "acknowledge_pediatric",
                "Запишу к детскому стоматологу. Подскажите возраст ребёнка и удобное время.",
            )
        return None

    # ------------------------------------------------------------------
    async def _llm_turn(self, user_text: str, tri) -> str:
        """
        Двухитеративный цикл с tool-calling:
        — генерируем; если есть tool-вызовы, исполняем и просим LLM продолжить.
        """
        # подмешиваем триаж как short hint
        triage_hint = (
            f"[служебная_подсказка: urgency={tri.urgency.value}, "
            f"specialty={tri.specialty}, priority={tri.priority}]"
        )

        messages = self._build_messages(user_text + "\n" + triage_hint)

        for _ in range(2):  # максимум 2 итерации (chat → tool → chat)
            raw = await asyncio.to_thread(self._ollama_chat, messages)
            speech, calls = extract_tool_calls(raw)

            if not calls:
                return speech or raw.strip()

            # исполняем tools последовательно
            tool_results = []
            for call in calls:
                res = await self.dispatcher.call(call)
                tool_results.append({"call": call, "result": res})

            # подсовываем результат в контекст следующей итерации
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": "Результаты инструментов: " + json.dumps(tool_results, ensure_ascii=False) +
                           "\nТеперь ответь пациенту коротко, голосом, без markdown."
            })

        # если 2 итерации не хватило — отдаём что есть
        return speech or "Минутку, я уточню детали."

    # ------------------------------------------------------------------
    def _build_messages(self, user_text: str) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": self.system_prompt}]
        # последние 4 пары — для голосового сценария большего не надо
        # (меньше контекста → быстрее ответ на CPU)
        for pair in self.history[-4:]:
            msgs.append({"role": "user", "content": pair["user"]})
            msgs.append({"role": "assistant", "content": pair["assistant"]})
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def _ollama_chat(self, messages: list[dict]) -> str:
        r = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                # держим модель в памяти между репликами — иначе на CPU
                # каждый ответ платит за повторную загрузку весов
                "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
                "options": {
                    "temperature": self.temperature,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.max_tokens,
                },
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return (data.get("message", {}) or {}).get("content", "").strip()

    # ------------------------------------------------------------------
    def _with_optional_joke(self, text: str, intent: Intent, tri) -> str:
        if not self.enable_humor:
            return text
        joke = maybe_joke(
            intent=intent,
            triage_result=tri,
            user_history=self.user_history[-3:],
            last_joke_turns_ago=self._turns_since_joke,
            rng=self._rng,
        )
        if joke:
            self._turns_since_joke = 0
            return f"{text} {joke}"
        self._turns_since_joke += 1
        return text

    # ------------------------------------------------------------------
    def _push(self, user_text: str, assistant_text: str) -> None:
        self.history.append({"user": user_text, "assistant": assistant_text})
        self.user_history.append(user_text)
        # ограничиваем
        self.history = self.history[-16:]
        self.user_history = self.user_history[-16:]

    def reset_conversation(self) -> None:
        self.history.clear()
        self.user_history.clear()
        self._turns_since_joke = 999
        logger.info("История диалога очищена")
