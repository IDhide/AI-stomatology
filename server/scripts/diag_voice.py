#!/usr/bin/env python3
"""
Диагностика отпечатков голоса: проверяем, где ломается узнавание.

Шаги:
1. Пишем 3 дубля голоса с микрофона.
2. Считаем дистанции МЕЖДУ дублями (стабильность эмбеддинга на этом мике).
3. Смотрим, сколько речи остаётся после VAD-препроцессинга resemblyzer.
4. Сравниваем с отпечатком из базы (записан киоском ночью).
5. Свеже-записываем дубль 1 во временную базу и матчим дубли 2–3 —
   чистый прогон production-логики без старого отпечатка.

Запуск из корня: .venv/bin/python server/scripts/diag_voice.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from resemblyzer import preprocess_wav  # noqa: E402

from server.app.voice_id.embedder import SAMPLE_RATE, VoiceEmbedder, pcm16_to_float  # noqa: E402
from server.app.voice_id.store import VoiceMemoryStore  # noqa: E402

MIC = ":0"
TAKE_SECONDS = 6.0


def record(seconds: float, out: Path) -> bytes:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "avfoundation", "-i", MIC,
         "-t", str(seconds), "-ar", str(SAMPLE_RATE), "-ac", "1",
         "-f", "s16le", str(out)],
        check=True,
    )
    return out.read_bytes()


def dist(a, b) -> float:
    return 1.0 - float(np.dot(np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)))


def audio_stats(audio: bytes) -> str:
    x = pcm16_to_float(audio)
    rms = float(np.sqrt(np.mean(x**2)))
    voiced = preprocess_wav(x, source_sr=SAMPLE_RATE)
    return f"RMS={rms:.4f}, после VAD осталось {voiced.size / SAMPLE_RATE:.1f}с речи из {len(x) / SAMPLE_RATE:.1f}с"


def main() -> int:
    embedder = VoiceEmbedder()
    if not embedder.enabled:
        print("❌ Resemblyzer не загрузился")
        return 1

    store = VoiceMemoryStore("data/voice_memory.sqlite3")
    rows = store._all_rows()

    embs: list[list[float]] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i in range(1, 4):
            print(f"\n🎙 Дубль {i}/3 — запись {TAKE_SECONDS:.0f}с начнётся через 3с. Говори свободно.")
            time.sleep(3)
            print("   🔴 ГОВОРИ!")
            audio = record(TAKE_SECONDS, tmp / f"take{i}.pcm")
            print(f"   ⏺  Записано. {audio_stats(audio)}")
            emb = embedder.embed(audio)
            if not emb:
                print("   ⚠️  Эмбеддинг не построился")
                continue
            embs.append(emb)

    if len(embs) < 2:
        print("Мало дублей для анализа")
        return 1

    print("\n── 1. Стабильность: дистанции между СВОИМИ дублями (один голос, один мик)")
    for i in range(len(embs)):
        for j in range(i + 1, len(embs)):
            print(f"   дубль{i + 1} ↔ дубль{j + 1}: {dist(embs[i], embs[j]):.3f}")

    print("\n── 2. Старый отпечаток из базы (записан киоском 10.08 в 02:20)")
    for row_id, name, phone, stored in rows:
        for i, emb in enumerate(embs, 1):
            print(f"   дубль{i} ↔ база «{name}»: {dist(emb, stored.tolist()):.3f}")

    print("\n── 3. Чистый прогон: дубль1 записываем как нового пациента, матчим 2–3")
    with tempfile.TemporaryDirectory() as td2:
        fresh = VoiceMemoryStore(str(Path(td2) / "fresh.sqlite3"))
        fresh.enroll(embs[0], "Тестовый", None)
        for i, emb in enumerate(embs[1:], 2):
            m = fresh.match(emb, threshold=0.15, weak_threshold=0.25)
            print(f"   дубль{i}: distance={m.distance:.3f} confidence={m.confidence} is_new={m.is_new}")

    print("\nГотово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
