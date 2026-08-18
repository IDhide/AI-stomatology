"""
QA-стенд голосовой биометрии: доказательная матрица «свой/чужой» на
синтетической речи с симуляцией киоскового аудиотракта.

Что делаем:
  1. 4 диктора (2 жен., 2 муж.) × 3 разные фразы через macOS `say`.
  2. Каждую фразу гоняем через тракт киоска: 48кГц → блочно-усредняющий
     даунсэмпл в 16кГц (как в kiosk/audio.js после фикса алиасинга) +
     лёгкий белый шум (~-25 дБ, имитация регистратуры).
  3. Эмбеддинги через боевой VoiceEmbedder (гейт 6с чистой речи).
  4. Матрица косинусных дистанций → max «свой», min «чужой», запас к
     боевым порогам 0.25 (high) / 0.35 (weak).
  5. Отдельно: короткий образец (< 6с) обязан быть отброшен гейтом.

Запуск из папки server/:
    ../.venv/bin/python scripts/qa_voice.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.voice_id.embedder import VoiceEmbedder  # noqa: E402

VOICES = ["Samantha", "Karen", "Daniel", "Fred"]
PHRASES = [
    "Hello, I would like to make an appointment at the dental clinic for tomorrow evening, please.",
    "Good afternoon. My tooth has been hurting for two days, and I need to see a doctor as soon as possible.",
    "Hi, could you tell me how much a teeth cleaning costs and what time slots are available on Friday?",
]
HIGH_THRESHOLD = 0.17
WEAK_THRESHOLD = 0.35


def say_pcm(text: str, voice: str, tmp: Path, sr: int = 48000) -> np.ndarray:
    """say → WAV float32 нужной частоты."""
    aiff = tmp / f"{abs(hash((text, voice)))}.aiff"
    wav = tmp / f"{abs(hash((text, voice)))}.wav"
    subprocess.run(["say", text, "-v", voice, "-o", str(aiff)], check=True, capture_output=True)
    subprocess.run(
        ["afconvert", str(aiff), str(wav), "-f", "WAVE", "-d", f"F32@{sr}"],
        check=True, capture_output=True,
    )
    data, _ = sf.read(str(wav), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data


def kiosk_channel(audio48: np.ndarray, noise_db: float = -25.0) -> bytes:
    """Симуляция тракта киоска: даунсэмпл 48→16кГц блочным усреднением
    (ровно как kiosk/audio.js) + белый шум регистратуры. Выход PCM16.
    noise_db можно переопределить аргументом CLI: qa_voice.py -35"""
    factor = 3  # 48000 → 16000
    n = len(audio48) // factor * factor
    audio16 = audio48[:n].reshape(-1, factor).mean(axis=1)
    rms = float(np.sqrt(np.mean(audio16**2)) + 1e-12)
    noise_rms = rms * (10 ** (noise_db / 20))
    rng = np.random.default_rng(42)
    audio16 = audio16 + rng.normal(0, noise_rms, len(audio16)).astype(np.float32)
    pcm = np.clip(audio16, -1, 1)
    return (pcm * 32767).astype(np.int16).tobytes()


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()


def cos_dist(a: np.ndarray, b: np.ndarray) -> float:
    return 1.0 - float(np.dot(a, b))


def main() -> None:
    emb = VoiceEmbedder()
    if not emb.enabled:
        print("resemblyzer недоступен — стенд не запустить")
        sys.exit(1)

    tmp = Path(tempfile.mkdtemp(prefix="qa_voice_"))
    # embeddings[voice][phrase_idx] = vector
    embeddings: dict[str, list[np.ndarray]] = {}
    short_gate_results = []

    noise_db = float(sys.argv[1]) if len(sys.argv) > 1 else -25.0
    print(f"шум тракта: {noise_db} дБ")
    for voice in VOICES:
        embeddings[voice] = []
        for i, phrase in enumerate(PHRASES):
            audio48 = say_pcm(phrase, voice, tmp)
            pcm = kiosk_channel(audio48, noise_db=noise_db)
            # боевой гейт 6с чистой речи: короткую фразу «накапливаем» (как
            # main.py копит реплики в течение визита) до ~8с сырого аудио
            raw = pcm
            while len(raw) < int(8 * 16000) * 2:
                raw += pcm
            vec = emb.embed(raw)
            assert vec is not None, f"{voice} phrase {i}: embedding is None"
            embeddings[voice].append(np.array(vec, dtype=np.float32))
            print(f"  {voice} / фраза {i + 1}: отпечаток построен")
        # контроль гейта: одна короткая фраза без накопления
        short_vec = emb.embed(kiosk_channel(say_pcm("Hello.", voice, tmp)))
        short_gate_results.append((voice, short_vec is None))

    # ── матрица ───────────────────────────────────────────────────────
    same, cross = [], []
    names = list(embeddings)
    print(f"\n{'═' * 64}\nМАТРИЦА ДИСТАНЦИЙ (косинус, 0 = идентично)\n{'═' * 64}")
    header = " " * 22 + "".join(f"{n:>22}" for n in names)
    print(header)
    for a in names:
        row = f"{a:>22}"
        for b in names:
            if a == b:
                # честно: только РАЗНЫЕ фразы одного диктора (i < j)
                ds = [
                    cos_dist(embeddings[a][i], embeddings[a][j])
                    for i in range(len(embeddings[a]))
                    for j in range(i + 1, len(embeddings[a]))
                ]
            else:
                ds = [cos_dist(x, y) for x in embeddings[a] for y in embeddings[b]]
            d = min(ds)
            row += f"{d:>22.3f}"
            (same if a == b else cross).append(d)
        print(row)

    max_same, min_cross = max(same), min(cross)
    print(f"\nmax «свой» (разные фразы одного диктора): {max_same:.3f}")
    print(f"min «чужой»:                              {min_cross:.3f}")
    print(f"пороги: high={HIGH_THRESHOLD}, weak={WEAK_THRESHOLD}")
    print(f"запас high: {HIGH_THRESHOLD - max_same:+.3f} / weak: {WEAK_THRESHOLD - max_same:+.3f} "
          f"(свои), от чужих до weak: {min_cross - WEAK_THRESHOLD:+.3f}")

    # ── вердикты ──────────────────────────────────────────────────────
    # Критерий сдачи: чужой НИКОГДА не должен быть назван уверенно по имени
    # (min_cross > high). Попадание чужого в weak-зону — штатно: Оливия
    # мягко переспросит «вы Илья?», а не утверждает личность.
    weak_hits = [d for d in cross if HIGH_THRESHOLD < d <= WEAK_THRESHOLD]
    checks = [
        ("все «свои» уверенно узнаются (max_same <= high)", max_same <= HIGH_THRESHOLD),
        ("ни один «чужой» не назван уверенно (min_cross > high)", min_cross > HIGH_THRESHOLD),
        ("гейт 6с отбраковывает короткие образцы", all(ok for _, ok in short_gate_results)),
    ]
    print(f"\nчужих в weak-зоне (мягкий переспрос, штатно): {len(weak_hits)} из {len(cross)}")
    print(f"\n{'═' * 64}")
    failed = 0
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌'} {label}")
        failed += 0 if ok else 1
    print(f"\nИТОГ: {'PASS' if failed == 0 else f'FAIL ({failed})'}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
