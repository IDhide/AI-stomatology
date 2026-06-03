# ════════════════════════════════════════════════════════════════════
#  Smile.AI — Dockerfile (multi-stage)
#
#  Build (CPU, для разработки и CI):
#    docker build --target runtime -t smile-ai:latest .
#
#  Build (GPU / CUDA 12.1, production):
#    docker build --build-arg VARIANT=gpu --target runtime -t smile-ai:gpu .
#
#  Run:
#    docker compose up
# ════════════════════════════════════════════════════════════════════

ARG PYTHON_VERSION=3.11
ARG VARIANT=cpu

# ── Stage 1: builder ─────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

ARG VARIANT

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    libportaudio2 libsndfile1 ffmpeg \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# uv из официального образа — быстро и без curl-pipe-sh
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uvx /usr/local/bin/uvx

WORKDIR /app

# Используем системный Python образа (не скачиваем новый)
ENV UV_PYTHON_DOWNLOADS=never

# Создаём venv из системного Python
RUN uv venv .venv

# Копируем исходники (нужно для hatchling editable install)
COPY pyproject.toml .
COPY src/ src/

# Ставим зависимости
# CPU: torch со стандартного PyPI (cpu-only wheel)
# GPU: torch с индекса CUDA 12.1
RUN if [ "$VARIANT" = "gpu" ]; then \
      uv pip install \
        --python .venv/bin/python \
        --extra-index-url https://download.pytorch.org/whl/cu121 \
        -e ".[gpu]"; \
    else \
      uv pip install \
        --python .venv/bin/python \
        --index-url https://pypi.org/simple \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -e ".[cpu]"; \
    fi

# ── Stage 2: runtime ─────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="Smile.AI Dental Assistant"
LABEL org.opencontainers.image.description="Голосовой ассистент стоматологической клиники"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 libsndfile1 ffmpeg \
    libgl1 libglib2.0-0 \
    libsdl2-2.0-0 libsdl2-mixer-2.0-0 \
    libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

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

CMD ["python", "-m", "src.main_offline", "--no-camera", "--simulate-voice"]
