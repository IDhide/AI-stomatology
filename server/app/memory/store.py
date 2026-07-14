"""
Память ассистента поверх Supabase (Postgres + pgvector).

Отвечает на два вопроса из ТЗ:
  1. «Мы этого человека уже видели?»  → match_face()
  2. «Здоровались ли мы с ним недавно?» → should_greet()

Если Supabase не сконфигурирован — работает как no-op заглушка (in-memory),
чтобы локальная разработка не требовала базы.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from loguru import logger

try:
    from supabase import Client, create_client

    HAVE_SUPABASE = True
except ImportError:  # pragma: no cover
    HAVE_SUPABASE = False
    Client = object  # type: ignore


@dataclass
class PatientMatch:
    patient_id: str | None
    name: str | None
    distance: float
    is_new: bool


class MemoryStore:
    def __init__(self, url: str = "", key: str = "", match_threshold: float = 0.42):
        self.match_threshold = match_threshold
        self.client: Client | None = None
        if url and key and HAVE_SUPABASE:
            self.client = create_client(url, key)
            logger.info("MemoryStore: Supabase подключён")
        else:
            logger.warning("MemoryStore: заглушка (Supabase не настроен)")

    # ── лица ─────────────────────────────────────────────────────────
    def match_face(self, embedding: list[float]) -> PatientMatch:
        """Ищет ближайшее лицо; если далеко — считает нового пациента."""
        if not self.client:
            return PatientMatch(None, None, 2.0, is_new=True)
        try:
            res = self.client.rpc(
                "match_patient", {"query_embedding": embedding}
            ).execute()
            rows = res.data or []
        except Exception as e:
            logger.error(f"match_patient RPC: {e}")
            return PatientMatch(None, None, 2.0, is_new=True)

        if not rows:
            return PatientMatch(None, None, 2.0, is_new=True)

        row = rows[0]
        distance = float(row.get("distance", 2.0))
        if distance <= self.match_threshold:
            return PatientMatch(row["id"], row.get("name"), distance, is_new=False)
        return PatientMatch(None, None, distance, is_new=True)

    def create_patient(self, embedding: list[float], name: str | None = None) -> str | None:
        if not self.client:
            return None
        try:
            res = (
                self.client.table("patients")
                .insert({"embedding": embedding, "name": name,
                         "last_seen_at": _now_iso()})
                .execute()
            )
            return (res.data or [{}])[0].get("id")
        except Exception as e:
            logger.error(f"create_patient: {e}")
            return None

    # ── сессии / приветствие ─────────────────────────────────────────
    def should_greet(self, patient_id: str | None, regreet_minutes: int) -> bool:
        """True, если давно (или ни разу) не здоровались с этим пациентом."""
        if not self.client or not patient_id:
            return True
        try:
            res = (
                self.client.table("sessions")
                .select("started_at, greeted")
                .eq("patient_id", patient_id)
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = res.data or []
        except Exception as e:
            logger.error(f"should_greet: {e}")
            return True

        if not rows or not rows[0].get("greeted"):
            return True
        last = _parse(rows[0]["started_at"])
        return datetime.now(timezone.utc) - last > timedelta(minutes=regreet_minutes)

    def touch_seen(self, patient_id: str | None) -> None:
        if not self.client or not patient_id:
            return
        try:
            self.client.table("patients").update(
                {"last_seen_at": _now_iso()}
            ).eq("id", patient_id).execute()
        except Exception as e:
            logger.error(f"touch_seen: {e}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
