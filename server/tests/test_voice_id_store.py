"""
tests/test_voice_id_store.py
Локальное хранилище голосовых отпечатков (sqlite, без Resemblyzer).

Эмбеддинги ниже — синтетические единичные векторы, а не настоящие голосовые
отпечатки: для проверки match/enroll/touch_seen важна только геометрия
(cosine distance), а не то, откуда взялся вектор. Реальная точность модели
проверена вручную (см. план) отдельно, на синтетической речи через `say`.
"""
import math

import pytest

from server.app.voice_id.store import VoiceMemoryStore, VoiceMatch


def _unit_vector(angle_deg: float, dim: int = 4) -> list[float]:
    """Двумерный единичный вектор (в первых двух координатах), остальное — нули."""
    rad = math.radians(angle_deg)
    vec = [math.cos(rad), math.sin(rad)] + [0.0] * (dim - 2)
    return vec


def test_match_on_empty_store_is_always_new(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    match = store.match(_unit_vector(0), threshold=0.25)

    assert match.is_new is True
    assert match.patient_id is None
    assert match.distance == 2.0


def test_enroll_then_match_identical_vector_recognizes(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    vec = _unit_vector(0)
    patient_id = store.enroll(vec, name="Мария", phone="+7 921 555-12-34")

    match = store.match(vec, threshold=0.25)

    assert match.is_new is False
    assert match.patient_id == patient_id
    assert match.name == "Мария"
    assert match.phone == "+7 921 555-12-34"
    assert match.distance < 0.01


def test_match_far_vector_is_new_even_with_data_in_store(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    store.enroll(_unit_vector(0), name="Мария")

    # 90 градусов -> cosine distance = 1 - 0 = 1.0, далеко за порогом
    match = store.match(_unit_vector(90), threshold=0.25)

    assert match.is_new is True
    assert match.patient_id is None


def test_match_picks_closest_of_several_patients(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    # углы далеко друг от друга (> DEDUP_DISTANCE), иначе enroll сольёт
    # «дубли» в один профиль — это новое осознанное поведение
    store.enroll(_unit_vector(0), name="Далёкий", phone=None)
    store.enroll(_unit_vector(120), name="Близкий", phone=None)

    match = store.match(_unit_vector(110), threshold=1.5)

    assert match.name == "Близкий"


def test_threshold_boundary_is_strict_greater_than(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    vec = _unit_vector(0)
    store.enroll(vec, name="Мария")

    # distance ровно 0.0 (идентичный вектор) — должен пройти любой порог >= 0
    assert store.match(vec, threshold=0.0).is_new is False


def test_touch_seen_updates_last_seen_at_without_error(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    patient_id = store.enroll(_unit_vector(0), name="Мария")

    store.touch_seen(patient_id)  # не должно бросать исключение

    match = store.match(_unit_vector(0), threshold=0.25)
    assert match.patient_id == patient_id


def test_two_tier_match_high_confidence(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    vec = _unit_vector(0)
    store.enroll(vec, name="Мария")

    # distance 0.0 <= 0.15 -> high confidence
    match = store.match(vec, threshold=0.15, weak_threshold=0.25)

    assert match.is_new is False
    assert match.confidence == "high"


def test_two_tier_match_low_confidence(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    store.enroll(_unit_vector(0), name="Мария")

    # 20 градусов -> distance = 1 - cos(20°) ≈ 0.06 -> high confidence
    # 50 градусов -> distance = 1 - cos(50°) ≈ 0.36 -> beyond weak threshold
    # 30 градусов -> distance ≈ 0.134 -> high confidence
    # 40 градусов -> distance ≈ 0.234 -> low confidence
    match = store.match(_unit_vector(40), threshold=0.15, weak_threshold=0.25)

    assert match.is_new is False
    assert match.confidence == "low"


def test_two_tier_match_new_patient(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    store.enroll(_unit_vector(0), name="Мария")

    # 60 градусов -> distance ≈ 0.5 > 0.25 -> new patient
    match = store.match(_unit_vector(60), threshold=0.15, weak_threshold=0.25)

    assert match.is_new is True
    assert match.confidence == "none"


def test_format_for_prompt_none_when_is_new():
    match = VoiceMatch(patient_id=None, name=None, phone=None, distance=2.0, is_new=True)
    assert VoiceMemoryStore.format_for_prompt(match) is None


def test_format_for_prompt_greets_by_name_at_high_confidence():
    # distance 0.05 -> similarity 95%, confidence=high -> приветствие по имени
    match = VoiceMatch(patient_id=1, name="Мария", phone="+7 921 555-12-34", distance=0.05, is_new=False, confidence="high")
    text = VoiceMemoryStore.format_for_prompt(match)

    assert text is not None
    assert "Мария" in text
    assert "+7 921 555-12-34" in text
    assert "Приятно вас снова видеть, Мария" in text
    assert "высокая уверенность" in text
    assert "ДОГАДКА" not in text


def test_format_for_prompt_is_cautious_when_low_confidence():
    # distance 0.20 -> similarity 80%, confidence=low -> мягкий вопрос
    match = VoiceMatch(patient_id=1, name="Мария", phone=None, distance=0.20, is_new=False, confidence="low")
    text = VoiceMemoryStore.format_for_prompt(match)

    assert text is not None
    assert "Мария" in text
    assert "ДОГАДКА" in text
    assert "Приятно вас снова видеть" not in text
    assert "возможное совпадение" in text


def test_format_for_prompt_without_phone_omits_phone_line():
    match = VoiceMatch(patient_id=1, name="Мария", phone=None, distance=0.05, is_new=False, confidence="high")
    text = VoiceMemoryStore.format_for_prompt(match)

    assert text is not None
    assert "Телефон" not in text
    assert "Приятно вас снова видеть, Мария" in text


def test_similarity_property():
    match = VoiceMatch(patient_id=1, name="Мария", phone=None, distance=0.25, is_new=False)
    assert match.similarity == pytest.approx(0.75)


def test_update_embedding_shifts_vector_toward_new(tmp_path):
    # 0° и 30°: среднее должно лежать между ними, норма — единичная
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    patient_id = store.enroll(_unit_vector(0), name="Мария")

    store.update_embedding(patient_id, _unit_vector(30), new_weight=0.5)

    match = store.match(_unit_vector(15), threshold=0.25)
    assert match.is_new is False
    assert match.distance < 1.0 - math.cos(math.radians(16))  # ближе к 15°, чем к 16°
    with store._connect() as conn:
        raw = conn.execute(
            "select embedding_json from voice_patients where id = ?", (patient_id,)
        ).fetchone()[0]
    import json

    vec = json.loads(raw)
    norm = math.sqrt(sum(x * x for x in vec))
    assert norm == pytest.approx(1.0, abs=1e-5)


def test_update_embedding_missing_patient_is_noop(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    # не должно падать на несуществующем id
    store.update_embedding(999, _unit_vector(10))


def test_enroll_merges_duplicate_voice_instead_of_new_row(tmp_path):
    """Похожий отпечаток (тот же человек в другой визит) не плодит дубли."""
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    first_id = store.enroll(_unit_vector(0), name="Илья", phone=None)

    second_id = store.enroll(_unit_vector(10), name="Илья", phone="+7 900 000-00-00")

    assert second_id == first_id  # объединили, а не создали новый
    rows = store._all_rows()
    assert len(rows) == 1
    # телефон дозаписался в существующий профиль
    assert rows[0][2] == "+7 900 000-00-00"


def test_enroll_keeps_truly_different_voice_separate(tmp_path):
    store = VoiceMemoryStore(str(tmp_path / "voice.sqlite3"))
    store.enroll(_unit_vector(0), name="Илья")
    store.enroll(_unit_vector(150), name="Сергей")

    assert len(store._all_rows()) == 2
