"""Stable domain values shared by backend, CV, frontend, and tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from typing import Any, BinaryIO


JOB_ID_PATTERN = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}$")
EXTENSION_PATTERN = re.compile(r"^[a-z0-9]+$")


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


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


SUPPORTED_MEDIA_EXTENSIONS: dict[MediaType, frozenset[str]] = {
    MediaType.IMAGE: frozenset({"jpg", "jpeg", "png"}),
    MediaType.VIDEO: frozenset({"mp4", "mov"}),
}


def _require_basename(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
    ):
        raise ValueError(f"{field_name} must be a safe basename")
    return value


def _validate_timestamp(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"{field_name} must be an ISO 8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


@dataclass(slots=True)
class AssetInput:
    original_name: str
    extension: str
    media_type: MediaType
    stream: BinaryIO

    def __post_init__(self) -> None:
        if not isinstance(self.original_name, str) or not self.original_name.strip():
            raise ValueError("original_name must not be empty")
        if not isinstance(self.extension, str) or not EXTENSION_PATTERN.fullmatch(
            self.extension
        ):
            raise ValueError("extension must be lowercase and contain no dot")
        try:
            self.media_type = MediaType(self.media_type)
        except ValueError as error:
            raise ValueError("media_type must be image or video") from error
        if not callable(getattr(self.stream, "read", None)) or not callable(
            getattr(self.stream, "seek", None)
        ):
            raise TypeError("stream must be a seekable binary stream")


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
        if not isinstance(self.risk_classes, (list, tuple)):
            raise ValueError("risk_classes must be a list or tuple")
        risk_classes = tuple(self.risk_classes)
        object.__setattr__(self, "risk_classes", risk_classes)
        if not risk_classes or any(
            not isinstance(value, str) or not value.strip()
            for value in risk_classes
        ):
            raise ValueError("risk_classes must contain at least one class")
        confidence_values = (
            self.reject_confidence,
            self.review_confidence,
            self.inference_confidence,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in confidence_values
        ):
            raise ValueError("confidence values must be numbers")
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
        if (
            isinstance(self.min_evidence_frames, bool)
            or not isinstance(self.min_evidence_frames, int)
            or self.min_evidence_frames < 1
        ):
            raise ValueError("min_evidence_frames must be at least 1")
        if (
            isinstance(self.sample_interval_seconds, bool)
            or not isinstance(self.sample_interval_seconds, (int, float))
            or self.sample_interval_seconds <= 0
        ):
            raise ValueError("sample_interval_seconds must be positive")
        if (
            isinstance(self.max_sample_frames, bool)
            or not isinstance(self.max_sample_frames, int)
            or not 1 <= self.max_sample_frames <= 120
        ):
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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuditSettings":
        if not isinstance(payload, dict):
            raise ValueError("settings must be a JSON object")
        expected = {
            "risk_classes",
            "reject_confidence",
            "review_confidence",
            "inference_confidence",
            "min_evidence_frames",
            "sample_interval_seconds",
            "max_sample_frames",
        }
        if set(payload) != expected:
            raise ValueError("settings fields do not match the contract")
        return cls(**payload)


@dataclass(slots=True)
class JobRecord:
    job_id: str
    project_name: str
    asset_name: str
    asset_type: MediaType
    asset_file: str
    status: JobStatus
    created_at: str
    started_at: str | None
    completed_at: str | None
    settings: dict[str, Any]
    result_file: str | None
    error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, str) or not JOB_ID_PATTERN.fullmatch(
            self.job_id
        ):
            raise ValueError("job_id does not match the published format")
        if (
            not isinstance(self.project_name, str)
            or not 1 <= len(self.project_name.strip()) <= 80
        ):
            raise ValueError("project_name must contain between 1 and 80 characters")
        self.project_name = self.project_name.strip()
        if not isinstance(self.asset_name, str) or not self.asset_name.strip():
            raise ValueError("asset_name must not be empty")
        try:
            self.asset_type = MediaType(self.asset_type)
        except ValueError as error:
            raise ValueError("asset_type must be image or video") from error
        self.asset_file = _require_basename(self.asset_file, "asset_file")
        try:
            self.status = JobStatus(self.status)
        except ValueError as error:
            raise ValueError("status does not match the job contract") from error
        _validate_timestamp(self.created_at, "created_at")
        _validate_timestamp(self.started_at, "started_at")
        _validate_timestamp(self.completed_at, "completed_at")
        self.settings = AuditSettings.from_dict(self.settings).to_dict()
        if self.result_file is not None:
            self.result_file = _require_basename(
                self.result_file,
                "result_file",
            )
        if self.error is not None and not isinstance(self.error, str):
            raise ValueError("error must be a string or null")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobRecord":
        if not isinstance(payload, dict):
            raise ValueError("job record must be a JSON object")
        expected = {
            "job_id",
            "project_name",
            "asset_name",
            "asset_type",
            "asset_file",
            "status",
            "created_at",
            "started_at",
            "completed_at",
            "settings",
            "result_file",
            "error",
        }
        if set(payload) != expected:
            raise ValueError("job record fields do not match the contract")
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_name": self.project_name,
            "asset_name": self.asset_name,
            "asset_type": self.asset_type.value,
            "asset_file": self.asset_file,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "settings": dict(self.settings),
            "result_file": self.result_file,
            "error": self.error,
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
    downloads: dict[str, str] = field(default_factory=dict)

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
            "downloads": dict(self.downloads),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AnalysisReport":
        if not isinstance(payload, dict):
            raise ValueError("analysis report must be a JSON object")
        expected = {
            "job_id",
            "detections",
            "evidence_frames",
            "rules",
            "auto_decision",
            "final_decision",
            "reviewer",
            "note",
            "downloads",
        }
        if set(payload) != expected:
            raise ValueError("analysis report fields do not match the contract")
        if not isinstance(payload["job_id"], str):
            raise ValueError("analysis report job_id must be a string")
        if not isinstance(payload["detections"], list) or any(
            not isinstance(detection, dict)
            for detection in payload["detections"]
        ):
            raise ValueError("analysis report detections must be a list of objects")
        if not isinstance(payload["evidence_frames"], list) or any(
            not isinstance(filename, str)
            for filename in payload["evidence_frames"]
        ):
            raise ValueError(
                "analysis report evidence_frames must be a list of strings"
            )
        if not isinstance(payload["rules"], dict):
            raise ValueError("analysis report rules must be an object")
        if (
            payload["reviewer"] is not None
            and not isinstance(payload["reviewer"], str)
        ):
            raise ValueError("analysis report reviewer must be a string or null")
        if payload["note"] is not None and not isinstance(payload["note"], str):
            raise ValueError("analysis report note must be a string or null")
        if not isinstance(payload["downloads"], dict) or any(
            not isinstance(label, str) or not isinstance(filename, str)
            for label, filename in payload["downloads"].items()
        ):
            raise ValueError("analysis report downloads must map strings to strings")
        auto_decision = payload["auto_decision"]
        final_decision = payload["final_decision"]
        return cls(
            job_id=payload["job_id"],
            detections=list(payload["detections"]),
            evidence_frames=list(payload["evidence_frames"]),
            rules=dict(payload["rules"]),
            auto_decision=(
                AuditDecision(auto_decision)
                if auto_decision is not None
                else None
            ),
            final_decision=(
                AuditDecision(final_decision)
                if final_decision is not None
                else None
            ),
            reviewer=payload["reviewer"],
            note=payload["note"],
            downloads=dict(payload["downloads"]),
        )
