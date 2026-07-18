"""Tests for all API routes with fake JobService and full HTTP checks."""
from __future__ import annotations
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
import pytest
import sys
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

class TestJobSerialization:
    def test_list_response_no_asset_file(self, tmp_path):
        app, service = _mock_app(tmp_path)
        job = dict(_SAMPLE_JOB)
        service.list_jobs.return_value = [job]
        resp = app.test_client().get('/api/jobs')
        data = resp.get_json()
        assert 'asset_file' not in data['jobs'][0]
        assert 'asset_url' in data['jobs'][0]
    def test_report_downloads_urls(self, tmp_path):
        app, service = _mock_app(tmp_path)
        report = dict(_SAMPLE_REPORT, downloads={'csv': 'detections.csv', 'zip': 'audit_package.zip'})
        service.get_report.return_value = report
        resp = app.test_client().get('/api/jobs/20260718_101530_a1b2c3d4/report')
        dl = resp.get_json()['report']['downloads']
        assert dl['csv'].endswith('/artifacts/detections.csv')
        assert dl['zip'].endswith('/artifacts/audit_package.zip')
    def test_original_report_untouched(self, tmp_path):
        app, service = _mock_app(tmp_path)
        original = dict(_SAMPLE_REPORT, downloads={'csv': 'detections.csv'})
        service.get_report.return_value = original
        app.test_client().get('/api/jobs/20260718_101530_a1b2c3d4/report')
        assert original['downloads']['csv'] == 'detections.csv'
class TestUploadBoundaries:
    def test_dual_asset_rejected(self, tmp_path):
        app, service = _mock_app(tmp_path)
        png = _png_bytes()
        data = {'project_name': 'test', 'asset': [(BytesIO(png), 'a.png'), (BytesIO(png), 'b.png')]}
        resp = app.test_client().post('/api/jobs', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400
        service.create_job.assert_not_called()
    def test_reviewer_empty_rejected(self, tmp_path):
        app, _ = _mock_app(tmp_path)
        resp = app.test_client().patch('/api/jobs/20260718_101530_a1b2c3d4/review', json={'decision': 'pass', 'reviewer': ''})
        assert resp.status_code == 400
    def test_reviewer_40_accepted(self, tmp_path):
        app, service = _mock_app(tmp_path)
        service.review_job.return_value = dict(_SAMPLE_REPORT, final_decision='pass', reviewer='a'*40)
        resp = app.test_client().patch('/api/jobs/20260718_101530_a1b2c3d4/review', json={'decision': 'pass', 'reviewer': 'a'*40})
        assert resp.status_code == 200
    def test_reviewer_41_rejected(self, tmp_path):
        app, _ = _mock_app(tmp_path)
        resp = app.test_client().patch('/api/jobs/20260718_101530_a1b2c3d4/review', json={'decision': 'pass', 'reviewer': 'a'*41})
        assert resp.status_code == 400
    def test_unknown_exception_returns_500(self, tmp_path):
        app, service = _mock_app(tmp_path)
        service.get_job.side_effect = RuntimeError(
            "secret /" "Users/example/.ssh/key.pem"
        )
        resp = app.test_client().get('/api/jobs/20260718_101530_a1b2c3d4')
        assert resp.status_code == 500
        payload = resp.get_json()
        assert 'secret' not in str(payload) and 'Users' not in str(payload)
class TestRealService:
    @pytest.mark.skipif(sys.platform == "win32", reason="storage.py fsync PermissionError on Windows")
    def test_create_and_retrieve_png(self, tmp_path):
        from aegis_review.storage import JobStorage
        from aegis_review.service import JobService, UnavailableAnalyzer
        storage = JobStorage(tmp_path / 'outputs', 200 * 1024 * 1024)
        service = JobService(storage, UnavailableAnalyzer())
        config = AppConfig(project_root=tmp_path, testing=True)
        app = _create_app(config, job_service=service)
        png = _png_bytes()
        data = {'project_name': 'test', 'asset': (BytesIO(png), 'test.png')}
        resp = app.test_client().post('/api/jobs', data=data, content_type='multipart/form-data')
        assert resp.status_code == 201
        job_id = resp.get_json()['job']['job_id']
        assert (tmp_path / 'outputs' / job_id / 'job.json').is_file()
        assert (tmp_path / 'outputs' / job_id / 'input' / 'original.png').is_file()
        service.shutdown(wait=True)
    def test_not_found_404_with_real_service(self, tmp_path):
        app = _real_app(tmp_path)
        resp = app.test_client().get('/api/jobs/20260718_101530_deadbeef')
        assert resp.status_code == 404
class TestArtifactDisposition:
    def test_png_inline(self, tmp_path):
        app, service = _mock_app(tmp_path)
        p = tmp_path / 'test.png'
        p.write_bytes(_png_bytes())
        service.resolve_artifact.return_value = p
        resp = app.test_client().get('/api/jobs/id/artifacts/test.png')
        assert resp.headers.get('Content-Disposition', '').startswith('inline')
    def test_json_attachment(self, tmp_path):
        app, service = _mock_app(tmp_path)
        p = tmp_path / 'test.json'
        p.write_text('{}')
        service.resolve_artifact.return_value = p
        resp = app.test_client().get('/api/jobs/id/artifacts/test.json')
        cd = resp.headers.get('Content-Disposition', '')
        assert 'attachment' in cd

class TestHttpException:
    def test_bad_request_returns_400_json(self, tmp_path: Path) -> None:
        from werkzeug.exceptions import BadRequest
        app, service = _mock_app(tmp_path)
        service.get_job.side_effect = BadRequest(
            "secret /" "Users/example/"
        )
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4")
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["ok"] is False
        assert "secret" not in str(payload)

    def test_entity_too_large_returns_413_json(self, tmp_path: Path) -> None:
        from werkzeug.exceptions import RequestEntityTooLarge
        app, service = _mock_app(tmp_path)
        service.get_job.side_effect = RequestEntityTooLarge()
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4")
        assert resp.status_code == 413
        assert resp.get_json()["ok"] is False

    def test_runtime_error_returns_500_json(self, tmp_path: Path) -> None:
        app, service = _mock_app(tmp_path)
        service.get_job.side_effect = RuntimeError("internal secret")
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4")
        assert resp.status_code == 500
        payload = resp.get_json()
        assert "secret" not in str(payload)

    def test_wrong_method_returns_json(self, tmp_path: Path) -> None:
        app = _real_app(tmp_path)
        resp = app.test_client().post("/api/health")
        assert resp.status_code == 405
        assert resp.is_json
        payload = resp.get_json()
        assert payload["ok"] is False
        assert payload["error"]["code"] == "invalid_request"
    def test_method_not_allowed_returns_405(self, tmp_path: Path) -> None:
        from werkzeug.exceptions import MethodNotAllowed
        app, service = _mock_app(tmp_path)
        service.get_job.side_effect = MethodNotAllowed(
            "secret /" "Users/example/private"
        )
        resp = app.test_client().get("/api/jobs/20260718_101530_a1b2c3d4")
        assert resp.status_code == 405
        assert resp.is_json
        payload = resp.get_json()
        assert payload["ok"] is False
        assert payload["error"]["code"] == "invalid_request"
        assert "secret" not in str(payload)
        assert "Users" not in str(payload)
        assert "private" not in str(payload)
