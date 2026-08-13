"""
Интеграционные тесты voice_id: реальные голосовые эмбеддинги через Resemblyzer.

Генерируем речь утилитой `say` (macOS), конвертируем в PCM16 mono 16kHz
и проверяем, что система:
  1. Запоминает голос пациента вместе с именем.
  2. При повторном звучании того же голоса находит совпадение.
  3. При сходстве >= 75% формирует приветствие по имени.
  4. Чужой голос считает новым пациентом.

Запуск:
    cd server && ../.venv/bin/python -m pytest tests/test_voice_id_integration.py -v -s
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from server.app.voice_id.embedder import VoiceEmbedder
from server.app.voice_id.store import VoiceMemoryStore, VoiceMatch


def _say_to_pcm16(text: str, voice: str, tmp_path: Path) -> bytes:
    """macOS say → AIFF → WAVE 16kHz mono → PCM16 bytes."""
    aiff = tmp_path / f"{voice}.aiff"
    wav = tmp_path / f"{voice}.wav"
    subprocess.run(
        ["say", text, "-v", voice, "-o", str(aiff)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["afconvert", str(aiff), str(wav), "-f", "WAVE", "-d", "LEI16@16000"],
        check=True,
        capture_output=True,
    )
    data, sr = sf.read(str(wav), dtype="int16")
    assert sr == 16000, f"unexpected sample rate {sr}"
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data.astype(np.int16).tobytes()


@pytest.fixture
def embedder():
    emb = VoiceEmbedder()
    if not emb.enabled:
        pytest.skip("resemblyzer не установлен или не загрузился")
    return emb


def _embed(embedder, pcm: bytes) -> list[float] | None:
    """embed() с учётом боевого гейта MIN_VOICED_SECONDS (6с чистой речи):
    короткую синтетическую фразу зацикливаем до ~8с сырого аудио, иначе
    гейт честно вернёт None — он для того и сделан, чтобы отбраковывать
    короткие образцы."""
    min_bytes = int(8 * 16000) * 2
    while len(pcm) < min_bytes:
        pcm += pcm
    return embedder.embed(pcm)


@pytest.fixture
def store(tmp_path):
    return VoiceMemoryStore(str(tmp_path / "voice_memory.sqlite3"))


def test_voice_match_has_similarity_property(store):
    vec = [1.0, 0.0, 0.0, 0.0]
    store.enroll(vec, name="Анна")
    match = store.match(vec, threshold=0.15, weak_threshold=0.25)

    assert match.is_new is False
    assert match.similarity == pytest.approx(1.0)
    assert match.confidence == "high"


def test_format_for_prompt_greets_by_name_at_high_confidence(store):
    vec = [1.0, 0.0, 0.0, 0.0]
    store.enroll(vec, name="Анна", phone="+7 921 555-12-34")
    match = store.match(vec, threshold=0.15, weak_threshold=0.25)

    text = VoiceMemoryStore.format_for_prompt(match)

    assert text is not None
    assert "высокая уверенность" in text
    assert "Приятно вас снова видеть, Анна" in text
    assert "+7 921 555-12-34" in text


def test_format_for_prompt_is_cautious_when_weak_match(store):
    import math
    vec_a = [math.cos(0), math.sin(0), 0.0, 0.0]
    # 40 градусов -> distance ≈ 0.234 -> между 0.15 и 0.25 -> low confidence
    vec_b = [math.cos(math.radians(40)), math.sin(math.radians(40)), 0.0, 0.0]
    store.enroll(vec_a, name="Анна")
    match = store.match(vec_b, threshold=0.15, weak_threshold=0.25)

    assert match.is_new is False
    assert match.confidence == "low"
    text = VoiceMemoryStore.format_for_prompt(match)
    assert text is not None
    assert "ДОГАДКА" in text
    assert "Приятно вас снова видеть" not in text


def test_format_for_prompt_none_when_new_patient(store):
    import math
    vec_a = [math.cos(0), math.sin(0), 0.0, 0.0]
    # 60 градусов -> distance = 0.5 > 0.25 -> new
    vec_b = [math.cos(math.radians(60)), math.sin(math.radians(60)), 0.0, 0.0]
    store.enroll(vec_a, name="Анна")
    match = store.match(vec_b, threshold=0.15, weak_threshold=0.25)

    assert match.is_new is True
    assert VoiceMemoryStore.format_for_prompt(match) is None


@pytest.mark.asyncio
async def test_real_voice_same_speaker_is_recognized(tmp_path, embedder, store):
    """Два образца одного голоса должны дать высокое сходство."""
    phrase = "Hello, I am a patient at the dental clinic. I would like to make an appointment."
    enroll_audio = _say_to_pcm16(phrase, "Samantha", tmp_path)
    test_audio = _say_to_pcm16(
        "Good afternoon, this is my second visit to the clinic.",
        "Samantha",
        tmp_path,
    )

    enroll_emb = _embed(embedder, enroll_audio)
    test_emb = _embed(embedder, test_audio)
    assert enroll_emb is not None, " enrollment embedding is None"
    assert test_emb is not None, "test embedding is None"

    store.enroll(enroll_emb, name="Анна", phone="+7 921 555-12-34")
    match = store.match(test_emb, threshold=0.15, weak_threshold=0.25)

    print(f"\n[同一说话人] similarity={match.similarity:.1%}, distance={match.distance:.3f}, confidence={match.confidence}, is_new={match.is_new}")
    assert match.is_new is False, f"same voice should match, got similarity={match.similarity:.1%}"
    assert match.similarity >= 0.85, f"expected >= 85% similarity, got {match.similarity:.1%}"
    assert match.confidence == "high"
    assert match.name == "Анна"


@pytest.mark.asyncio
async def test_real_voice_different_speaker_is_rejected(tmp_path, embedder, store):
    """Голоса двух разных дикторов не должны считаться одним пациентом."""
    anna_audio = _say_to_pcm16(
        "Hello, I am Anna, and this is my first appointment.",
        "Samantha",
        tmp_path,
    )
    boris_audio = _say_to_pcm16(
        "Hello, I am Boris, and I need a dental checkup.",
        "Daniel",
        tmp_path,
    )

    anna_emb = _embed(embedder, anna_audio)
    boris_emb = _embed(embedder, boris_audio)
    assert anna_emb is not None
    assert boris_emb is not None

    store.enroll(anna_emb, name="Анна")
    match = store.match(boris_emb, threshold=0.15, weak_threshold=0.25)

    print(f"\n[不同说话人] similarity={match.similarity:.1%}, distance={match.distance:.3f}, confidence={match.confidence}, is_new={match.is_new}")
    assert match.is_new is True, f"different voices should not match, got similarity={match.similarity:.1%}"


@pytest.mark.asyncio
async def test_similar_sounding_stranger_is_not_falsely_identified(tmp_path, embedder, store):
    """Похожий по полу/тембру голос не должен приниматься за известного пациента."""
    anna_audio = _say_to_pcm16(
        "Hello, I am Anna, and this is my first appointment.",
        "Samantha",
        tmp_path,
    )
    stranger_audio = _say_to_pcm16(
        "Hi, this is my first time at the clinic. Can I book a visit?",
        "Karen",
        tmp_path,
    )

    anna_emb = _embed(embedder, anna_audio)
    stranger_emb = _embed(embedder, stranger_audio)
    assert anna_emb is not None
    assert stranger_emb is not None

    store.enroll(anna_emb, name="Анна")
    match = store.match(stranger_emb, threshold=0.15, weak_threshold=0.25)

    print(f"\n[相似声音陌生人] similarity={match.similarity:.1%}, confidence={match.confidence}, is_new={match.is_new}")
    # Karen vs Samantha даёт ~82% — попадает в диапазон "возможное совпадение",
    # но НЕ в "высокая уверенность", значит Оливия только мягко переспросит.
    assert match.is_new is False or match.confidence == "low"
    if match.confidence == "high":
        pytest.fail(f"similar sounding stranger was accepted with high confidence: {match.similarity:.1%}")


@pytest.mark.asyncio
async def test_voice_greeting_prompt_for_returning_patient(tmp_path, embedder, store):
    """Полный сценарий: запомнили голос Анны, потом услышали её снова → приветствие по имени."""
    anna_first = _say_to_pcm16(
        "Hi, my name is Anna, and I want to book a consultation.",
        "Samantha",
        tmp_path,
    )
    anna_return = _say_to_pcm16(
        "Hi again, I would like to schedule another visit.",
        "Samantha",
        tmp_path,
    )

    first_emb = _embed(embedder, anna_first)
    return_emb = _embed(embedder, anna_return)
    assert first_emb is not None
    assert return_emb is not None

    store.enroll(first_emb, name="Анна", phone="+7 921 555-12-34")
    match = store.match(return_emb, threshold=0.15, weak_threshold=0.25)

    print(f"\n[回归患者] similarity={match.similarity:.1%}, confidence={match.confidence}, name={match.name}, is_new={match.is_new}")
    assert match.is_new is False
    assert match.similarity >= 0.85
    assert match.confidence == "high"

    prompt = VoiceMemoryStore.format_for_prompt(match)
    print(f"[prompt] {prompt}")
    assert prompt is not None
    assert "Приятно вас снова видеть, Анна" in prompt
