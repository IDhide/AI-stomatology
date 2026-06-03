# ════════════════════════════════════════════════════════════════════
#  Smile.AI — Dockerfile (multi-stage)
#
#  Targets:
#    deps    — только лёгкие зависимости (без torch/ML), для CI-проверки
#    builder — полная сборка с torch (для production)
#    runtime — финальный образ (FROM builder)
#
#  Build для CI:
#    docker build --target deps -t smile-ai:deps .
#
#  Build production (CPU):
#    docker build --target runtime -t smile-ai:latest .
#
#  Build production (GPU):
#    docker build --build-arg VARIANT=gpu --target runtime -t smile-ai:gpu .
#
#  Run:
#    docker compose up
# ════════════════════════════════════════════════════════════════════

ARG PYTHON_VERSION=3.11
ARG VARIANT=cpu

# ── Stage 1: base системные зависимости ──────────────────────────
FROM python:${PYTHON_VERSION}-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 libsndfile1 ffmpeg \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Не скачиваем Python — используем тот что в образе
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# ── Stage 2: deps — только лёгкие зависимости (CI target) ────────
FROM base AS deps

RUN uv venv .venv

COPY pyproject.toml .
COPY src/ src/

# Устанавливаем всё кроме torch/ML (для быстрой CI-проверки структуры)
RUN uv pip install --python .venv/bin/python \
    "loguru>=0.7.2" "pyyaml>=6.0.1" "pydantic>=2.5" \
    "python-dotenv>=1.0" "requests>=2.31" "aiohttp>=3.9" \
    "num2words>=0.5.13" "numpy>=1.26,<2.1" \
    "sounddevice>=0.4.6" "soundfile>=0.12.1" \
    "omegaconf>=2.3.0" "pillow>=10.0" \
    && uv pip install --python .venv/bin/python -e "." --no-deps

# ── Stage 3: builder — полная сборка с torch ─────────────────────
FROM base AS builder

ARG VARIANT

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN uv venv .venv

COPY pyproject.toml .
COPY src/ src/

# torch с PyPI работает и на CPU (содержит CUDA runtime, но не требует GPU)
# Для реального GPU сервера используй VARIANT=gpu
RUN if [ "$VARIANT" = "gpu" ]; then \
      uv pip install \
        --python .venv/bin/python \
        --extra-index-url https://download.pytorch.org/whl/cu121 \
        -e ".[gpu]"; \
    else \
      uv pip install \
        --python .venv/bin/python \
        -e ".[cpu]"; \
    fi

# ── Stage 4: runtime — финальный образ ───────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="Smile.AI Dental Assistant"
LABEL org.opencontainers.image.description="Голосовой ассистент стоматологической клиники"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 libsndfile1 ffmpeg \
    libgl1 libglib2.0-0 \
    libsdl2-2.0-0 libsdl2-mixer-2.0-0 \
    libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=builder /app/.venv .venv
COPY src/ src/
COPY config/ config/
COPY scripts/Modelfile scripts/Modelfile

RUN mkdir -p data/logs assets/videos

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV SDL_VIDEODRIVER=dummy
ENV SDL_AUDIODRIVER=dummy

WORKDIR /app

CMD ["python", "-m", "src.main_offline", "--no-camera", "--simulate-voice"]
