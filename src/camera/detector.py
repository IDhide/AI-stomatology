"""
Детекция присутствия человека через камеру
"""
import cv2
import mediapipe as mp
from loguru import logger


class PersonDetector:
    """Детектор присутствия человека"""

    def __init__(self, config):
        self.config = config

        # Инициализация камеры
        self.cap = cv2.VideoCapture(config.device_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.resolution["width"])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.resolution["height"])
        self.cap.set(cv2.CAP_PROP_FPS, config.fps)

        if not self.cap.isOpened():
            raise RuntimeError("Не удалось открыть камеру")

        # Инициализация MediaPipe для детекции лиц
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detection = self.mp_face_detection.FaceDetection(
            model_selection=0,
            min_detection_confidence=config.detection["face_confidence"]
        )

        # Для детекции движения
        self.prev_frame = None
        self.motion_threshold = config.detection["motion_threshold"]

        logger.success("Камера инициализирована")

    def detect_person(self) -> bool:
        """
        Определяет наличие человека перед камерой
        Использует детекцию лица + детекцию движения
        """
        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Не удалось получить кадр с камеры")
            return False

        # Детекция лица
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_detection.process(rgb_frame)

        if results.detections:
            logger.debug(f"Обнаружено лиц: {len(results.detections)}")
            return True

        # Дополнительная детекция движения
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self.prev_frame is None:
            self.prev_frame = gray
            return False

        frame_delta = cv2.absdiff(self.prev_frame, gray)
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        motion_pixels = cv2.countNonZero(thresh)

        self.prev_frame = gray

        # Если много движения - возможно человек
        if motion_pixels > self.motion_threshold * 1000:
            logger.debug(f"Обнаружено движение: {motion_pixels} пикселей")
            return True

        return False

    # Алиас для совместимости со старым кодом
    def detect_presence(self) -> bool:
        return self.detect_person()

    def get_frame(self):
        """Получить текущий кадр с камеры"""
        ret, frame = self.cap.read()
        return frame if ret else None

    def cleanup(self):
        """Освобождение ресурсов"""
        if self.cap:
            self.cap.release()
        logger.info("Камера освобождена")


# Имя, под которым main_offline.py ожидает класс
CameraDetector = PersonDetector
