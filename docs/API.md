# API Документация

## DIKIDI API Integration

### Основные методы

#### Получение свободных слотов

```python
slots = await dikidi_client.get_available_slots(
    service_id=123,
    master_id=456,
    days_ahead=7
)
```

**Параметры:**
- `service_id` (int, optional): ID услуги
- `master_id` (int, optional): ID мастера
- `days_ahead` (int): Количество дней вперед

**Возвращает:** Список словарей со слотами

#### Создание записи

```python
booking = await dikidi_client.create_booking(
    client_name="Иван Иванов",
    client_phone="+79991234567",
    service_id=123,
    master_id=456,
    datetime_str="2024-03-20T14:00:00"
)
```

**Параметры:**
- `client_name` (str): Имя клиента
- `client_phone` (str): Телефон клиента
- `service_id` (int): ID услуги
- `master_id` (int): ID мастера
- `datetime_str` (str): Дата и время в ISO формате

**Возвращает:** Данные созданной записи или None

#### Поиск клиента

```python
client = await dikidi_client.find_client(phone="+79991234567")
```

**Параметры:**
- `phone` (str): Номер телефона

**Возвращает:** Данные клиента или None

#### Получение услуг

```python
services = await dikidi_client.get_services()
```

**Возвращает:** Список услуг компании

#### Получение мастеров

```python
masters = await dikidi_client.get_masters()
```

**Возвращает:** Список мастеров

## Внутренние модули

### PersonDetector

Детекция присутствия человека через камеру.

```python
from camera.detector import PersonDetector

detector = PersonDetector(config.camera)
is_present = detector.detect_person()
```

**Методы:**
- `detect_person()`: Возвращает True если человек обнаружен
- `get_frame()`: Возвращает текущий кадр с камеры
- `cleanup()`: Освобождение ресурсов

### SpeechToText

Распознавание речи через Whisper.

```python
from voice.stt import SpeechToText

stt = SpeechToText(config.voice.stt)
text = await stt.listen(timeout=30)
```

**Методы:**
- `listen(timeout)`: Слушает и возвращает распознанный текст

### TextToSpeech

Синтез речи на русском языке.

```python
from voice.tts import TextToSpeech

tts = TextToSpeech(config.voice.tts)
await tts.speak("Здравствуйте!", ui_display)
```

**Методы:**
- `speak(text, ui_display)`: Произносит текст с анимацией

### LLMAssistant

Интеграция с Ollama для генерации ответов.

```python
from llm.assistant import LLMAssistant

llm = LLMAssistant(config.llm)
response = await llm.get_response(user_message, dikidi_client)
```

**Методы:**
- `get_response(message, dikidi_client)`: Получить ответ от LLM
- `reset_conversation()`: Сброс истории разговора

### UIDisplay

Визуальный интерфейс с анимацией.

```python
from ui.display import UIDisplay

ui = UIDisplay(config.ui)
ui.set_mode("speaking")  # idle, listening, thinking, speaking
```

**Методы:**
- `set_mode(mode)`: Установка режима отображения
- `start_speaking_animation()`: Запуск анимации речи
- `stop_speaking_animation()`: Остановка анимации
- `cleanup()`: Освобождение ресурсов

### ConversationLogger

Логирование разговоров.

```python
from core.conversation_logger import ConversationLogger

logger = ConversationLogger(config.logging.conversations)
conv_id = logger.start_conversation()
logger.log_message(conv_id, "user", "Привет")
logger.log_message(conv_id, "assistant", "Здравствуйте!")
logger.end_conversation(conv_id)
```

**Методы:**
- `start_conversation()`: Начало новой беседы
- `log_message(conv_id, role, content)`: Логирование сообщения
- `end_conversation(conv_id)`: Завершение беседы

## Состояния приложения

```python
class AppState(Enum):
    IDLE = "idle"              # Режим ожидания (медузы)
    DETECTING = "detecting"    # Обнаружен человек
    GREETING = "greeting"      # Приветствие
    CONVERSATION = "conversation"  # Разговор
    GOODBYE = "goodbye"        # Прощание
```

## Формат логов разговоров

Логи сохраняются в JSONL формате:

```json
{"conversation_id": "uuid", "event": "start", "timestamp": "2024-03-20T10:00:00"}
{"conversation_id": "uuid", "event": "message", "role": "user", "content": "Привет", "timestamp": "2024-03-20T10:00:05"}
{"conversation_id": "uuid", "event": "message", "role": "assistant", "content": "Здравствуйте!", "timestamp": "2024-03-20T10:00:07"}
{"conversation_id": "uuid", "event": "end", "timestamp": "2024-03-20T10:05:00"}
```
