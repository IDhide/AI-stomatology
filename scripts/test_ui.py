#!/usr/bin/env python3
"""
test_ui.py
==========
Smoke-тест UI без камеры, без микрофона, без LLM.

Что делает:
  • открывает окно (windowed по умолчанию; --fullscreen для ТВ)
  • прогоняет режимы: IDLE → GREETING → LISTENING → THINKING → SPEAKING → IDLE
  • имитирует амплитуду TTS синусом, чтобы видеть пульсацию круга
  • показывает субтитры из тестовой реплики
  • через 30 секунд закрывается (или Esc, или закрыть окно)

Запуск:
    python scripts/test_ui.py
    python scripts/test_ui.py --fullscreen
"""
from __future__ import annotations

import argparse
import asyncio
import math
import sys
import time
from pathlib import Path

# чтобы можно было запускать как `python scripts/test_ui.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_config         # noqa: E402
from src.ui.display import UIDisplay            # noqa: E402


SCRIPT = [
    # (t, action, payload)
    (0.0,  "mode", "idle"),
    (3.0,  "subtitle_user", "[демо] нажмите Esc, чтобы выйти. F11 — fullscreen, S — субтитры"),
    (6.0,  "mode", "greeting"),
    (6.0,  "subtitle_bot", "Здравствуйте, я Лена, администратор клиники Smile. Чем могу помочь?"),
    (10.0, "mode", "listening"),
    (10.0, "subtitle_user", "вы: хочу записаться на чистку"),
    (14.0, "mode", "thinking"),
    (16.0, "mode", "speaking"),
    (16.0, "subtitle_bot", "Сейчас посмотрю свободное время. У нас есть пятница в пятнадцать тридцать, гигиенист Мария."),
    (24.0, "mode", "listening"),
    (24.0, "subtitle_user", "вы: подходит, запишите меня"),
    (27.0, "mode", "speaking"),
    (27.0, "subtitle_bot", "Записала, до встречи в пятницу!"),
    (32.0, "mode", "idle"),
    (32.0, "subtitle_clear", ""),
]


async def amplitude_emitter(ui: UIDisplay) -> None:
    """Имитирует амплитуду TTS пока mode == speaking."""
    t0 = time.monotonic()
    while ui.running:
        if ui.mode == "speaking":
            t = time.monotonic() - t0
            # «голос»: квазипериодический сигнал + слегка случайный
            amp = 0.5 + 0.4 * math.sin(t * 7.5) * (0.6 + 0.4 * math.sin(t * 1.8))
            ui.set_amplitude(max(0.0, amp))
        else:
            ui.set_amplitude(0.0)
        await asyncio.sleep(0.04)


async def script_runner(ui: UIDisplay, duration: float) -> None:
    t0 = time.monotonic()
    for when, action, payload in SCRIPT:
        wait = max(0.0, when - (time.monotonic() - t0))
        await asyncio.sleep(wait)
        if not ui.running:
            return
        if action == "mode":
            ui.set_mode(payload)
        elif action == "subtitle_user":
            ui.set_subtitle(payload, who="user")
        elif action == "subtitle_bot":
            ui.set_subtitle(payload, who="bot")
        elif action == "subtitle_clear":
            ui.clear_subtitle()
    # подождём остаток
    remain = duration - (time.monotonic() - t0)
    if remain > 0:
        await asyncio.sleep(remain)
    ui.running = False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fullscreen", action="store_true",
                        help="запустить в полноэкранном режиме на ТВ 1920×1080")
    parser.add_argument("--duration", type=float, default=36.0)
    args = parser.parse_args()

    cfg = load_config()
    cfg.ui.window["fullscreen"] = bool(args.fullscreen)
    if not args.fullscreen:
        cfg.ui.window["width"] = 1280
        cfg.ui.window["height"] = 720

    ui = UIDisplay(cfg.ui)

    async def runner():
        await asyncio.gather(
            ui.run(),
            amplitude_emitter(ui),
            script_runner(ui, args.duration),
        )

    try:
        asyncio.run(runner())
    finally:
        ui.cleanup()


if __name__ == "__main__":
    main()
