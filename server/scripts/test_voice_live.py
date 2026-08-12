#!/usr/bin/env python3
"""
Живой тест узнавания голоса: записывает голос с микрофона и сверяет
с отпечатками в базе (data/voice_memory.sqlite3).

Показывает дистанции до каждого сохранённого голоса и вердикт при
текущих порогах (VOICE_MATCH_THRESHOLD / VOICE_MATCH_WEAK_THRESHOLD).
Для контраста добавляет синтетический «чужой» голос через `say`.

Запуск из корня репозитория:
    .venv/bin/python server/scripts/test_voice_live.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.app.voice_id.embedder import VoiceEmbedder, pcm16_to_float  # noqa: E402
from server.app.voice_id.store import VoiceMemoryStore  # noqa: E402

# Текущие пороги из server/.env (на момент правок)
THRESHOLD = 0.15
WEAK_THRESHOLD = 0.25

MIC = ":0"  # avfoundation: [0] MacBook Pro Microphone
SAMPLE_RATE = 16000


def record_pcm16(seconds: float, out_path: Path) -> bytes:
    """Пишет микрофон через ffmpeg → PCM16 mono 16 kHz."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "avfoundation", "-i", MIC,
            "-t", str(seconds),
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-f", "s16le", str(out_path),
        ],
        check=True,
    )
    return out_path.read_bytes()


def say_pcm16(text: str, voice: str, tmp: Path) -> bytes:
    """Синтез чужого голоса macOS `say` → PCM16 mono 16 kHz."""
    aiff = tmp / f"{voice}.aiff"
    pcm = tmp / f"{voice}.pcm"
    subprocess.run(["say", text, "-v", voice, "-o", str(aiff)], check=True, capture_output=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(aiff), "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-f", "s16le", str(pcm),
        ],
        check=True,
    )
    return pcm.read_bytes()


def distance(a: list[float], b: list[float]) -> float:
    """Косинусная дистанция, как в VoiceMemoryStore.match()."""
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    return 1.0 - float(np.dot(va, vb))


def verdict(dist: float) -> str:
    if dist <= THRESHOLD:
        return f"✅ УЗНАЛА (high, {1 - dist:.0%})"
    if dist <= WEAK_THRESHOLD:
        return f"🟡 переспросит имя (low, {1 - dist:.0%})"
    return f"❌ НЕ УЗНАЛА ({1 - dist:.0%} < 75%)"


def main() -> int:
    store = VoiceMemoryStore("data/voice_memory.sqlite3")
    rows = store._all_rows()
    if not rows:
        print("❌ База пустая — не с чем сравнивать.")
        return 1
    print(f"В базе отпечатков: {len(rows)}")
    for row_id, name, phone, emb in rows:
        print(f"  id={row_id} «{name}» ({phone}), размер вектора {emb.shape}")

    embedder = VoiceEmbedder()
    if not embedder.enabled:
        print("❌ Resemblyzer не загрузился")
        return 1

    takes = [
        ("Дубль 1", "Здравствуйте, я хочу записаться на чистку зубов завтра после шести вечера."),
        ("Дубль 2 (другая фраза)", "Меня зовут Илья, продиктую номер телефона: восемь девять два один пять пять пять двенадцать тридцать четыре."),
        ("Дубль 3 (тише/иначе)", "А сколько стоят виниры и входит ли в цену работа врача?"),
    ]

    results: list[tuple[str, float]] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for label, phrase in takes:
            print(f"\n🎙 {label}. Скажи в микрофон (примерно): «{phrase}»")
            print("   Запись 6 секунд начнётся через 3 секунды…")
            time.sleep(3)
            print("   🔴 ГОВОРИ!")
            audio = record_pcm16(6.0, tmp / f"{label.split()[0]}.pcm")
            print("   ⏺  Записано.")
            emb = embedder.embed(audio)
            if not emb:
                print("   ⚠️  Не удалось построить отпечаток (тишина?)")
                continue
            for row_id, name, phone, stored in rows:
                d = distance(emb, stored.tolist())
                results.append((f"{label} vs «{name}»", d))
                print(f"   📊 дистанция до «{name}»: {d:.3f} → {verdict(d)}")

        # Контроль: заведомо чужой голос
        print("\n🎙 Контроль: синтетический чужой голос (say, Milena)…")
        alien = say_pcm16("Здравствуйте, я хочу записаться к стоматологу на завтра.", "Milena", tmp)
        alien_emb = embedder.embed(alien)
        for row_id, name, phone, stored in rows:
            d = distance(alien_emb, stored.tolist())
            results.append((f"чужой (Milena) vs «{name}»", d))
            print(f"   📊 дистанция до «{name}»: {d:.3f} → {verdict(d)}")

    print("\n" + "═" * 60)
    print("СВОДКА (пороги: high ≤ 0.15, low ≤ 0.25)")
    print("═" * 60)
    for label, d in results:
        print(f"  {label}: {d:.3f} — {verdict(d)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
