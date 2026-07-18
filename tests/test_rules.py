from __future__ import annotations

import pytest

from aegis_review.cv.rules import decide_audit, low_confidence_risk_frame_ratio
from aegis_review.domain import AuditDecision, AuditSettings


def _enemy(frame: int, confidence: float) -> dict:
    return {
        "frame_index": frame,
        "timestamp_seconds": float(frame),
        "class_id": 1,
        "class_name": "enemy",
        "confidence": confidence,
        "bbox_xyxy": [1.0, 2.0, 3.0, 4.0],
        "evidence_file": "frame_000000.jpg",
    }


def test_reject_at_and_above_0_60() -> None:
    settings = AuditSettings()
    assert (
        decide_audit([_enemy(0, 0.60)], sampled_frame_count=1, settings=settings)
        is AuditDecision.REJECT
    )
    assert (
        decide_audit([_enemy(0, 0.99)], sampled_frame_count=1, settings=settings)
        is AuditDecision.REJECT
    )


def test_review_at_0_35_and_below_0_60() -> None:
    settings = AuditSettings()
    assert (
        decide_audit([_enemy(0, 0.35)], sampled_frame_count=1, settings=settings)
        is AuditDecision.REVIEW
    )
    assert (
        decide_audit([_enemy(0, 0.599)], sampled_frame_count=1, settings=settings)
        is AuditDecision.REVIEW
    )


def test_pass_when_peak_below_0_35_and_ratio_outside_open_interval() -> None:
    settings = AuditSettings()
    # Exactly 1/5 = 0.20 low-confidence risk frames → not in (0.20, 0.80)
    detections = [_enemy(0, 0.30)]
    assert (
        decide_audit(detections, sampled_frame_count=5, settings=settings)
        is AuditDecision.PASS
    )


def test_ratio_exactly_0_20_does_not_trigger_review() -> None:
    settings = AuditSettings()
    detections = [_enemy(0, 0.30)]
    ratio = low_confidence_risk_frame_ratio(detections, 5, settings)
    assert ratio == pytest.approx(0.20)
    assert decide_audit(detections, 5, settings) is AuditDecision.PASS


def test_ratio_exactly_0_80_does_not_trigger_review() -> None:
    settings = AuditSettings()
    detections = [_enemy(index, 0.30) for index in range(4)]
    ratio = low_confidence_risk_frame_ratio(detections, 5, settings)
    assert ratio == pytest.approx(0.80)
    assert decide_audit(detections, 5, settings) is AuditDecision.PASS


def test_ratio_strictly_between_0_20_and_0_80_is_review() -> None:
    settings = AuditSettings()
    detections = [_enemy(0, 0.30), _enemy(1, 0.28)]
    ratio = low_confidence_risk_frame_ratio(detections, 5, settings)
    assert 0.20 < ratio < 0.80
    assert decide_audit(detections, 5, settings) is AuditDecision.REVIEW


def test_just_below_0_35_uses_ratio_path_not_band_review() -> None:
    settings = AuditSettings()
    detections = [_enemy(0, 0.349)]
    # One frame of five → 0.20 → pass
    assert decide_audit(detections, 5, settings) is AuditDecision.PASS


def test_non_risk_classes_do_not_trigger_reject() -> None:
    settings = AuditSettings()
    detections = [
        {
            "frame_index": 0,
            "timestamp_seconds": 0.0,
            "class_id": 0,
            "class_name": "player",
            "confidence": 0.99,
            "bbox_xyxy": [0.0, 0.0, 1.0, 1.0],
            "evidence_file": "frame_000000.jpg",
        }
    ]
    assert decide_audit(detections, 1, settings) is AuditDecision.PASS
