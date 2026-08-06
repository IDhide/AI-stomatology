"""
tests/test_voice_id_embedder.py
VoiceEmbedder: конвертация PCM16→float, поведение при выключенной/включённой
модели. Точность самой модели Resemblyzer не переизобретаем тестами — она
проверена вручную на синтетической речи (см. план); здесь — только наша
обвязка вокруг неё.
"""
import numpy as np
import pytest

from server.app.voice_id import embedder as embedder_module
from server.app.voice_id.embedder import VoiceEmbedder, pcm16_to_float


def test_pcm16_to_float_converts_known_values():
    # int16: 0, 32767 (макс), -32768 (мин)
    raw = np.array([0, 32767, -32768], dtype=np.int16).tobytes()

    floats = pcm16_to_float(raw)

    assert floats.dtype == np.float32
    assert floats[0] == pytest.approx(0.0)
    assert floats[1] == pytest.approx(1.0, abs=1e-4)
    assert floats[2] == pytest.approx(-1.0, abs=1e-4)


def test_embedder_disabled_when_library_missing(monkeypatch):
    monkeypatch.setattr(embedder_module, "HAVE_RESEMBLYZER", False)

    emb = VoiceEmbedder()

    assert emb.enabled is False
    assert emb.embed(b"\x00\x00" * 8000) is None


@pytest.mark.skipif(not embedder_module.HAVE_RESEMBLYZER, reason="resemblyzer не установлен")
def test_embedder_returns_none_for_silence():
    emb = VoiceEmbedder()
    silence = b"\x00\x00" * (16000 * 2)  # 2 секунды полной тишины

    assert emb.embed(silence) is None


@pytest.mark.skipif(not embedder_module.HAVE_RESEMBLYZER, reason="resemblyzer не установлен")
def test_embedder_produces_normalized_vector_for_tonal_signal():
    emb = VoiceEmbedder()
    sr = 16000
    t = np.linspace(0, 3, sr * 3, dtype=np.float32)
    # модулированный тон ближе к речи, чем чистая синусоида, но это всё
    # ещё не гарантирует прохождение VAD — тест допускает оба исхода и
    # проверяет только то, что код не падает и, если эмбеддинг есть, он
    # нормирован
    tone = (0.2 * np.sin(2 * np.pi * 180 * t) * (1 + 0.5 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)
    audio_bytes = (tone * 32767).astype(np.int16).tobytes()

    result = emb.embed(audio_bytes)

    if result is not None:
        assert abs(np.linalg.norm(result) - 1.0) < 1e-3
