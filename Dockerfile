# ════════════════════════════════════════════════════════════════════
#  Smile.AI — Dockerfile
#
#  Многоэтапная сборка:
#    builder  — устанавливает зависимости через uv
#    runtime  — минимальный образ без build-инструментов
#
#  Build:
#    docker build --target runtime -t smile-ai:latest .
#    docker build --build-arg VARIANT=gpu --target runtime -t smile-ai:gpu .
#
#  Run (офлайн-демо без камеры):
#    docker compose up
# ════════════════════════════════════════════════════════════════════

ARG PYTHON_VERSION=3.11
ARG VARIANT=cpu

# ── Stage 1: builder ─────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

ARG VARIANT

# Системные зависимости для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libportaudio2 \
    libsndfile1 \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"

WORKDIR /app

# Копируем только файлы описания зависимостей (кэш слоёв)
COPY pyproject.toml .
COPY requirements.txt .
COPY requirements-minimal.txt .

# Создаём venv и ставим зависимости
RUN uv venv --python ${PYTHON_VERSION} .venv

RUN if [ "$VARIANT" = "gpu" ]; then \
        uv pip install \
            --extra-index-url https://download.pytorch.org/whl/cu121 \
            -e ".[gpu]" --no-cache; \
    else \
        uv pip install -e ".[cpu]" --no-cache; \
    fi

# ── Stage 2: runtime ─────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="Smile.AI Dental Assistant"
LABEL org.opencontainers.image.description="Голосовой ассистент стоматологической клиники"

# Runtime-зависимости (без build-tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 \
    libsndfile1 \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsdl2-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-ttf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем venv из builder-стадии
COPY --from=builder /app/.venv .venv

# Копируем исходники
COPY src/ src/
COPY config/ config/
COPY scripts/Modelfile scripts/Modelfile

# Создаём директории для данных
RUN mkdir -p data/logs assets/videos

# .env монтируется снаружи — не копируем
# assets/videos монтируется снаружи

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Для pygame без дисплея (headless / X11-форвардинг)
ENV SDL_VIDEODRIVER=dummy
ENV SDL_AUDIODRIVER=dummy

EXPOSE 8080

# Точка входа — оффлайн-демо по умолчанию
CMD ["python", "-m", "src.main_offline", "--no-camera", "--simulate-voice"]
