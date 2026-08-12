#!/usr/bin/env python3
"""
Перезаписывает голосовой отпечаток пациента чистой записью с микрофона.

Зачем: отпечаток, записанный киоском 10.08, оказался мусором (дистанция
до живого голоса владельца 0.58–0.70, тогда как дубли одного голоса —
0.14–0.18). Этот скрипт пишет 3 дубля, усредняет эмбеддинги и заменяет
строку в базе; затем контрольный дубль — проверка, что узнавание работает.

Запуск из корня репозитория:
    .venv/bin/python server/scripts/re_enroll_voice.py "Илья"
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.app.voice_id.embedder import SAMPLE_RATE, VoiceEmbedder  # noqa: E402
from server.app.voice_id.store import VoiceMemoryStore  # noqa: E402

MIC = ":0"
TAKE_SECONDS = 6.0
TAKES = 3
DB_PATH = "data/voice_memory.sqlite3"
THRESHOLD = 0.15
WEAK_THRESHOLD = 0.25


def record(seconds: float, out: Path) -> bytes:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "avfoundation", "-i", MIC,
         "-t", str(seconds), "-ar", str(SAMPLE_RATE), "-ac", "1",
         "-f", "s16le", str(out)],
        check=True,
    )
    return out.read_bytes()


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "Илья"
    embedder = VoiceEmbedder()
    if not embedder.enabled:
        print("❌ Resemblyzer не загрузился")
        return 1
    store = VoiceMemoryStore(DB_PATH)

    embs: list[list[float]] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i in range(1, TAKES + 1):
            print(f"\n🎙 Дубль {i}/{TAKES}: говори свободно ~6 секунд (как у киоска).")
            time.sleep(3)
            print("   🔴 ГОВОРИ!")
            audio = record(TAKE_SECONDS, tmp / f"take{i}.pcm")
            emb = embedder.embed(audio)
            if emb:
                embs.append(emb)
                print("   ⏺  Принято.")
            else:
                print("   ⚠️  Мало чистой речи — дубль пропущен.")

        if len(embs) < 2:
            print("❌ Меньше двух удачных дублей — отпечаток не обновляю.")
            return 1

        mean = np.mean(np.asarray(embs, dtype=np.float32), axis=0)
        mean = (mean / np.linalg.norm(mean)).astype(np.float32)

        # удаляем старые строки с этим именем и пишем свежую
        with store._connect() as conn:
            cur = conn.execute("delete from voice_patients where name = ?", (name,))
            if cur.rowcount:
                print(f"\n🗑  Удалены старые отпечатки «{name}»: {cur.rowcount}")
        new_id = store.enroll(mean.tolist(), name, "+7 918 963-18-88")
        print(f"✅ Свежий отпечаток «{name}» записан, id={new_id} (усреднение {len(embs)} дублей)")

        # контрольный дубль
        print("\n🎙 Контрольный дубль: скажи что-нибудь ещё раз (другие слова).")
        time.sleep(3)
        print("   🔴 ГОВОРИ!")
        check_audio = record(TAKE_SECONDS, tmp / "check.pcm")
        check_emb = embedder.embed(check_audio)
        if not check_emb:
            print("⚠️  Контрольный дубль не прошёл по качеству — повтори скрипт.")
            return 1
        match = store.match(check_emb, THRESHOLD, weak_threshold=WEAK_THRESHOLD)
        print(f"\n📊 distance={match.distance:.3f} confidence={match.confidence} is_new={match.is_new}")
        if not match.is_new:
            print(f"✅ Узнала: «{match.name}» — фича работает.")
            return 0
        print("❌ Не узнала даже после переобучения — нужен разбор дальше.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
