#!/usr/bin/env python3
"""
Визуальная демонстрация распознавания голоса Оливии.

Генерирует речь утилитой `say` (macOS), запоминает двух пациентов
(Анна и Борис), затем имитирует возвращение Анны и показывает,
как Оливия распознаёт её и формирует приветствие.

Запуск:
    cd server && ../.venv/bin/python scripts/demo_voice_id.py
"""
from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

import sys
from pathlib import Path
# проектный root, чтобы импорты server.app.* работали как в тестах
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.app.voice_id.embedder import VoiceEmbedder
from server.app.voice_id.store import VoiceMemoryStore


def say_to_pcm16(text: str, voice: str, tmp: Path) -> bytes:
    aiff = tmp / f"{voice}_{hash(text) % 10000}.aiff"
    wav = tmp / f"{voice}_{hash(text) % 10000}.wav"
    subprocess.run(["say", text, "-v", voice, "-o", str(aiff)], check=True, capture_output=True)
    subprocess.run(["afconvert", str(aiff), str(wav), "-f", "WAVE", "-d", "LEI16@16000"], check=True, capture_output=True)
    data, sr = sf.read(str(wav), dtype="int16")
    assert sr == 16000
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data.astype(np.int16).tobytes()


def main():
    embedder = VoiceEmbedder()
    if not embedder.enabled:
        print("❌ Resemblyzer не загрузился. Установите: pip install resemblyzer")
        return 1

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        store = VoiceMemoryStore(str(tmp / "voice_memory.sqlite3"))

        print("=" * 60)
        print("Демо: Оливия запоминает голоса пациентов")
        print("=" * 60)

        # 1. Регистрация двух пациентов
        print("\n🎙️  Регистрируем голос Анны (Samantha)...")
        anna_audio = say_to_pcm16(
            "Hello, I am Anna. I would like to book a dental consultation.",
            "Samantha",
            tmp,
        )
        anna_emb = embedder.embed(anna_audio)
        anna_id = store.enroll(anna_emb, name="Анна", phone="+7 921 555-12-34")
        print(f"   ✅ Анна сохранена, id={anna_id}")

        print("\n🎙️  Регистрируем голос Бориса (Daniel)...")
        boris_audio = say_to_pcm16(
            "Hello, I am Boris. I need a dental checkup tomorrow.",
            "Daniel",
            tmp,
        )
        boris_emb = embedder.embed(boris_audio)
        boris_id = store.enroll(boris_emb, name="Борис", phone="+7 921 555-56-78")
        print(f"   ✅ Борис сохранён, id={boris_id}")

        # 2. Анна возвращается — говорит другую фразу
        print("\n🎙️  Анна возвращается и говорит новую фразу...")
        anna_return_audio = say_to_pcm16(
            "Good afternoon, I am here for my follow-up appointment.",
            "Samantha",
            tmp,
        )
        anna_return_emb = embedder.embed(anna_return_audio)

        match = store.match(anna_return_emb, threshold=0.15, weak_threshold=0.25)
        print(f"   📊 similarity={match.similarity:.1%}, distance={match.distance:.3f}, confidence={match.confidence}, is_new={match.is_new}")

        if match.is_new:
            print("   ❌ Оливия НЕ узнала Анну")
        else:
            print(f"   ✅ Оливия узнала: это {match.name} ({match.phone})")
            prompt = VoiceMemoryStore.format_for_prompt(match)
            print(f"\n📝 Контекст для LLM:\n   {prompt}")
            print(f"\n💬 Оливия скажет:")
            print(f"   'Приятно вас снова видеть, {match.name}! Чем могу помочь?'")

        # 3. Новый пациент — голос, которого нет в базе
        print("\n🎙️  Новый пациент (Fred) подходит к киоску...")
        stranger_audio = say_to_pcm16(
            "Hi, this is my first time at the clinic. Can I book a visit?",
            "Fred",
            tmp,
        )
        stranger_emb = embedder.embed(stranger_audio)
        match_stranger = store.match(stranger_emb, threshold=0.15, weak_threshold=0.25)
        print(f"   📊 similarity={match_stranger.similarity:.1%}, distance={match_stranger.distance:.3f}, confidence={match_stranger.confidence}, is_new={match_stranger.is_new}")

        if match_stranger.is_new:
            print("   ✅ Оливия правильно считает это новым пациентом")
        else:
            print(f"   ⚠️  Ошибка: Оливия приняла нового пациента за {match_stranger.name}")

        # 4. Проверка порогов
        print("\n📐 Проверка порогов:")
        print(f"   strong threshold=0.15 → уверенное совпадение при similarity >= {1 - 0.15:.0%} (85%)")
        print(f"   weak threshold=0.25 → возможное совпадение при similarity >= {1 - 0.25:.0%} (75%)")

    print("\n" + "=" * 60)
    print("Демо завершено.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
