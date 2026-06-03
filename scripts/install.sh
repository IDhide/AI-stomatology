#!/bin/bash
# Скрипт автоматической установки AI Salon Assistant

set -e

echo "🚀 Установка AI Salon Assistant"
echo "================================"

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден. Установите Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python версия: $PYTHON_VERSION"

# Создание виртуального окружения
echo "📦 Создание виртуального окружения..."
python3 -m venv venv
source venv/bin/activate

# Обновление pip
echo "⬆️  Обновление pip..."
pip install --upgrade pip

# Установка зависимостей
echo "📚 Установка зависимостей..."
pip install -r requirements.txt

# Проверка CUDA
if command -v nvidia-smi &> /dev/null; then
    echo "✅ NVIDIA GPU обнаружена"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "⚠️  NVIDIA GPU не обнаружена, будет использоваться CPU"
fi

# Установка Ollama
if ! command -v ollama &> /dev/null; then
    echo "📥 Установка Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "✅ Ollama уже установлена"
fi

# Загрузка модели
echo "🤖 Загрузка модели OpenClaw..."
ollama pull openclaw

# Создание директорий
echo "📁 Создание директорий..."
mkdir -p data/logs
mkdir -p assets/videos
mkdir -p config

# Копирование конфигурации
if [ ! -f .env ]; then
    echo "📝 Создание .env файла..."
    cp .env.example .env
    echo "⚠️  Не забудьте заполнить .env файл!"
fi

echo ""
echo "✅ Установка завершена!"
echo ""
echo "Следующие шаги:"
echo "1. Отредактируйте .env файл с вашими API ключами"
echo "2. Поместите видео с медузами в assets/videos/jellyfish.mp4"
echo "3. Запустите: python src/main.py"
echo ""
