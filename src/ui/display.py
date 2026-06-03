"""
display.py
==========
Полноэкранный UI для телевизора 1920×1080 (Linux + pygame).

Режимы:
  IDLE      — фоновое видео с медузами, петля + fade
  GREETING  — короткая «волна», круг проявляется
  LISTENING — мягкое дыхание круга, лёгкая зелень
  THINKING  — медленная пульсация, тусклый круг, янтарный
  SPEAKING  — пульс в такт амплитуде TTS + волновые кольца

Особенности:
- Адаптивное разрешение: можно работать в окне и full-screen.
- Субтитры (последняя реплика) выводятся внизу — переключаются клавишей S.
- Реакция на амплитуду речи: TTS вызывает `set_amplitude(float)` и круг
  «дышит» в такт. Без этого пульсация — синусоидальная.
- Все цвета и параметры — через self.cfg, легко тюнить из settings.yaml.
- F11 — toggle fullscreen, Esc — выход, R — сброс к IDLE.

Запуск без камеры/мика:
    python scripts/test_ui.py
"""
from __future__ import annotations

import asyncio
import math
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pygame
from loguru import logger


# ────────────────────────────────────────────────────────────
# Цветовые пресеты режимов (R, G, B)
# ────────────────────────────────────────────────────────────
COLOR_PRESETS = {
    "idle":      ((120, 210, 255), (80, 180, 240)),
    "greeting":  ((140, 220, 255), (110, 200, 240)),
    "listening": ((130, 235, 200), (90, 200, 170)),
    "thinking":  ((255, 200, 110), (220, 170, 90)),
    "speaking":  ((140, 215, 255), (90, 180, 240)),
}

# Цвет subtitle bar
SUBTITLE_BG = (10, 18, 36, 200)        # тёмно-синий полупрозрачный
SUBTITLE_FG_USER = (159, 225, 203)     # мятный — пациент
SUBTITLE_FG_BOT = (200, 230, 255)      # светло-голубой — Лена


