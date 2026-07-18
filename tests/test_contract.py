from __future__ import annotations

from pathlib import Path

import pytest

from aegis_review import create_app
from aegis_review.config import AppConfig
from aegis_review.domain import AnalysisReport, AuditDecision, AuditSettings, JobStatus
from aegis_review.service import InvalidStatusTransition, validate_transition
from aegis_review.storage import atomic_write_json, read_json


def test_health_exposes_service_and_dependency_readiness(tmp_path: Path) -> None:
    config = AppConfig(project_root=tmp_path, testing=True)
    app = create_app(config)

    response = app.test_client().get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["model_ready"] is False
    assert isinstance(payload["ffmpeg_ready"], bool)
    assert payload["storage_ready"] is True


def test_unknown_api_route_uses_structured_error_contract(tmp_path: Path) -> None:
    app = create_app(AppConfig(project_root=tmp_path, testing=True))

    response = app.test_client().get("/api/not-a-route")

    assert response.status_code == 404
    assert response.get_json() == {
        "ok": False,
        "error": {
            "code": "not_found",
            "message": "请求的接口不存在。",
        },
    }


def test_domain_enums_match_the_published_contract() -> None:
    assert [status.value for status in JobStatus] == [
        "created",
        "queued",
        "running",
        "completed",
        "failed",
    ]
    assert [decision.value for decision in AuditDecision] == [
        "pass",
        "review",
        "reject",
    ]


def test_default_audit_settings_match_the_api_contract() -> None:
    settings = AuditSettings()

    assert settings.to_dict() == {
        "risk_classes": ["enemy"],
        "reject_confidence": 0.60,
        "review_confidence": 0.35,
        "inference_confidence": 0.25,
        "min_evidence_frames": 1,
        "sample_interval_seconds": 1.0,
        "max_sample_frames": 120,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"risk_classes": []}, "risk_classes"),
        ({"inference_confidence": 0.36}, "confidence"),
        ({"review_confidence": 0.60}, "confidence"),
        ({"min_evidence_frames": 0}, "min_evidence_frames"),
        ({"sample_interval_seconds": 0}, "sample_interval_seconds"),
        ({"max_sample_frames": 121}, "max_sample_frames"),
    ],
)
def test_invalid_audit_settings_are_rejected(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        AuditSettings(**overrides)


def test_analysis_report_serializes_stable_contract() -> None:
    report = AnalysisReport.new(
        job_id="20260718_101530_a1b2c3d4",
        settings=AuditSettings(),
    )

    assert report.to_dict() == {
        "job_id": "20260718_101530_a1b2c3d4",
        "detections": [],
        "evidence_frames": [],
        "rules": AuditSettings().to_dict(),
        "auto_decision": None,
        "final_decision": None,
        "reviewer": None,
        "note": None,
        "downloads": {},
    }


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobStatus.CREATED, JobStatus.QUEUED),
        (JobStatus.QUEUED, JobStatus.RUNNING),
        (JobStatus.QUEUED, JobStatus.FAILED),
        (JobStatus.RUNNING, JobStatus.COMPLETED),
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.FAILED, JobStatus.QUEUED),
    ],
)
def test_valid_status_transitions_are_accepted(
    current: JobStatus, target: JobStatus
) -> None:
    validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobStatus.CREATED, JobStatus.COMPLETED),
        (JobStatus.QUEUED, JobStatus.COMPLETED),
        (JobStatus.COMPLETED, JobStatus.RUNNING),
        (JobStatus.FAILED, JobStatus.COMPLETED),
    ],
)
def test_invalid_status_transitions_are_rejected(
    current: JobStatus, target: JobStatus
) -> None:
    with pytest.raises(InvalidStatusTransition):
        validate_transition(current, target)


def test_atomic_json_storage_round_trip(tmp_path: Path) -> None:
    destination = tmp_path / "outputs" / "job-id" / "job.json"
    payload = {"job_id": "job-id", "status": "created", "error": None}

    atomic_write_json(destination, payload)

    assert read_json(destination) == payload
    assert not destination.with_suffix(".json.tmp").exists()
