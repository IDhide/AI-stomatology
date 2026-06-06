# ════════════════════════════════════════════════════════════════════
#  Smile.AI — Dockerfile (веб-киоск)
#
#  Один образ для всего: веб-киоск (голос + визуал) и тестовый DIKIDI API.
#  Только pure-python зависимости. STT (faster-whisper) — опционально.
#
#  Сборка:        docker build --target web -t smile-ai:web .
#  С STT:         docker build --target web --build-arg WITH_STT=1 -t smile-ai:web .
#  Запуск удобнее через docker-compose.demo.yml / docker-compose.smart.yml.
# ════════════════════════════════════════════════════════════════════

ARG PYTHON_VERSION=3.11

# ── base ─────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# ── web: киоск + тестовый DIKIDI ─────────────────────────────────
FROM base AS web

# WITH_STT=1 — доустановить faster-whisper для серверного распознавания речи
# WITH_TTS=1 — доустановить piper-tts для серверного синтеза речи (рекомендуется
#              для медицины: голос полностью локальный, ничего в Google не уходит)
ARG WITH_STT=0
ARG WITH_TTS=0

RUN uv venv --python python3 .venv

RUN uv pip install --python .venv/bin/python \
    "loguru>=0.7.2" \
    "pyyaml>=6.0.1" \
    "pydantic>=2.5" \
    "python-dotenv>=1.0" \
    "aiohttp>=3.9" \
    "requests>=2.31"

# Опционально — серверный STT (faster-whisper, модель ~150 МБ–1.5 ГБ в рантайме)
RUN if [ "$WITH_STT" = "1" ]; then \
      uv pip install --python .venv/bin/python "faster-whisper>=1.0.0"; \
    fi

# Опционально — серверный TTS (Piper, голос ~63 МБ скачивается при первом запросе)
RUN if [ "$WITH_TTS" = "1" ]; then \
      uv pip install --python .venv/bin/python "piper-tts>=1.2.0"; \
    fi

# Опционально — детекция лиц камерой (OpenCV, ~50 МБ)
ARG WITH_CAMERA=0
RUN if [ "$WITH_CAMERA" = "1" ]; then \
      uv pip install --python .venv/bin/python "opencv-python-headless>=4.8.0"; \
    fi

COPY src/ src/
COPY config/ config/
COPY web/ web/

RUN mkdir -p data/logs assets/videos

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Smoke-тест импортов
RUN python -c "import src.web.server, src.dikidi.fake_server, src.dikidi.client; print('web stage OK')"

EXPOSE 8080 8089

# По умолчанию — веб-киоск (в compose переопределяется command-ой)
CMD ["python", "-m", "src.web.server", "--host", "0.0.0.0", "--port", "8080"]
