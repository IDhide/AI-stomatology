#!/usr/bin/env python3
"""
test_tts.py
===========
Изолированная проверка ЗВУКА: синтезирует пару русских фраз через Silero
и проигрывает их. Ни камеры, ни LLM, ни STT — только TTS + динамики.

Запуск:
    python scripts/test_tts.py
    python scripts/test_tts.py --speaker baya       # другой голос
    python scripts/test_tts.py --list-devices       # показать аудио-выходы
    python scripts/test_tts.py --device 2           # принудительно выбрать выход
    python scripts/test_tts.py --save out.wav       # сохранить в файл вместо проигрывания

Если звука всё равно нет — см. вывод --list-devices и раздел диагностики ниже.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speaker", default="xenia",
                        help="xenia | baya | kseniya | aidar | eugene")
    parser.add_argument("--device", type=int, default=None,
                        help="индекс устройства вывода (см. --list-devices)")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--save", default=None, help="сохранить wav вместо проигрывания")
    parser.add_argument("--text", default=None, help="произнести свой текст")
    args = parser.parse_args()

    # ── проверка зависимостей с понятными сообщениями ──
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        import torch
    except ImportError as e:
        print(f"✗ не хватает зависимости: {e}")
        print("  Поставьте окружение: bash scripts/setup_macbook.sh")
        print("  и активируйте: source .venv/bin/activate")
        return 1

    if args.list_devices:
        print("Доступные аудио-устройства:")
        print(sd.query_devices())
        print(f"\nТекущий выход по умолчанию: {sd.default.device}")
        return 0

    if args.device is not None:
        sd.default.device = (None, args.device)
        print(f"▶ Выбран выход #{args.device}")

    print("Доступные устройства вывода (кратко):")
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0:
                mark = " ← default" if i == sd.default.device[1] else ""
                print(f"  [{i}] {d['name']}{mark}")
    except Exception:
        pass

    # ── загрузка Silero ──
    print("\n▶ Загружаю Silero TTS (v4_ru)... (первый раз — скачается ~50 МБ)")
    device = torch.device("cpu")  # на Mac синтез на CPU
    model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-models",
        model="silero_tts",
        language="ru",
        speaker="v4_ru",
        trust_repo=True,
    )
    model.to(device)
    sample_rate = 48000

    # прогоним текст через наш нормализатор — проверим заодно и его
    try:
        from src.voice.russian_normalizer import normalize
    except Exception:
        def normalize(t):  # type: ignore
            return t

    phrases = [args.text] if args.text else [
        "Здравствуйте, я Лена, администратор клиники Smile.",
        "Чистка зубов стоит от 5500 рублей, ближайшее окно — завтра в 15:30.",
        "Чтобы зубы были здоровы, навещайте нас раз в полгода.",
    ]

    for raw in phrases:
        text = normalize(raw)
        print(f"\n▶ Синтез: {text}")
        audio = model.apply_tts(
            text=text, speaker=args.speaker, sample_rate=sample_rate,
            put_accent=True, put_yo=True,
        )
        audio_np = audio.cpu().numpy().astype(np.float32)

        if args.save:
            sf.write(args.save, audio_np, sample_rate)
            print(f"  ✓ сохранено в {args.save}")
        else:
            peak = float(np.abs(audio_np).max())
            print(f"  пик амплитуды = {peak:.3f} (если ~0 — синтез пустой)")
            sd.play(audio_np, sample_rate)
            sd.wait()
            print("  ✓ проиграно")

    print("\nГотово. Если ничего не услышали — проверьте:")
    print("  • громкость и выбранный выход в System Settings → Sound → Output")
    print("  • --list-devices и затем --device <N> для нужной колонки/наушников")
    print("  • что пик амплитуды выше нуля (иначе проблема в синтезе, а не в звуке)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
