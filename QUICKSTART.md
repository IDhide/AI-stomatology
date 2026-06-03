# 🚀 Быстрый старт

## Вариант 1: DEMO режим (5 минут)

Самый быстрый способ увидеть систему в действии:

```bash
# 1. Установите минимальные зависимости
pip3 install loguru pyyaml pydantic python-dotenv requests aiohttp python-dateutil

# 2. Создайте .env
cp .env.example .env

# 3. Запустите DEMO
python3 src/main_demo.py
```

**Что вы увидите:**
- Симуляцию обнаружения клиента
- Автоматическое приветствие
- Разговор с mock ответами
- Прощание
- Логи в `data/logs/conversations.jsonl`

**Нажмите Ctrl+C для остановки**

---

## Вариант 2: Полная установка (30-60 минут)

### Шаг 1: Системные требования

- Python 3.10+
- NVIDIA GPU с CUDA (опционально, но рекомендуется)
- 16GB RAM минимум
- Камера (USB или встроенная)

### Шаг 2: Установка зависимостей

```bash
# Создайте виртуальное окружение (рекомендуется)
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt
```

### Шаг 3: Установка Ollama

**Linux/Mac:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Скачайте с https://ollama.com/download

**Загрузите модель:**
```bash
ollama pull openclaw
```

### Шаг 4: Настройка DIKIDI API

1. Зарегистрируйтесь на https://dikidi.net
2. Получите API ключ в личном кабинете
3. Найдите ID вашей компании

Отредактируйте `.env`:
```env
DIKIDI_API_KEY=ваш_ключ_здесь
DIKIDI_COMPANY_ID=ваш_id_здесь
```

### Шаг 5: Подготовка видео

Создайте или скачайте видео с медузами:
```bash
mkdir -p assets/videos
# Поместите видео в assets/videos/jellyfish.mp4
```

Или используйте любое другое видео, обновив путь в `config/settings.yaml`

### Шаг 6: Проверка камеры

```bash
python3 -c "import cv2; print([i for i in range(10) if cv2.VideoCapture(i).isOpened()])"
```

Обновите индекс камеры в `config/settings.yaml` если нужно.

### Шаг 7: Запуск

```bash
python3 src/main.py
```

---

## Тестирование компонентов

Перед полным запуском протестируйте отдельные модули:

```bash
# Тест камеры
python3 scripts/test_components.py camera

# Тест распознавания речи
python3 scripts/test_components.py stt

# Тест синтеза речи
python3 scripts/test_components.py tts

# Тест LLM
python3 scripts/test_components.py llm

# Тест DIKIDI API
python3 scripts/test_components.py dikidi
```

---

## Устранение проблем

### Ollama не запускается

```bash
# Проверьте статус
ollama list

# Перезапустите
sudo systemctl restart ollama  # Linux
```

### Камера не работает

```bash
# Проверьте права доступа (Linux)
sudo usermod -a -G video $USER
# Перезагрузитесь
```

### CUDA ошибки

```bash
# Проверьте CUDA
nvidia-smi

# Переустановите PyTorch с CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Нет звука

```bash
# Проверьте аудио устройства
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

---

## Следующие шаги

1. ✅ Запустили DEMO? → Изучите `docs/ARCHITECTURE.md`
2. ⚙️ Настроили систему? → Прочитайте `docs/API.md`
3. 🔧 Хотите кастомизировать? → См. `config/settings.yaml`
4. 🐛 Нашли баг? → Проверьте логи в `data/logs/`

---

## Полезные команды

```bash
# Просмотр логов в реальном времени
tail -f data/logs/app.log

# Просмотр логов разговоров
tail -f data/logs/conversations.jsonl

# Остановка приложения
# Нажмите Ctrl+C или отправьте SIGTERM

# Очистка логов
rm -rf data/logs/*
```

---

## Поддержка

- 📖 Документация: `docs/`
- 🐛 Issues: GitHub Issues
- 💬 Вопросы: Создайте Discussion
