"""Normal-path acceptance matrix (N1‑N8) backed by the public API.

Every test guards on backend/CV/model availability; when a dependency
has not been merged this suite skips with a descriptive reason rather
than fabricating a pass.  Health‑check and domain‑rule tests execute
immediately and provide real evidence.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.support import (
    FIXTURE_MEDIA,
    PROJECT_ROOT,
    SKIP_NO_BACKEND,
    SKIP_NO_CV,
    SKIP_NO_DETECTOR_SEAM,
    SKIP_NO_MODEL,
    error_matches,
    flow_image_complete,
    has_analyze_route,
    has_artifacts_route,
    has_delete_route,
    has_job_routes,
    has_report_route,
    has_review_route,
    has_statistics_route,
    make_app,
    poll,
    skip_if,
    upload,
    validate_artifact_dir,
    validate_csv,
    validate_json,
    validate_report_payload,
    validate_zip,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
CLEAN = FIXTURE_MEDIA / "clean_scene.jpg"
RISK = FIXTURE_MEDIA / "risk_scene.jpg"
REJECT = FIXTURE_MEDIA / "reject_scene.jpg"
VIDEO = FIXTURE_MEDIA / "sample_5s.mp4"


def _model_path() -> Path | None:
    env = Path("models/aegis_game_best.pt")
    if env.is_file():
        return env
    import os as _os

    cfg = _os.getenv("AEGIS_MODEL_PATH")
    if cfg:
        p = Path(cfg).expanduser().resolve()
        if p.is_file():
            return p
    return None


def _needs_model() -> None:
    skip_if(_model_path() is None, SKIP_NO_MODEL)


# ---------------------------------------------------------------------------
# N1  图片全流程: 创建 → 分析 → 完成 → 报告
# ---------------------------------------------------------------------------
def test_n1_image_upload_analyze_complete_report(tmp_path: Path) -> None:
    """N1: upload a clean image, analyse, wait for completed, fetch report."""
    skip_if(not CLEAN.is_file(), "clean_scene.jpg fixture missing — run make_fixtures")
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_analyze_route(app), SKIP_NO_BACKEND)
    skip_if(not has_report_route(app), SKIP_NO_BACKEND)
    _needs_model()

    with app.test_client() as client:
        job_id, report = flow_image_complete(client, CLEAN)
        assert report.get("job_id") == job_id
        validate_report_payload(report)
        assert report.get("auto_decision") in ("pass", "review", "reject")


# ---------------------------------------------------------------------------
# N2a/N2b/N2c  三档审核结论
# ---------------------------------------------------------------------------
def test_n2a_pass_decision(tmp_path: Path) -> None:
    """N2a: clean scene yields pass (no enemy detections above inference threshold)."""
    skip_if(not CLEAN.is_file(), "clean fixture missing")
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    _needs_model()

    with app.test_client() as client:
        _, report = flow_image_complete(client, CLEAN)
    assert report.get("auto_decision") == "pass", f"got {report.get('auto_decision')}"


def test_n2b_review_decision(tmp_path: Path) -> None:
    """N2b: risk scene should trigger review (moderate-confidence enemy)."""
    skip_if(not RISK.is_file(), "risk fixture missing")
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    _needs_model()
    skip_if(True, SKIP_NO_DETECTOR_SEAM)
    # ^ unskip after CV merge provides injectable Detector

    with app.test_client() as client:
        _, report = flow_image_complete(client, RISK)
    assert report.get("auto_decision") in ("review", "reject")


def test_n2c_reject_decision(tmp_path: Path) -> None:
    """N2c: high-risk scene should trigger reject (>0.60 confidence)."""
    skip_if(not REJECT.is_file(), "reject fixture missing")
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    _needs_model()
    skip_if(True, SKIP_NO_DETECTOR_SEAM)

    with app.test_client() as client:
        _, report = flow_image_complete(client, REJECT)
    assert report.get("auto_decision") == "reject"


# ---------------------------------------------------------------------------
# N3  视频异步处理与证据帧
# ---------------------------------------------------------------------------
def test_n3_video_async_status_progress_and_evidence_frames(tmp_path: Path) -> None:
    """N3: upload video → status changes created→queued→running→completed with evidence frames."""
    skip_if(not VIDEO.is_file(), "sample_5s.mp4 fixture missing")
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_analyze_route(app), SKIP_NO_BACKEND)
    _needs_model()

    with app.test_client() as client:
        resp = upload(client, VIDEO, "QA验收视频")
        assert resp.status_code == 201
        job_id = resp.get_json()["job"]["job_id"]

        resp = client.post(f"/api/jobs/{job_id}/analyze")
        assert resp.status_code == 202

        # Observe status transitions
        seen_statuses: list[str] = []
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            resp = client.get(f"/api/jobs/{job_id}")
            assert resp.status_code == 200
            st = resp.get_json().get("status")
            if st not in seen_statuses:
                seen_statuses.append(st)
            if st in ("completed", "failed"):
                break
            time.sleep(0.5)

        assert "completed" == resp.get_json().get("status"), (
            f"video job ended as {resp.get_json().get('status')}: {resp.get_json().get('error')}"
        )
        assert "queued" in seen_statuses or "running" in seen_statuses

        # Evidence frames must exist on disk
        job_dir = tmp_path / "outputs" / job_id
        evidence = job_dir / "evidence"
        assert evidence.is_dir(), f"no evidence dir in {job_dir}"
        frames = sorted(evidence.glob("frame_*.jpg"))
        assert len(frames) >= 1, f"expected >=1 evidence frame, got {len(frames)}"

        # Report contains evidence_frames list
        resp = client.get(f"/api/jobs/{job_id}/report")
        assert resp.status_code == 200
        report = resp.get_json()["report"]
        assert len(report.get("evidence_frames", [])) >= 1


# ---------------------------------------------------------------------------
# N4  人工改判
# ---------------------------------------------------------------------------
def test_n4_manual_review_update_preserves_auto_decision(tmp_path: Path) -> None:
    """N4: PATCH completed job with reviewer/decision/note; auto_decision unchanged."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_review_route(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")
    _needs_model()

    with app.test_client() as client:
        job_id, original = flow_image_complete(client, CLEAN)
        auto = original.get("auto_decision")

        resp = client.patch(
            f"/api/jobs/{job_id}/review",
            json={
                "decision": "review",
                "reviewer": "朱可心",
                "note": "QA 人工改判验收测试",
            },
        )
        assert resp.status_code == 200, resp.get_json()

        updated = resp.get_json().get("report", {})
        assert updated.get("final_decision") == "review"
        assert updated.get("auto_decision") == auto
        assert updated.get("reviewer") == "朱可心"
        assert "QA 人工改判验收测试" in updated.get("note", "")


