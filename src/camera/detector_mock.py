"""
Mock версия детектора для тестирования без камеры
"""
import random
from loguru import logger


class PersonDetector:
    """Mock детектор присутствия человека"""
    
    def __init__(self, config):
        self.config = config
        self.detection_probability = 0.1  # 10% шанс "обнаружить" человека
        logger.success("Mock камера инициализирована (без реальной камеры)")
    
    def detect_person(self) -> bool:
        """
        Симулирует детекцию человека
        """
        # Случайная детекция для демонстрации
        return random.random() < self.detection_probability
    
    def get_frame(self):
        """Получить текущий кадр с камеры"""
        return None
    
    def cleanup(self):
        """Освобождение ресурсов"""
        logger.info("Mock камера освобождена")
