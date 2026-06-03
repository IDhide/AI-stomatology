# Руководство по установке и настройке

## Системные требования

- **GPU**: NVIDIA RTX 3060 12GB (или аналогичная)
- **ОС**: Linux (Ubuntu 20.04+) или Windows 10/11
- **Python**: 3.10+
- **CUDA**: 11.8+ (для GPU ускорения)
- **Камера**: Xi Camera C200 или совместимая USB камера

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/your-repo/ai-salon-assistant.git
cd ai-salon-assistant
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Установка Ollama

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Mac
brew install ollama

# Windows
# Скачайте с https://ollama.com/download
```

### 5. Загрузка модели OpenClaw

```bash
ollama pull openclaw
```

Для квантизации под RTX 3060 12GB:

```bash
# Создайте Modelfile с квантизацией
cat > Modelfile << EOF
FROM openclaw
PARAMETER num_gpu 1
PARAMETER num_thread 8
PARAMETER num_ctx 4096
EOF

# Создайте квантизованную модель
ollama create openclaw-q4 -f Modelfile
```

## Настройка

### 1. Конфигурация окружения

Скопируйте `.env.example` в `.env`:

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```env
DIKIDI_API_KEY=ваш_api_ключ
DIKIDI_COMPANY_ID=ваш_id_компании
OLLAMA_MODEL=openclaw-q4
```

### 2. Настройка DIKIDI API

1. Зарегистрируйтесь на [DIKIDI](https://dikidi.net)
2. Получите API ключ в личном кабинете
3. Найдите ID вашей компании
4. Добавьте данные в `.env`

### 3. Настройка камеры

Проверьте индекс вашей камеры:

```bash
python -c "import cv2; print([i for i in range(10) if cv2.VideoCapture(i).isOpened()])"
```

Обновите `config/settings.yaml`:

```yaml
camera:
  device_index: 0  # Ваш индекс камеры
```

### 4. Подготовка видео с медузами

Используйте Seedance 2.0 для генерации видео:

1. Создайте видео с медузами (рекомендуется 1920x1080, 30fps)
2. Сохраните как `assets/videos/jellyfish.mp4`

Или используйте готовое видео:

```bash
mkdir -p assets/videos
# Поместите ваше видео в assets/videos/jellyfish.mp4
```

## Запуск

### Тестовый запуск

```bash
python src/main.py
```

### Запуск в фоновом режиме

```bash
nohup python src/main.py > logs/app.log 2>&1 &
```

### Автозапуск при загрузке системы

#### Linux (systemd)

Создайте файл `/etc/systemd/system/salon-assistant.service`:

```ini
[Unit]
Description=AI Salon Assistant
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/ai-salon-assistant
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python src/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Активируйте:

```bash
sudo systemctl enable salon-assistant
sudo systemctl start salon-assistant
```

## Тестирование

### Тест камеры

```bash
python -m tests.test_camera
```

### Тест голоса

```bash
python -m tests.test_voice
```

### Тест DIKIDI API

```bash
python -m tests.test_dikidi
```

## Оптимизация для RTX 3060

### Настройка Whisper

Для оптимальной производительности используйте модель `base`:

```yaml
voice:
  stt:
    model: "base"  # tiny, base, small
    device: "cuda"
```

### Настройка Ollama

Ограничьте использование памяти:

```bash
# В ~/.ollama/config.json
{
  "gpu_memory_fraction": 0.8,
  "num_gpu": 1
}
```

## Устранение неполадок

### Камера не обнаруживается

```bash
# Проверьте права доступа
sudo usermod -a -G video $USER

# Перезагрузитесь
```

### Ошибка CUDA

```bash
# Проверьте установку CUDA
nvidia-smi

# Переустановите PyTorch с CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Ollama не отвечает

```bash
# Перезапустите Ollama
sudo systemctl restart ollama

# Проверьте логи
journalctl -u ollama -f
```

## Дополнительные ресурсы

- [Документация DIKIDI API](https://api.dikidi.net/docs)
- [Ollama Documentation](https://ollama.com/docs)
- [Whisper GitHub](https://github.com/openai/whisper)
- [Silero TTS](https://github.com/snakers4/silero-models)