class UIDisplay:
    """
    Управление визуальным интерфейсом ассистента.
    Использование (async):
        ui = UIDisplay(cfg_window_cfg, video_path)
        asyncio.create_task(ui.run())
        ui.set_mode("listening")
        ui.set_subtitle("пациент: здравствуйте", who="user")
        ui.set_amplitude(0.7)
    """

    def __init__(self, cfg):
        """
        cfg — секция `ui` из settings.yaml. Поддерживается и pydantic-объект,
        и обычный dict (унаследовано от существующего config-загрузчика).
        """
        self.cfg = cfg
        self._win = self._get_section(cfg, "window")
        self._circle = self._get_section(cfg, "circle")
        self._video_cfg = self._get_section(cfg, "idle_video")

        # ── Pygame init ──
        pygame.init()
        pygame.display.set_caption("Smile.AI")

        self.width = int(self._win.get("width", 1920))
        self.height = int(self._win.get("height", 1080))
        self.bg_color = tuple(self._win.get("background", [8, 12, 22]))
        self.fullscreen = bool(self._win.get("fullscreen", True))
        self._build_surface()

        # ── Шрифты ──
        # pygame.freetype доступнее, но Font(None,..) даёт более «толстый» glyph
        try:
            self.font_subtitle = pygame.font.SysFont("DejaVu Sans, Arial", 42)
            self.font_status = pygame.font.SysFont("DejaVu Sans, Arial", 26)
        except Exception:
            self.font_subtitle = pygame.font.Font(None, 42)
            self.font_status = pygame.font.Font(None, 26)

        # ── Видео медуз ──
        video_path_raw = self._video_cfg.get("path", "assets/videos/jellyfish.mp4")
        video_path = Path(video_path_raw)
        self.video_cap: Optional[cv2.VideoCapture] = None
        if video_path.exists():
            self.video_cap = cv2.VideoCapture(str(video_path))
            fps_hint = self.video_cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.video_frame_dt = 1.0 / max(fps_hint, 10.0)
            self._last_video_t = 0.0
            self._last_video_surf: Optional[pygame.Surface] = None
            logger.success(f"Видео загружено: {video_path}")
        else:
            logger.warning(f"Видео медуз не найдено: {video_path} — фон чёрный")

        # ── Параметры круга ──
        self.base_radius = int(self._circle.get("radius", 180))
        self.pulse_speed = float(self._circle.get("pulse_speed", 2.0))
        self.pulse_range = tuple(self._circle.get("pulse_range", [0.85, 1.25]))
        self.react_to_amp = bool(self._circle.get("react_to_amplitude", True))

        # ── Состояние ──
        self.mode = "idle"
        self.prev_mode = "idle"
        self._mode_started_at = time.monotonic()
        self._fade = 0.0          # 0..1 = доля активного режима поверх медуз
        self._pulse_phase = 0.0
        self._amplitude = 0.0     # 0..1, плавно сглажен
        self._amp_target = 0.0
        self._rings: list[tuple[float, float]] = []  # (start_t, peak_radius)
        self._last_ring_t = 0.0
        self._subtitle_text = ""
        self._subtitle_who = "user"   # user | bot
        self._subtitle_visible = True

        self.running = False
        self.clock = pygame.time.Clock()
        logger.success(f"UI готов: {self.width}×{self.height} "
                       f"({'fullscreen' if self.fullscreen else 'window'})")

    # ──────────────────────────────────────────────────────────
    @staticmethod
    def _get_section(cfg, name: str) -> dict:
        """Поддержка и dict, и pydantic-конфига."""
        val = getattr(cfg, name, None)
        if val is None and isinstance(cfg, dict):
            val = cfg.get(name)
        if val is None:
            return {}
        if hasattr(val, "model_dump"):
            return val.model_dump()
        if isinstance(val, dict):
            return val
        return {}

    def _build_surface(self) -> None:
        flags = pygame.DOUBLEBUF
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((self.width, self.height), flags)

    # ──────────────────────────────────────────────────────────
    # Публичный API — вызывается из orchestrator / TTS
    # ──────────────────────────────────────────────────────────
    def set_mode(self, mode: str) -> None:
        if mode == self.mode:
            return
        logger.debug(f"UI: {self.mode} → {mode}")
        self.prev_mode = self.mode
        self.mode = mode
        self._mode_started_at = time.monotonic()
        self._pulse_phase = 0.0
        if mode in ("greeting", "listening", "thinking", "speaking"):
            # активный режим — fade in от idle
            pass
        if mode == "speaking":
            self._rings.clear()

    def set_amplitude(self, amp: float) -> None:
        """Вызывается из TTS на каждый аудиоблок (~50 мс). amp in [0..1+]."""
        # клип + сглаживание
        self._amp_target = float(max(0.0, min(1.5, amp)))

    def set_subtitle(self, text: str, who: str = "user") -> None:
        self._subtitle_text = text.strip()
        self._subtitle_who = "bot" if who == "bot" else "user"

    def clear_subtitle(self) -> None:
        self._subtitle_text = ""

    def start_speaking_animation(self) -> None:
        self.set_mode("speaking")

    def stop_speaking_animation(self) -> None:
        if self.mode == "speaking":
            self.set_mode("listening")

    # ──────────────────────────────────────────────────────────
    async def run(self) -> None:
        """Основной цикл. Запускать через asyncio.create_task()."""
        self.running = True
        target_fps = 60
        while self.running:
            self._handle_events()
            dt = self.clock.tick(target_fps) / 1000.0
            self._step(dt)
            self._draw()
            pygame.display.flip()
            await asyncio.sleep(0)   # отдать управление event loop

    # ──────────────────────────────────────────────────────────
    def _handle_events(self) -> None:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self.running = False
                elif ev.key == pygame.K_F11:
                    self.fullscreen = not self.fullscreen
                    self._build_surface()
                elif ev.key == pygame.K_s:
                    self._subtitle_visible = not self._subtitle_visible
                elif ev.key == pygame.K_r:
                    self.set_mode("idle")
                    self.clear_subtitle()

    # ──────────────────────────────────────────────────────────
    def _step(self, dt: float) -> None:
        # fade idle ↔ active
        target_fade = 0.0 if self.mode == "idle" else 1.0
        fade_speed = 1.5  # за секунду полный переход
        if self._fade < target_fade:
            self._fade = min(target_fade, self._fade + fade_speed * dt)
        elif self._fade > target_fade:
            self._fade = max(target_fade, self._fade - fade_speed * dt)

        # фаза пульсации
        self._pulse_phase += self.pulse_speed * dt

        # сглаживание амплитуды
        smoothing = 0.18
        self._amplitude += (self._amp_target - self._amplitude) * (1.0 - math.exp(-dt / smoothing))

        # speaking: новые волновые кольца при пиках амплитуды
        if self.mode == "speaking" and self._amplitude > 0.18:
            now = time.monotonic()
            if now - self._last_ring_t > 0.18:
                self._rings.append((now, self.base_radius * 1.8))
                self._last_ring_t = now
        # выкидываем старые кольца (>1.2с)
        now = time.monotonic()
        self._rings = [(t0, peak) for (t0, peak) in self._rings if now - t0 < 1.2]

    # ──────────────────────────────────────────────────────────
    def _draw(self) -> None:
        # 1. Фон: либо медузы, либо bg_color
        self._draw_idle_video_layer()

        # 2. Затемнение под круг (для активных режимов)
        if self._fade > 0.001:
            dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            dim.fill((0, 0, 0, int(160 * self._fade)))
            self.screen.blit(dim, (0, 0))

            self._draw_rings()
            self._draw_circle()
            self._draw_status_label()

        # 3. Субтитры — поверх всего
        self._draw_subtitle()

    # ──────────────────────────────────────────────────────────
    def _draw_idle_video_layer(self) -> None:
        if self.video_cap is None:
            self.screen.fill(self.bg_color)
            return
        # читаем с темпом видео (не каждый кадр UI)
        now = time.monotonic()
        if (self._last_video_surf is None) or (now - self._last_video_t >= self.video_frame_dt):
            ret, frame = self.video_cap.read()
            if not ret:
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.video_cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                # pygame ожидает (W, H, 3); cv2 даёт (H, W, 3) — swap осей
                frame = np.swapaxes(frame, 0, 1)
                self._last_video_surf = pygame.surfarray.make_surface(frame)
                self._last_video_t = now

        if self._last_video_surf is not None:
            self.screen.blit(self._last_video_surf, (0, 0))
        else:
            self.screen.fill(self.bg_color)

    # ──────────────────────────────────────────────────────────
    def _draw_circle(self) -> None:
        cx, cy = self.width // 2, self.height // 2
        primary, secondary = COLOR_PRESETS.get(self.mode, COLOR_PRESETS["idle"])

        # радиус
        if self.mode == "listening":
            # мягкое дыхание + лёгкая реакция на амплитуду
            breathe = 0.96 + 0.04 * math.sin(self._pulse_phase * 0.8)
            scale = breathe + (self._amplitude * 0.18 if self.react_to_amp else 0.0)
        elif self.mode == "thinking":
            scale = 0.92 + 0.05 * math.sin(self._pulse_phase * 0.5)
        elif self.mode == "speaking":
            base = 0.95 + 0.05 * math.sin(self._pulse_phase * 2.0)
            scale = base + (self._amplitude * 0.45 if self.react_to_amp else 0.15 * math.sin(self._pulse_phase * 3))
        elif self.mode == "greeting":
            t = min(1.0, (time.monotonic() - self._mode_started_at) / 0.6)
            scale = 0.5 + 0.6 * t
        else:
            scale = 1.0

        r = int(self.base_radius * scale * self._fade + self.base_radius * (1 - self._fade))
        r = max(40, r)

        # три «слоя» с убывающей прозрачностью
        halo = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.circle(halo, (*primary, 35), (cx, cy), int(r * 1.55))
        pygame.draw.circle(halo, (*primary, 70), (cx, cy), int(r * 1.25))
        pygame.draw.circle(halo, (*primary, 220), (cx, cy), int(r))
        pygame.draw.circle(halo, (*secondary, 255), (cx, cy), int(r * 0.62))
        self.screen.blit(halo, (0, 0))

    def _draw_rings(self) -> None:
        if not self._rings:
            return
        cx, cy = self.width // 2, self.height // 2
        ring_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        primary, _ = COLOR_PRESETS["speaking"]
        now = time.monotonic()
        for t0, peak in self._rings:
            age = now - t0
            life = 1.2
            k = age / life
            radius = int(self.base_radius * 0.9 + (peak - self.base_radius * 0.9) * k)
            alpha = max(0, int(180 * (1.0 - k)))
            width = max(1, int(4 * (1.0 - k)))
            pygame.draw.circle(ring_surf, (*primary, alpha), (cx, cy), radius, width)
        self.screen.blit(ring_surf, (0, 0))

    # ──────────────────────────────────────────────────────────
    def _draw_status_label(self) -> None:
        label_map = {
            "greeting":  "Здравствуйте",
            "listening": "Слушаю…",
            "thinking":  "Думаю…",
            "speaking":  "Говорю…",
        }
        text = label_map.get(self.mode, "")
        if not text:
            return
        surf = self.font_status.render(text, True, (220, 230, 240))
        rect = surf.get_rect(center=(self.width // 2, self.height // 2 + self.base_radius + 60))
        self.screen.blit(surf, rect)

    # ──────────────────────────────────────────────────────────
    def _draw_subtitle(self) -> None:
        if not (self._subtitle_visible and self._subtitle_text):
            return
        # Перенос длинного текста по словам
        max_width = int(self.width * 0.86)
        words = self._subtitle_text.split()
        lines: list[str] = []
        current: list[str] = []
        for w in words:
            test = " ".join(current + [w])
            if self.font_subtitle.size(test)[0] <= max_width:
                current.append(w)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [w]
        if current:
            lines.append(" ".join(current))
        # До 3 строк
        lines = lines[-3:]

        # фон-плашка
        line_h = self.font_subtitle.get_linesize()
        pad_x, pad_y = 40, 24
        block_h = line_h * len(lines) + pad_y * 2
        block_w = max(self.font_subtitle.size(ln)[0] for ln in lines) + pad_x * 2
        block_w = min(block_w, max_width + pad_x * 2)

        bx = (self.width - block_w) // 2
        by = self.height - block_h - 64

        plate = pygame.Surface((block_w, block_h), pygame.SRCALPHA)
        plate.fill(SUBTITLE_BG)
        self.screen.blit(plate, (bx, by))

        color = SUBTITLE_FG_USER if self._subtitle_who == "user" else SUBTITLE_FG_BOT
        for i, line in enumerate(lines):
            surf = self.font_subtitle.render(line, True, color)
            self.screen.blit(surf, (bx + pad_x, by + pad_y + i * line_h))

    # ──────────────────────────────────────────────────────────
    def cleanup(self) -> None:
        self.running = False
        if self.video_cap is not None:
            self.video_cap.release()
        pygame.quit()
        logger.info("UI остановлен")
