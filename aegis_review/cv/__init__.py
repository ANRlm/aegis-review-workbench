"""CV subsystem namespace owned by the CV engineer."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from aegis_review.cv.detector import Detector, UltralyticsDetector, clear_model_cache
from aegis_review.cv.pipeline import analyze_asset
from aegis_review.cv.rules import decide_audit
from aegis_review.cv.sampler import sample_media
from aegis_review.domain import AnalysisReport, AuditSettings


def bind_analyzer(
    detector: Detector | None = None,
    *,
    model_path: Path | str | None = None,
):
    """Return a 4-arg AnalysisRunner compatible with JobService."""
    if detector is None:
        if model_path is None:
            raise ValueError("detector or model_path is required")
        detector = UltralyticsDetector(model_path)
    return partial(analyze_asset, detector=detector)


__all__ = [
    "AnalysisReport",
    "AuditSettings",
    "Detector",
    "UltralyticsDetector",
    "analyze_asset",
    "bind_analyzer",
    "clear_model_cache",
    "decide_audit",
    "sample_media",
]
