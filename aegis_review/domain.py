"""Stable domain values shared by backend, CV, frontend, and tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditDecision(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class AuditSettings:
    risk_classes: tuple[str, ...] = ("enemy",)
    reject_confidence: float = 0.60
    review_confidence: float = 0.35
    inference_confidence: float = 0.25
    min_evidence_frames: int = 1
    sample_interval_seconds: float = 1.0
    max_sample_frames: int = 120

    def __post_init__(self) -> None:
        risk_classes = tuple(self.risk_classes)
        object.__setattr__(self, "risk_classes", risk_classes)
        if not risk_classes or any(not value.strip() for value in risk_classes):
            raise ValueError("risk_classes must contain at least one class")
        if not (
            0.0
            <= self.inference_confidence
            <= self.review_confidence
            < self.reject_confidence
            <= 1.0
        ):
            raise ValueError(
                "confidence values must satisfy inference <= review < reject"
            )
        if self.min_evidence_frames < 1:
            raise ValueError("min_evidence_frames must be at least 1")
        if self.sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be positive")
        if not 1 <= self.max_sample_frames <= 120:
            raise ValueError("max_sample_frames must be between 1 and 120")

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_classes": list(self.risk_classes),
            "reject_confidence": self.reject_confidence,
            "review_confidence": self.review_confidence,
            "inference_confidence": self.inference_confidence,
            "min_evidence_frames": self.min_evidence_frames,
            "sample_interval_seconds": self.sample_interval_seconds,
            "max_sample_frames": self.max_sample_frames,
        }


@dataclass(slots=True)
class AnalysisReport:
    job_id: str
    detections: list[dict[str, Any]] = field(default_factory=list)
    evidence_frames: list[str] = field(default_factory=list)
    rules: dict[str, Any] = field(default_factory=dict)
    auto_decision: AuditDecision | None = None
    final_decision: AuditDecision | None = None
    reviewer: str | None = None
    note: str | None = None

    @classmethod
    def new(cls, job_id: str, settings: AuditSettings) -> "AnalysisReport":
        return cls(job_id=job_id, rules=settings.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "detections": self.detections,
            "evidence_frames": self.evidence_frames,
            "rules": self.rules,
            "auto_decision": (
                self.auto_decision.value if self.auto_decision is not None else None
            ),
            "final_decision": (
                self.final_decision.value
                if self.final_decision is not None
                else None
            ),
            "reviewer": self.reviewer,
            "note": self.note,
        }
