"""
Распознавание лиц через InsightFace (buffalo_l).

Даёт эмбеддинг лица (512-мерный вектор) по кадру с камеры. Вектор потом
уходит в MemoryStore.match_face() для поиска в pgvector.

Тяжёлая зависимость (onnxruntime + модели ~300 МБ) грузится лениво: если
insightface не установлен — модуль импортируется, но recognizer выключен,
и система работает без персонализации.
"""
from __future__ import annotations

import numpy as np
from loguru import logger

try:
    from insightface.app import FaceAnalysis

    HAVE_INSIGHTFACE = True
except ImportError:  # pragma: no cover
    HAVE_INSIGHTFACE = False
    FaceAnalysis = None  # type: ignore


class FaceRecognizer:
    def __init__(self, model_name: str = "buffalo_l", det_size: int = 640):
        self.app = None
        if not HAVE_INSIGHTFACE:
            logger.warning("insightface не установлен — распознавание лиц выключено")
            return
        try:
            self.app = FaceAnalysis(name=model_name)
            self.app.prepare(ctx_id=0, det_size=(det_size, det_size))
            logger.success(f"FaceRecognizer готов: {model_name}")
        except Exception as e:
            logger.error(f"InsightFace init: {e}")
            self.app = None

    @property
    def enabled(self) -> bool:
        return self.app is not None

    def embed(self, image_bgr: np.ndarray) -> list[float] | None:
        """
        Возвращает нормализованный эмбеддинг самого крупного лица в кадре
        или None, если лица нет. image_bgr — HxWx3 uint8 (как отдаёт OpenCV).
        """
        if not self.app:
            return None
        faces = self.app.get(image_bgr)
        if not faces:
            return None
        # берём самое крупное лицо (ближайшего человека)
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        emb = face.normed_embedding  # уже L2-нормализован → удобно для косинуса
        return emb.astype(np.float32).tolist()