# ---------------------------------------------------------------------------
# N5  历史任务重开
# ---------------------------------------------------------------------------
def test_n5_history_reopen_after_refresh(tmp_path: Path) -> None:
    """N5: create job → list API returns it; restart app, list still returns it."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")
    _needs_model()

    with app.test_client() as client:
        resp = upload(client, CLEAN, "QA历史重开")
        assert resp.status_code == 201
        job_id = resp.get_json()["job"]["job_id"]

        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        ids = [j["job_id"] for j in resp.get_json().get("jobs", [])]
        assert job_id in ids

    # New app instance  –  disk persistence
    app2 = make_app({"project_root": tmp_path})
    with app2.test_client() as client2:
        resp = client2.get("/api/jobs")
        assert resp.status_code == 200
        ids = [j["job_id"] for j in resp.get_json().get("jobs", [])]
        assert job_id in ids


# ---------------------------------------------------------------------------
# N6  JSON / CSV / ZIP 下载
# ---------------------------------------------------------------------------
def test_n6_artifact_download_json_csv_zip(tmp_path: Path) -> None:
    """N6: completed job exposes downloadable JSON report, CSV, ZIP."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_artifacts_route(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")
    _needs_model()

    with app.test_client() as client:
        job_id, _report = flow_image_complete(client, CLEAN)

        # JSON report file
        resp = client.get(f"/api/jobs/{job_id}/artifacts/analysis_report.json")
        assert resp.status_code == 200
        validate_json(resp.data, f"report JSON for {job_id}")

        # CSV
        resp = client.get(f"/api/jobs/{job_id}/artifacts/detections.csv")
        assert resp.status_code == 200
        _cols, rows = validate_csv(resp.data, min_rows=0, label=f"detections CSV for {job_id}")

        # ZIP
        resp = client.get(f"/api/jobs/{job_id}/artifacts/audit_package.zip")
        assert resp.status_code == 200
        names = validate_zip(resp.data, f"audit_package for {job_id}")
        assert len(names) >= 2, f"ZIP too sparse: {names}"


# ---------------------------------------------------------------------------
# N7  删除已完成任务
# ---------------------------------------------------------------------------
def test_n7_delete_completed_job(tmp_path: Path) -> None:
    """N7: DELETE a completed job; job disappears from list and disk."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_delete_route(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")
    _needs_model()

    with app.test_client() as client:
        job_id, _report = flow_image_complete(client, CLEAN)

        resp = client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.get_json().get("deleted_job_id") == job_id

        # Gone from list
        resp = client.get("/api/jobs")
        ids = [j["job_id"] for j in resp.get_json().get("jobs", [])]
        assert job_id not in ids

        # Gone from disk
        job_dir = tmp_path / "outputs" / job_id
        assert not job_dir.exists()


# ---------------------------------------------------------------------------
# N8  统计接口
# ---------------------------------------------------------------------------
def test_n8_statistics_reflect_final_decisions(tmp_path: Path) -> None:
    """N8: stats endpoint counts jobs by final decision (or auto when not reviewed)."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_statistics_route(app), SKIP_NO_BACKEND)
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")
    _needs_model()

    with app.test_client() as client:
        # Create & complete two image jobs
        j1, r1 = flow_image_complete(client, CLEAN, "QA统计1")
        j2, r2 = flow_image_complete(client, CLEAN, "QA统计2")

        resp = client.get("/api/stats")
        assert resp.status_code == 200
        stats = resp.get_json().get("stats", {})
        assert stats.get("total", 0) >= 2

        # Change one to review
        client.patch(
            f"/api/jobs/{j1}/review",
            json={"decision": "review", "reviewer": "朱可心", "note": "改判为复核"},
        )

        resp = client.get("/api/stats")
        stats = resp.get_json().get("stats", {})
        assert stats.get("review", 0) >= 1


# ---------------------------------------------------------------------------
#  Health endpoint (always runnable)
# ---------------------------------------------------------------------------
def test_health_readiness_fields_are_live_not_hardcoded(tmp_path: Path) -> None:
    """Health endpoint: model_ready reflects disk truth."""
    app = make_app({"project_root": tmp_path})
    with app.test_client() as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["status"] == "ok"
        # tmp_path has no model → model_ready MUST be false
        assert payload["model_ready"] is False, "model_ready should be false when model is absent"
        assert isinstance(payload["ffmpeg_ready"], bool)
        assert payload["storage_ready"] is True
