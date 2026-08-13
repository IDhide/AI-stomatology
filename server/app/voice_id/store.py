"""
Локальная память голосовых «отпечатков» — без Supabase.

По архитектуре повторяет server/app/memory/store.py (написан для лиц через
Supabase + pgvector), но хранит данные в обычном sqlite-файле на диске:
для клиники с реалистичным потоком пациентов (сотни, не миллионы записей)
это на порядки проще внешней базы и не требует внешнего сервиса — весь
поиск делается перебором через numpy, без ANN-индекса.

Файл с эмбеддингами — биометрические персональные данные (см. план,
раздел «Приватность») — в .gitignore, как и data/conversations,
data/bookings.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from loguru import logger


@dataclass
class VoiceMatch:
    patient_id: int | None
    name: str | None
    phone: str | None
    distance: float
    is_new: bool
    confidence: str = "none"  # "high" | "low" | "none"

    @property
    def similarity(self) -> float:
        """Косинусное сходство: 1.0 — идентично, 0.0 — ортогонально."""
        return max(0.0, 1.0 - float(self.distance))


class VoiceMemoryStore:
    def __init__(self, db_path: str = "data/voice_memory.sqlite3"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists voice_patients (
                    id integer primary key autoincrement,
                    name text,
                    phone text,
                    embedding_json text not null,
                    created_at text not null,
                    last_seen_at text not null
                )
                """
            )

    # ── поиск ────────────────────────────────────────────────────────
    def match(
        self,
        embedding: list[float],
        threshold: float,
        weak_threshold: float | None = None,
    ) -> VoiceMatch:
        """
        Ищет ближайший сохранённый голос. Дистанция — косинусная
        (0 — идентично, 2 — противоположно), эмбеддинги Resemblyzer уже
        L2-нормированы, поэтому distance = 1 - dot(a, b).

        Двухуровневая логика:
        - distance <= threshold → confidence="high" (например, >= 85% сходство)
        - threshold < distance <= weak_threshold → confidence="low" (75–85%)
        - distance > weak_threshold → is_new=True

        Если weak_threshold не задан, используется только threshold:
        всё, что дальше threshold — новый пациент.
        """
        query = np.asarray(embedding, dtype=np.float32)
        rows = self._all_rows()
        if not rows:
            return VoiceMatch(None, None, None, distance=2.0, is_new=True, confidence="none")

        best = None
        best_distance = 2.0
        for row_id, name, phone, emb in rows:
            distance = 1.0 - float(np.dot(query, emb))
            if distance < best_distance:
                best_distance = distance
                best = (row_id, name, phone)

        if best is None:
            return VoiceMatch(None, None, None, distance=best_distance, is_new=True, confidence="none")

        weak = weak_threshold if weak_threshold is not None else threshold
        if best_distance > weak:
            return VoiceMatch(None, None, None, distance=best_distance, is_new=True, confidence="none")

        confidence = "high" if best_distance <= threshold else "low"
        row_id, name, phone = best
        return VoiceMatch(row_id, name, phone, distance=best_distance, is_new=False, confidence=confidence)

    def _all_rows(self) -> list[tuple[int, str | None, str | None, np.ndarray]]:
        try:
            with self._connect() as conn:
                cur = conn.execute("select id, name, phone, embedding_json from voice_patients")
                return [
                    (row_id, name, phone, np.asarray(json.loads(emb_json), dtype=np.float32))
                    for row_id, name, phone, emb_json in cur.fetchall()
                ]
        except Exception as e:
            logger.error(f"VoiceMemoryStore: не смог прочитать базу: {e}")
            return []

    # ── запись ───────────────────────────────────────────────────────
    # Если новый отпечаток ближе этого к уже сохранённому — это почти
    # наверняка тот же человек, которого просто не узнали в этот визит
    # (хрипотца, шум, мало речи). Чужие голоса лежат дальше (~0.48+).
    # Вместо дубля в базе — подмешиваем отпечаток в существующий профиль.
    DEDUP_DISTANCE = 0.45

    def enroll(self, embedding: list[float], name: str, phone: str | None = None) -> int | None:
        rows = self._all_rows()
        if rows:
            query = np.asarray(embedding, dtype=np.float32)
            best_id, best_dist = None, 2.0
            for row_id, _name, _phone, emb in rows:
                d = 1.0 - float(np.dot(query, emb))
                if d < best_dist:
                    best_id, best_dist = row_id, d
            if best_id is not None and best_dist <= self.DEDUP_DISTANCE:
                # дубль того же голоса: сливаем, а не плодим профили
                self.update_embedding(best_id, embedding)
                if phone:
                    self._update_phone_if_empty(best_id, phone)
                logger.info(
                    f"🎙️ Отпечаток похож на существующий профиль id={best_id} "
                    f"(distance={best_dist:.3f}) — объединил, дубль не создаю"
                )
                return best_id
        now = _now_iso()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    insert into voice_patients (name, phone, embedding_json, created_at, last_seen_at)
                    values (?, ?, ?, ?, ?)
                    """,
                    (name, phone, json.dumps(embedding), now, now),
                )
                logger.info(f"🎙️ Новый голосовой отпечаток: {name}")
                return cur.lastrowid
        except Exception as e:
            logger.error(f"VoiceMemoryStore.enroll: {e}")
            return None

    def _update_phone_if_empty(self, patient_id: int, phone: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "update voice_patients set phone = ? where id = ? and (phone is null or phone = '')",
                    (phone, patient_id),
                )
        except Exception as e:
            logger.error(f"VoiceMemoryStore._update_phone_if_empty: {e}")

    def touch_seen(self, patient_id: int) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "update voice_patients set last_seen_at = ? where id = ?",
                    (_now_iso(), patient_id),
                )
        except Exception as e:
            logger.error(f"VoiceMemoryStore.touch_seen: {e}")

    def update_embedding(self, patient_id: int, embedding: list[float], new_weight: float = 0.3) -> None:
        """
        Подмешивает свежий отпечаток к сохранённому (взвешенное среднее +
        ренормализация). Вызывается при уверенном совпадении: голос человека
        и акустика киоска «плывут», так база адаптируется сама.
        new_weight — вклад нового отпечатка (0.3 = плавная адаптация).
        """
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "select embedding_json from voice_patients where id = ?", (patient_id,)
                )
                row = cur.fetchone()
                if not row:
                    return
                old = np.asarray(json.loads(row[0]), dtype=np.float32)
                new = np.asarray(embedding, dtype=np.float32)
                mixed = (1.0 - new_weight) * old + new_weight * new
                norm = float(np.linalg.norm(mixed))
                if norm > 0:
                    mixed = mixed / norm
                conn.execute(
                    "update voice_patients set embedding_json = ?, last_seen_at = ? where id = ?",
                    (json.dumps(mixed.tolist()), _now_iso(), patient_id),
                )
        except Exception as e:
            logger.error(f"VoiceMemoryStore.update_embedding: {e}")

    # ── промпт ───────────────────────────────────────────────────────
    @staticmethod
    def format_for_prompt(match: VoiceMatch) -> str | None:
        """
        Блок для system-промпта, ТОЛЬКО когда есть похожий на кого-то
        голос. Уровень уверенности определяется порогами match():
        - confidence="high" (>= 85%): Оливия встречает по имени.
        - confidence="low" (75–85%): только мягко переспрашивает имя.
        """
        if match.is_new or not match.name:
            return None
        phone_line = f" Телефон в системе: {match.phone}." if match.phone else ""
        similarity_pct = int(round(match.similarity * 100))
        if match.confidence == "high":
            return (
                f"РАСПОЗНАВАНИЕ ПО ГОЛОСУ: высокая уверенность {similarity_pct}%. "
                f"Это {match.name}, уже был(а) в клинике.{phone_line} "
                f"В самом начале ответа скажи тёплую фразу: "
                f"'Приятно вас снова видеть, {match.name}!' — а потом ответь на вопрос."
            )
        return (
            f"РАСПОЗНАВАНИЕ ПО ГОЛОСУ: возможное совпадение {similarity_pct}%, "
            f"похоже (не наверняка), что это {match.name}.{phone_line} Это ДОГАДКА, "
            "не факт — см. правила в разделе «Распознавание по голосу» промпта."
        )


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
