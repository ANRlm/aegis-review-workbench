"""Ultralytics YOLO detector adapter with single-model caching."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Protocol

import numpy as np

from aegis_review.cv.classes import CLASS_NAMES
from aegis_review.cv.exceptions import InferenceError, ModelMissingError


class Detector(Protocol):
    def detect(
        self,
        frame: np.ndarray,
        confidence: float,
    ) -> list[dict[str, Any]]:
        """Return JSON-native detection dicts for one BGR frame."""


_MODEL_CACHE: dict[str, Any] = {}
_CACHE_LOCK = Lock()


def _to_float(value: Any) -> float:
    if hasattr(value, "item"):
        value = value.item()
    return float(value)


def _to_int(value: Any) -> int:
    if hasattr(value, "item"):
        value = value.item()
    return int(value)


def clip_bbox_xyxy(
    bbox: tuple[float, float, float, float] | list[float],
    width: int,
    height: int,
) -> list[float]:
    x1, y1, x2, y2 = (_to_float(v) for v in bbox)
    x1 = min(max(0.0, x1), float(width))
    x2 = min(max(0.0, x2), float(width))
    y1 = min(max(0.0, y1), float(height))
    y2 = min(max(0.0, y2), float(height))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return [x1, y1, x2, y2]


class UltralyticsDetector:
    """Load one YOLO weight and convert Results into plain Python dicts."""

    def __init__(self, model_path: Path | str) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise ModelMissingError(
                f"模型文件不存在：{self.model_path.name}。"
            )
        self._model = self._load_cached(self.model_path)

    @staticmethod
    def _load_cached(model_path: Path) -> Any:
        key = str(model_path.resolve())
        with _CACHE_LOCK:
            cached = _MODEL_CACHE.get(key)
            if cached is not None:
                return cached
            try:
                from ultralytics import YOLO
            except Exception as error:  # pragma: no cover - import env issue
                raise InferenceError("无法导入 Ultralytics YOLO。") from error
            try:
                model = YOLO(str(model_path))
            except Exception as error:
                raise InferenceError(
                    f"无法加载模型：{model_path.name}。"
                ) from error
            _MODEL_CACHE[key] = model
            return model

    def detect(
        self,
        frame: np.ndarray,
        confidence: float,
    ) -> list[dict[str, Any]]:
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            raise InferenceError("推理输入帧无效。")
        height, width = frame.shape[:2]
        try:
            results = self._model.predict(
                source=frame,
                conf=float(confidence),
                verbose=False,
            )
        except Exception as error:
            raise InferenceError("模型推理失败。") from error

        detections: list[dict[str, Any]] = []
        if not results:
            return detections
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return detections

        for box in boxes:
            class_id = _to_int(box.cls[0])
            if 0 <= class_id < len(CLASS_NAMES):
                class_name = CLASS_NAMES[class_id]
            else:
                names = getattr(result, "names", {}) or {}
                class_name = str(names.get(class_id, f"class_{class_id}"))
            xyxy = box.xyxy[0].tolist()
            detections.append(
                {
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": _to_float(box.conf[0]),
                    "bbox_xyxy": clip_bbox_xyxy(xyxy, width, height),
                }
            )
        return detections


def clear_model_cache() -> None:
    """Test helper to drop cached YOLO instances."""
    with _CACHE_LOCK:
        _MODEL_CACHE.clear()
