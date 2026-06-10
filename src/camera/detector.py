"""
detector.py
===========
Серверная детекция присутствия человека через RTSP-камеру.

Поддерживает:
  • USB-камеру (device_index, по умолчанию 0)
  • RTSP-поток (Xiaomi C200 через go2rtc, любая IP-камера)

Детекция — OpenCV Haar cascade (лёгкий, без GPU, <50 мс на кадр).
При устойчивом обнаружении лица → колбэк on_person_detected.
При уходе человека (нет лица N секунд) → колбэк on_person_left.

Переменные окружения:
  CAMERA_SOURCE     — RTSP URL или индекс USB-камеры (по умолчанию: не задано)
  CAMERA_FPS        — частота анализа кадров (по умолчанию 5)
  CAMERA_COOLDOWN   — секунд между повторными детекциями (по умолчанию 30)
  CAMERA_LOST_AFTER — секунд без лица = «ушёл» (по умолчанию 5)
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from threading import Thread

from loguru import logger

_detector_thread: Thread | None = None
_stop_flag = False


def _resolve_source() -> str | int | None:
    src = os.getenv("CAMERA_SOURCE", "").strip()
    if not src:
        return None
    if src.isdigit():
        return int(src)
    return src


def _run_loop(
    source: str | int,
    fps: float,
    cooldown: float,
    lost_after: float,
    on_detected: Callable[[], None],
    on_left: Callable[[], None],
) -> None:
    global _stop_flag
    try:
        import cv2
    except ImportError:
        logger.error("opencv-python-headless не установлен — камера не работает")
        return

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    logger.info(f"Камера: подключаюсь к {source}…")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        logger.error(f"Камера: не удалось открыть {source}")
        return
    logger.success(f"Камера: подключена ({source})")

    person_present = False
    last_face_time = 0.0
    last_trigger_time = 0.0
    frame_interval = 1.0 / max(fps, 1)

    while not _stop_flag:
        time.sleep(frame_interval)
        ret, frame = cap.read()
        if not ret:
            logger.warning("Камера: не удалось прочитать кадр, переподключение…")
            cap.release()
            time.sleep(2)
            cap = cv2.VideoCapture(source)
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.3, minNeighbors=5, minSize=(80, 80)
        )

        now = time.monotonic()

        if len(faces) > 0:
            last_face_time = now
            if not person_present and (now - last_trigger_time) > cooldown:
                person_present = True
                last_trigger_time = now
                logger.info("Камера: человек обнаружен")
                try:
                    on_detected()
                except Exception:
                    logger.exception("on_detected callback error")
        else:
            if person_present and (now - last_face_time) > lost_after:
                person_present = False
                logger.info("Камера: человек ушёл")
                try:
                    on_left()
                except Exception:
                    logger.exception("on_left callback error")

    cap.release()
    logger.info("Камера: остановлена")


def start(
    on_detected: Callable[[], None],
    on_left: Callable[[], None],
) -> bool:
    """Запустить детекцию в фоновом потоке. Возвращает True если камера настроена."""
    global _detector_thread, _stop_flag
    source = _resolve_source()
    if source is None:
        logger.info("Камера: CAMERA_SOURCE не задан — детекция отключена")
        return False

    fps = float(os.getenv("CAMERA_FPS", "5"))
    cooldown = float(os.getenv("CAMERA_COOLDOWN", "30"))
    lost_after = float(os.getenv("CAMERA_LOST_AFTER", "5"))

    _stop_flag = False
    _detector_thread = Thread(
        target=_run_loop,
        args=(source, fps, cooldown, lost_after, on_detected, on_left),
        daemon=True,
        name="camera-detector",
    )
    _detector_thread.start()
    return True


def stop() -> None:
    global _stop_flag
    _stop_flag = True
