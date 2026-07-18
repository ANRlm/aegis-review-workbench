"""Pure audit decision rules for detection lists."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aegis_review.domain import AuditDecision, AuditSettings


def _as_float(value: Any) -> float:
    return float(value)


def max_risk_confidence(
    detections: Sequence[Mapping[str, Any]],
    risk_classes: Sequence[str],
) -> float:
    """Return the highest confidence among risk-class detections, else 0.0."""
    risk = set(risk_classes)
    peak = 0.0
    for detection in detections:
        if detection.get("class_name") not in risk:
            continue
        peak = max(peak, _as_float(detection["confidence"]))
    return peak


def low_confidence_risk_frame_ratio(
    detections: Sequence[Mapping[str, Any]],
    sampled_frame_count: int,
    settings: AuditSettings,
) -> float:
    """Fraction of sampled frames with risk conf in [inference, review)."""
    if sampled_frame_count <= 0:
        return 0.0

    risk = set(settings.risk_classes)
    frame_peaks: dict[int, float] = {}
    for detection in detections:
        if detection.get("class_name") not in risk:
            continue
        frame_index = int(detection["frame_index"])
        confidence = _as_float(detection["confidence"])
        previous = frame_peaks.get(frame_index, 0.0)
        if confidence > previous:
            frame_peaks[frame_index] = confidence

    low_frames = sum(
        1
        for confidence in frame_peaks.values()
        if settings.inference_confidence <= confidence < settings.review_confidence
    )
    return low_frames / sampled_frame_count


def decide_audit(
    detections: Sequence[Mapping[str, Any]],
    sampled_frame_count: int,
    settings: AuditSettings,
) -> AuditDecision:
    """Apply the fixed four-step short-circuit audit policy."""
    peak = max_risk_confidence(detections, settings.risk_classes)
    if peak >= settings.reject_confidence:
        return AuditDecision.REJECT
    if settings.review_confidence <= peak < settings.reject_confidence:
        return AuditDecision.REVIEW

    ratio = low_confidence_risk_frame_ratio(
        detections,
        sampled_frame_count,
        settings,
    )
    if 0.20 < ratio < 0.80:
        return AuditDecision.REVIEW
    return AuditDecision.PASS
