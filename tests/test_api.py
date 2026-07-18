"""Tests for all API routes with fake JobService and full HTTP checks."""
from __future__ import annotations
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from PIL import Image
from aegis_review import create_app as _create_app
from aegis_review.config import AppConfig
from aegis_review.domain import AuditSettings
from aegis_review.storage import JobNotFoundError
from aegis_review.service import (
    ArtifactNotFoundError, InvalidStatusTransition,
    JobBusyError, JobService, JobServiceError,
)
def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1)).save(buf, format="PNG")
    return buf.getvalue()
def _mock_app(tmp_path: Path):
    config = AppConfig(project_root=tmp_path, testing=True)
    service = MagicMock(spec=JobService)
    app = _create_app(config, job_service=service)
    return app, service
def _real_app(tmp_path: Path):
    config = AppConfig(project_root=tmp_path, testing=True)
    app = _create_app(config)
    return app
_SAMPLE_JOB = {
    "job_id": "20260718_101530_a1b2c3d4",
    "project_name": "\u6d4b\u8bd5\u9879\u76ee",
    "asset_name": "test.png", "asset_type": "image",
    "asset_file": "original.png", "status": "created",
    "created_at": "2026-07-18T10:15:30+08:00",
    "started_at": None, "completed_at": None,
    "settings": AuditSettings().to_dict(),
    "result_file": None, "error": None,
}
_SAMPLE_REPORT = {
    "job_id": "20260718_101530_a1b2c3d4",
    "detections": [],
    "evidence_frames": ["frame_000001.jpg"],
    "rules": AuditSettings().to_dict(),
    "auto_decision": "pass", "final_decision": None,
    "reviewer": None, "note": None,
    "downloads": {},
}
_SAMPLE_STATS = {"total": 3, "pass": 2, "review": 0, "reject": 1, "failed": 0}
class TestCreateJob:
    def test_valid_media_returns_201(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.create_job.return_value = dict(_SAMPLE_JOB, status="created")
        data = {"project_name": "\u6d4b\u8bd5\u9879\u76ee"}
        data["asset"] = (BytesIO(_png_bytes()), "test.png")
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 201
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["job"]["status"] == "created"
    def test_missing_asset_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        data = {"project_name": "test"}
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
    def test_missing_project_name_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        data = {"asset": (BytesIO(_png_bytes()), "test.png")}
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
    def test_unsupported_extension_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        data = {"project_name": "test", "asset": (BytesIO(b"data"), "test.exe")}
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
    def test_corrupted_image_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        data = {"project_name": "test", "asset": (BytesIO(b"not-an-image"), "bad.png")}
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
    def test_invalid_settings_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        data = {"project_name": "test", "settings": '{"bad_field": 1}', "asset": (BytesIO(_png_bytes()), "test.png")}
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
    def test_empty_file_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        data = {"project_name": "test", "asset": (BytesIO(b""), "empty.png")}
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
    def test_no_task_dir_left_after_failure(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        data = {"project_name": "test", "asset": (BytesIO(b"garbage"), "bad.png")}
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        outputs = tmp_path / "outputs"
        if outputs.exists():
            assert not list(outputs.iterdir())
class TestAnalyzeJob:
    def test_created_job_returns_202(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.enqueue_analysis.return_value = {"job_id": "20260718_101530_a1b2c3d4", "status": "queued"}
        resp = app.test_client().post("/api/jobs/20260718_101530_a1b2c3d4/analyze")
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["ok"] is True
        assert data["status"] == "queued"
    def test_invalid_status_returns_409(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.enqueue_analysis.side_effect = InvalidStatusTransition("bad transition")
        resp = app.test_client().post("/api/jobs/20260718_101530_a1b2c3d4/analyze")
        assert resp.status_code == 409
        assert resp.get_json()["ok"] is False
    def test_running_job_returns_409(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.enqueue_analysis.side_effect = JobBusyError("job is running")
        resp = app.test_client().post("/api/jobs/20260718_101530_a1b2c3d4/analyze")
        assert resp.status_code == 409
        assert resp.get_json()["ok"] is False
class TestListJobs:
    def test_returns_jobs_list(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.list_jobs.return_value = [_SAMPLE_JOB]
        resp = app.test_client().get("/api/jobs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert len(data["jobs"]) == 1
        assert data["total"] == 1
    def test_empty_list(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.list_jobs.return_value = []
        resp = app.test_client().get("/api/jobs")
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 0
    def test_filters_by_status(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.list_jobs.return_value = []
        resp = app.test_client().get("/api/jobs?status=completed")
        assert resp.status_code == 200
        service.list_jobs.assert_called_once_with(status="completed")
    def test_invalid_status_param_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        resp = app.test_client().get("/api/jobs?status=invalid_status")
        assert resp.status_code == 400
class TestGetJob:
    def test_returns_job(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.get_job.return_value = _SAMPLE_JOB
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
    def test_not_found_returns_404(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        e = JobNotFoundError("\u4efb\u52a1\u4e0d\u5b58\u5728\u3002")
        service.get_job.side_effect = e
        resp = app.test_client().get("/api/jobs/notexist")
        assert resp.status_code == 404
        assert resp.get_json()["ok"] is False
class TestDeleteJob:
    def test_delete_created_job_returns_200(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.delete_job.return_value = None
        resp = app.test_client().delete("/api/jobs/20260718_101530_a1b2c3d4")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["deleted_job_id"] == "20260718_101530_a1b2c3d4"
    def test_busy_job_returns_409(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.delete_job.side_effect = JobBusyError("job busy")
        resp = app.test_client().delete("/api/jobs/20260718_101530_a1b2c3d4")
        assert resp.status_code == 409
    def test_not_found_returns_404(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.delete_job.side_effect = JobNotFoundError("\u4efb\u52a1\u4e0d\u5b58\u5728\u3002")
        resp = app.test_client().delete("/api/jobs/notexist")
        assert resp.status_code == 404
class TestReviewJob:
    def test_valid_review_returns_200(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        report = dict(_SAMPLE_REPORT, final_decision="review", reviewer="\u5f20\u4e09")
        service.review_job.return_value = report
        resp = app.test_client().patch(
            "/api/jobs/20260718_101530_a1b2c3d4/review",
            json={"decision": "review", "reviewer": "\u5f20\u4e09", "note": "\u786e\u8ba4"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
    def test_invalid_decision_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        resp = app.test_client().patch(
            "/api/jobs/20260718_101530_a1b2c3d4/review",
            json={"decision": "invalid", "reviewer": "\u5f20\u4e09"},
        )
        assert resp.status_code == 400
    def test_missing_reviewer_returns_400(self, tmp_path: Path) -> None:
        app, _ = _mock_app(tmp_path)
        resp = app.test_client().patch(
            "/api/jobs/20260718_101530_a1b2c3d4/review",
            json={"decision": "pass", "reviewer": ""},
        )
        assert resp.status_code == 400
    def test_non_completed_returns_409(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.review_job.side_effect = InvalidStatusTransition("not completed")
        resp = app.test_client().patch(
            "/api/jobs/20260718_101530_a1b2c3d4/review",
            json={"decision": "review", "reviewer": "\u5f20\u4e09"},
        )
        assert resp.status_code == 409
class TestGetReport:
    def test_returns_report(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.get_report.return_value = _SAMPLE_REPORT
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4/report")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
    def test_not_completed_returns_409(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.get_report.side_effect = InvalidStatusTransition("not completed")
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4/report")
        assert resp.status_code == 409
class TestGetArtifact:
    def test_existing_artifact_returns_file(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        artifact_path = tmp_path / "test_artifact.txt"
        artifact_path.write_text("hello")
        service.resolve_artifact.return_value = artifact_path
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4/artifacts/report.json")
        assert resp.status_code == 200
        assert resp.data == b"hello"
    def test_nonexistent_artifact_returns_404(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.resolve_artifact.side_effect = ArtifactNotFoundError("not found")
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4/artifacts/missing.txt")
        assert resp.status_code == 404
    def test_path_traversal_returns_404(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.resolve_artifact.side_effect = ArtifactNotFoundError("not found")
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4/artifacts/../../../etc/passwd")
        assert resp.status_code == 404
class TestStats:
    def test_returns_stats(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.stats.return_value = _SAMPLE_STATS
        resp = app.test_client().get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["stats"]["total"] == 3
class TestUnknownRoute:
    def test_unknown_api_route_returns_404(self, tmp_path: Path) -> None:
        app = _real_app(tmp_path)
        resp = app.test_client().get("/api/unknown-route")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_found"
class TestFullHttpContract:
    def test_health_full_response_structure(self, tmp_path: Path) -> None:
        app = _real_app(tmp_path)
        resp = app.test_client().get("/api/health")
        payload = resp.get_json()
        assert resp.status_code == 200
        assert payload["ok"] is True
        assert payload["status"] == "ok"
        assert isinstance(payload.get("model_ready"), bool)
        assert "ffmpeg_ready" in payload
        assert "storage_ready" in payload
    def test_invalid_file_rejects_without_leaving_dirs(self, tmp_path: Path) -> None:
        app = _real_app(tmp_path)
        data = {"project_name": "\u5168\u91cf\u6d4b\u8bd5", "asset": (BytesIO(b"bad-data"), "test.png")}
        resp = app.test_client().post("/api/jobs", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["ok"] is False
        assert "error" in payload
        outputs = tmp_path / "outputs"
        if outputs.exists():
            children = list(outputs.iterdir())
            assert not children
