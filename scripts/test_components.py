#!/usr/bin/env python3
"""
Скрипт для тестирования отдельных компонентов системы
"""
import asyncio
import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.config import load_config
from loguru import logger


async def test_camera():
    """Тест камеры и детекции"""
    logger.info("🎥 Тестирование камеры...")
    
    try:
        from camera.detector import PersonDetector
        
        config = load_config()
        detector = PersonDetector(config.camera)
        
        logger.info("Проверка детекции (5 секунд)...")
        for i in range(50):
            is_detected = detector.detect_person()
            if is_detected:
                logger.success("✅ Человек обнаружен!")
            await asyncio.sleep(0.1)
        
        detector.cleanup()
        logger.success("✅ Тест камеры пройден")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста камеры: {e}")
        return False


async def test_stt():
    """Тест распознавания речи"""
    logger.info("🎤 Тестирование STT...")
    
    try:
        from voice.stt import SpeechToText
        
        config = load_config()
        stt = SpeechToText(config.voice.stt)
        
        logger.info("Скажите что-нибудь (10 секунд)...")
        text = await stt.listen(timeout=10)
        
        if text:
            logger.success(f"✅ Распознано: {text}")
            return True
        else:
            logger.warning("⚠️  Ничего не распознано")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка теста STT: {e}")
        return False


async def test_tts():
    """Тест синтеза речи"""
    logger.info("🔊 Тестирование TTS...")
    
    try:
        from voice.tts import TextToSpeech
        
        config = load_config()
        tts = TextToSpeech(config.voice.tts)
        
        test_text = "Здравствуйте! Это тест синтеза речи."
        logger.info(f"Произношу: {test_text}")
        
        await tts.speak(test_text)
        
        logger.success("✅ Тест TTS пройден")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста TTS: {e}")
        return False


async def test_llm():
    """Тест LLM"""
    logger.info("🤖 Тестирование LLM...")
    
    try:
        from llm.assistant import LLMAssistant
        from dikidi.client import DikidiClient
        
        config = load_config()
        llm = LLMAssistant(config.llm)
        dikidi = DikidiClient(config.dikidi)
        
        test_message = "Здравствуйте, какие у вас есть услуги?"
        logger.info(f"Запрос: {test_message}")
        
        response = await llm.get_response(test_message, dikidi)
        logger.success(f"✅ Ответ: {response}")
        
        await dikidi.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста LLM: {e}")
        return False


async def test_dikidi():
    """Тест DIKIDI API"""
    logger.info("📅 Тестирование DIKIDI API...")
    
    try:
        from dikidi.client import DikidiClient
        
        config = load_config()
        dikidi = DikidiClient(config.dikidi)
        
        # Тест получения услуг
        services = await dikidi.get_services()
        logger.info(f"Получено услуг: {len(services)}")
        
        # Тест получения мастеров
        masters = await dikidi.get_masters()
        logger.info(f"Получено мастеров: {len(masters)}")
        
        # Тест получения слотов
        slots = await dikidi.get_available_slots()
        logger.info(f"Получено слотов: {len(slots)}")
        
        await dikidi.close()
        logger.success("✅ Тест DIKIDI API пройден")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста DIKIDI: {e}")
        return False


async def main():
    """Главная функция"""
    print("=" * 50)
    print("Тестирование компонентов AI Salon Assistant")
    print("=" * 50)
    print()
    
    tests = {
        "camera": test_camera,
        "stt": test_stt,
        "tts": test_tts,
        "llm": test_llm,
        "dikidi": test_dikidi
    }
    
    # Выбор теста
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name in tests:
            await tests[test_name]()
        else:
            print(f"Неизвестный тест: {test_name}")
            print(f"Доступные тесты: {', '.join(tests.keys())}")
    else:
        # Запуск всех тестов
        results = {}
        for name, test_func in tests.items():
            print()
            results[name] = await test_func()
            print()
        
        # Итоги
        print("=" * 50)
        print("Результаты тестирования:")
        print("=" * 50)
        for name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{name:15} {status}")


if __name__ == "__main__":
    asyncio.run(main())
