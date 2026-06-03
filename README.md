# AI Администратор Салона Красоты

Голосовой AI-ассистент для автоматизации записи клиентов через DIKIDI API с детекцией присутствия и анимированным интерфейсом.

## ✨ Возможности

- 🎥 Автоматическое включение при обнаружении человека (Xi Camera C200)
- 🗣️ Голосовое общение на русском языке (Whisper STT + TTS)
- 📅 Интеграция с DIKIDI API (запись, поиск клиента, свободные окна)
- 🎨 Анимированный интерфейс (пульсирующий круг + видео с медузами)
- 💾 Логирование всех разговоров
- 👋 Автоматическое приветствие и прощание

## 🚀 Быстрый старт (DEMO режим)

Для первого запуска используйте демо версию без установки тяжелых зависимостей:

```bash
# 1. Установите минимальные зависимости
pip3 install -r requirements-minimal.txt

# 2. Создайте .env файл
cp .env.example .env

# 3. Запустите DEMO
python3 src/main_demo.py
```

**DEMO режим** использует mock модули и симулирует работу системы без:
- Реальной камеры
- Ollama/LLM
- Whisper STT
- Silero TTS
- Pygame UI
- DIKIDI API

Это позволяет увидеть логику работы системы и структуру проекта.

## 📦 Полная установка

Для работы с реальным оборудованием:

```bash
# 1. Установите все зависимости
pip3 install -r requirements.txt

# 2. Установите Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 3. Загрузите модель
ollama pull openclaw

# 4. Настройте .env
cp .env.example .env
# Заполните DIKIDI_API_KEY и DIKIDI_COMPANY_ID

# 5. Добавьте видео с медузами
# Поместите в assets/videos/jellyfish.mp4

# 6. Запустите
python3 src/main.py
```

## 🏗️ Технологический стек

- **LLM**: Ollama + OpenClaw (квантизация для RTX 3060 12GB)
- **STT**: Whisper (распознавание речи)
- **TTS**: Silero TTS (русский синтез речи)
- **Камера**: Xi Camera C200 (детекция движения/лица через MediaPipe)
- **API**: DIKIDI REST API
- **Визуализация**: Pygame + OpenCV (видео с медузами)
- **Backend**: Python 3.10+

## 📁 Структура проекта

```
ai-salon-assistant/
├── src/
│   ├── main.py                    # Полная версия
│   ├── main_demo.py               # DEMO версия
│   ├── core/                      # Ядро приложения
│   ├── camera/                    # Детекция (+ mock)
│   ├── voice/                     # STT/TTS (+ mock)
│   ├── llm/                       # LLM (+ mock)
│   ├── dikidi/                    # DIKIDI API (+ mock)
│   └── ui/                        # UI (+ mock)
├── config/
│   └── settings.yaml              # Конфигурация
├── docs/                          # Документация
│   ├── SETUP.md                   # Установка
│   ├── API.md                     # API документация
│   └── ARCHITECTURE.md            # Архитектура
├── scripts/
│   ├── install.sh                 # Автоустановка
│   └── test_components.py         # Тесты
├── requirements.txt               # Полные зависимости
├── requirements-minimal.txt       # Минимальные зависимости
└── .env.example                   # Пример конфигурации
```

## 🎯 Режимы работы

### 1. DEMO режим (рекомендуется для начала)
```bash
python3 src/main_demo.py
```
- Без реального оборудования
- Mock модули для симуляции
- Быстрый запуск
- Демонстрация логики работы

### 2. Полный режим
```bash
python3 src/main.py
```
- Реальная камера
- Ollama LLM
- Whisper + Silero
- DIKIDI API
- Полный UI

## 📊 Пример вывода DEMO

```
🚀 AI Администратор Салона Красоты - DEMO РЕЖИМ
============================================================

💤 Режим ожидания (показываем медуз)...
👤 [DEMO] Симулируем появление клиента
🔍 Подтверждение присутствия...
✅ Присутствие подтверждено
🗣️ Приветствие: Здравствуйте! Я виртуальный администратор салона...
👤 Клиент: Здравствуйте, хочу записаться на маникюр
🤖 Ассистент: Конечно! У нас есть классический маникюр за 1500 рублей...
```

## 📖 Документация

- [Руководство по установке](docs/SETUP.md)
- [API документация](docs/API.md)
- [Архитектура системы](docs/ARCHITECTURE.md)

## 🔧 Конфигурация

Основные настройки в `config/settings.yaml`:
- Параметры камеры и детекции
- Настройки голоса (STT/TTS)
- Конфигурация LLM
- DIKIDI API
- Таймауты и пороги

Секреты в `.env`:
- `DIKIDI_API_KEY` - API ключ DIKIDI
- `DIKIDI_COMPANY_ID` - ID компании
- `OLLAMA_MODEL` - Модель LLM

## 🧪 Тестирование

```bash
# Все компоненты
python3 scripts/test_components.py

# Отдельные модули
python3 scripts/test_components.py camera
python3 scripts/test_components.py stt
python3 scripts/test_components.py llm
```

## 📝 Логи

Все разговоры логируются в `data/logs/conversations.jsonl` в формате:

```json
{"conversation_id": "uuid", "event": "start", "timestamp": "2024-03-20T10:00:00"}
{"conversation_id": "uuid", "event": "message", "role": "user", "content": "...", "timestamp": "..."}
{"conversation_id": "uuid", "event": "message", "role": "assistant", "content": "...", "timestamp": "..."}
{"conversation_id": "uuid", "event": "end", "timestamp": "2024-03-20T10:05:00"}
```

## 🎓 Следующие шаги

1. ✅ Запустите DEMO режим для ознакомления
2. 📚 Изучите документацию в `docs/`
3. ⚙️ Установите Ollama и зависимости
4. 🔑 Получите DIKIDI API ключи
5. 🎥 Подключите камеру
6. 🚀 Запустите полную версию

## 💡 Оптимизация для RTX 3060 12GB

- Whisper модель: `base` (оптимальный баланс)
- Ollama: квантизация Q4
- GPU memory management настроен
- Подробности в `docs/SETUP.md`
