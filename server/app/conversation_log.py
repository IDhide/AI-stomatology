"""
Логирование разговоров для анализа.

При первом запуске создаётся папка data/conversations/ (путь настраивается
через CONVERSATIONS_DIR). Каждый диалог — отдельная пара файлов в подпапке
за день:

    data/conversations/2026-07-16/
        103015_a1b2.jsonl   — машиночитаемый лог (для скриптов анализа)
        103015_a1b2.txt     — человекочитаемая расшифровка (открыл и прочёл)

События в JSONL: start / message (role, text) / end (reason).
Причины завершения: assistant_closed (Оливия попрощалась), patient_left
(ушёл из кадра / кнопка), silence (10с тишины), disconnect (обрыв связи).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from loguru import logger


class ConversationLog:
    def __init__(self, base_dir: str = "data/conversations"):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self._file: Path | None = None
        self._messages: list[dict] = []
        self._started_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self._file is not None

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Открывает новый диалог (закрыв предыдущий, если тот завис)."""
        if self.active:
            self.end("interrupted_by_new")
        now = datetime.now()
        day_dir = self.base / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        name = f"{now.strftime('%H%M%S')}_{uuid.uuid4().hex[:4]}"
        self._file = day_dir / f"{name}.jsonl"
        self._messages = []
        self._started_at = now
        self._write({"event": "start", "ts": now.isoformat(timespec="seconds")})
        logger.info(f"📁 Диалог пишется в {self._file}")

    def log(self, role: str, text: str) -> None:
        """role: 'user' | 'assistant'."""
        if not self.active or not text:
            return
        ts = datetime.now().isoformat(timespec="seconds")
        self._messages.append({"ts": ts, "role": role, "text": text})
        self._write({"event": "message", "ts": ts, "role": role, "text": text})

    def end(self, reason: str) -> None:
        if not self.active:
            return
        now = datetime.now()
        duration = (now - self._started_at).total_seconds() if self._started_at else 0
        self._write({
            "event": "end",
            "ts": now.isoformat(timespec="seconds"),
            "reason": reason,
            "duration_sec": round(duration),
            "turns": len(self._messages),
        })
        self._write_transcript(reason, duration)
        logger.info(f"📁 Диалог закрыт ({reason}, {len(self._messages)} реплик)")
        self._file = None
        self._messages = []
        self._started_at = None

    # ------------------------------------------------------------------
    def _write(self, obj: dict) -> None:
        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Не смог записать лог диалога: {e}")

    def _write_transcript(self, reason: str, duration: float) -> None:
        """Рядом с .jsonl кладём читаемую расшифровку .txt."""
        try:
            txt = self._file.with_suffix(".txt")
            lines = [
                f"Диалог {self._started_at:%d.%m.%Y %H:%M:%S}",
                f"Длительность: {round(duration)} сек · Реплик: {len(self._messages)}"
                f" · Завершение: {reason}",
                "─" * 60,
            ]
            for m in self._messages:
                who = "Пациент" if m["role"] == "user" else "Оливия "
                lines.append(f"[{m['ts'][11:]}] {who}: {m['text']}")
            txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            logger.error(f"Не смог записать расшифровку: {e}")
