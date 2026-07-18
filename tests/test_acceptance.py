"""Normal-path acceptance matrix (N1-N8) backed by the integrated public API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.support import (
    FIXTURE_MEDIA,
    PROJECT_ROOT,
    flow_image_complete,
    make_app,
    managed_app,
    poll,
    real_model_analyzer,
    static_analyzer,
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


def _require_model() -> None:
    assert _model_path() is not None, "required model aegis_game_best.pt is missing"


def _enemy(confidence: float) -> list[dict[str, Any]]:
    return [
        {
            "class_id": 0,
            "class_name": "enemy",
            "confidence": confidence,
            "bbox_xyxy": [1.0, 1.0, 20.0, 20.0],
        }
    ]


# ---------------------------------------------------------------------------
# N1  图片全流程: 创建 → 分析 → 完成 → 报告
# ---------------------------------------------------------------------------
def test_n1_image_upload_analyze_complete_report(tmp_path: Path) -> None:
    """N1: upload a clean image, analyse, wait for completed, fetch report."""
    assert CLEAN.is_file()
    _require_model()

    with managed_app(
        {"project_root": tmp_path},
        analyzer=real_model_analyzer(),
    ) as app:
        with app.test_client() as client:
            job_id, report = flow_image_complete(client, CLEAN)
            assert report.get("job_id") == job_id
            validate_report_payload(report)
            assert report.get("auto_decision") in ("pass", "review", "reject")


# ---------------------------------------------------------------------------
# N2a/N2b/N2c  三档审核结论
# ---------------------------------------------------------------------------
def test_n2a_pass_decision(tmp_path: Path) -> None:
    """N2a: no risk detection yields pass through the public API."""
    with managed_app(
        {"project_root": tmp_path},
        analyzer=static_analyzer([]),
    ) as app:
        with app.test_client() as client:
            _, report = flow_image_complete(client, CLEAN)
    assert report.get("auto_decision") == "pass", f"got {report.get('auto_decision')}"


def test_n2b_review_decision(tmp_path: Path) -> None:
    """N2b: a 0.42 enemy detection yields review."""
    with managed_app(
        {"project_root": tmp_path},
        analyzer=static_analyzer(_enemy(0.42)),
    ) as app:
        with app.test_client() as client:
            _, report = flow_image_complete(client, RISK)
    assert report.get("auto_decision") == "review"


def test_n2c_reject_decision(tmp_path: Path) -> None:
    """N2c: a 0.82 enemy detection yields reject."""
    with managed_app(
        {"project_root": tmp_path},
        analyzer=static_analyzer(_enemy(0.82)),
    ) as app:
        with app.test_client() as client:
            _, report = flow_image_complete(client, REJECT)
    assert report.get("auto_decision") == "reject"


# ---------------------------------------------------------------------------
# N3  视频异步处理与证据帧
# ---------------------------------------------------------------------------
def test_n3_video_async_status_progress_and_evidence_frames(tmp_path: Path) -> None:
    """N3: HTTP 202 video analysis completes with real-model evidence."""
    assert VIDEO.is_file()
    _require_model()
    with managed_app(
        {"project_root": tmp_path},
        analyzer=real_model_analyzer(),
    ) as app:
        with app.test_client() as client:
            resp = upload(client, VIDEO, "QA验收视频")
            assert resp.status_code == 201
            job_id = resp.get_json()["job"]["job_id"]

            resp = client.post(f"/api/jobs/{job_id}/analyze")
            assert resp.status_code == 202
            completed = poll(client, job_id, "completed", timeout=60)
            final_job = completed["job"]
            assert final_job["started_at"]
            assert final_job["completed_at"]

            job_dir = tmp_path / "outputs" / job_id
            evidence = job_dir / "evidence"
            frames = sorted(evidence.glob("frame_*.jpg"))
            assert frames

            resp = client.get(f"/api/jobs/{job_id}/report")
            assert resp.status_code == 200
            report = resp.get_json()["report"]
            assert report.get("evidence_frames")
            validate_artifact_dir(job_dir)


# ---------------------------------------------------------------------------
# N4  人工改判
# ---------------------------------------------------------------------------
def test_n4_manual_review_update_preserves_auto_decision(tmp_path: Path) -> None:
    """N4: PATCH completed job with reviewer/decision/note; auto_decision unchanged."""
    with managed_app(
        {"project_root": tmp_path},
        analyzer=static_analyzer([]),
    ) as app:
        with app.test_client() as client:
            job_id, original = flow_image_complete(client, CLEAN)
            auto = original.get("auto_decision")

            resp = client.patch(
                f"/api/jobs/{job_id}/review",
                json={
                    "decision": "review",
                    "reviewer": "李佳铭",
                    "note": "组长最终人工改判验收测试",
                },
            )
            assert resp.status_code == 200, resp.get_json()

            updated = resp.get_json().get("report", {})
            assert updated.get("final_decision") == "review"
            assert updated.get("auto_decision") == auto
            assert updated.get("reviewer") == "李佳铭"
            assert "组长最终人工改判验收测试" in updated.get("note", "")


# ---------------------------------------------------------------------------
# N5  历史任务重开
# ---------------------------------------------------------------------------
def test_n5_history_reopen_after_refresh(tmp_path: Path) -> None:
    """N5: create job → list API returns it; restart app, list still returns it."""
    with managed_app({"project_root": tmp_path}) as app:
        with app.test_client() as client:
            resp = upload(client, CLEAN, "QA历史重开")
            assert resp.status_code == 201
            job_id = resp.get_json()["job"]["job_id"]

            resp = client.get("/api/jobs")
            assert resp.status_code == 200
            ids = [j["job_id"] for j in resp.get_json().get("jobs", [])]
            assert job_id in ids

    with managed_app({"project_root": tmp_path}) as app2:
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
    with managed_app(
        {"project_root": tmp_path},
        analyzer=static_analyzer([]),
    ) as app:
        with app.test_client() as client:
            job_id, _report = flow_image_complete(client, CLEAN)

            resp = client.get(f"/api/jobs/{job_id}/artifacts/analysis_report.json")
            assert resp.status_code == 200
            validate_json(resp.data, f"report JSON for {job_id}")

            resp = client.get(f"/api/jobs/{job_id}/artifacts/detections.csv")
            assert resp.status_code == 200
            validate_csv(resp.data, min_rows=0, label=f"detections CSV for {job_id}")

            resp = client.get(f"/api/jobs/{job_id}/artifacts/audit_package.zip")
            assert resp.status_code == 200
            names = validate_zip(resp.data, f"audit_package for {job_id}")
            assert len(names) >= 2, f"ZIP too sparse: {names}"


# ---------------------------------------------------------------------------
# N7  删除已完成任务
# ---------------------------------------------------------------------------
def test_n7_delete_completed_job(tmp_path: Path) -> None:
    """N7: DELETE a completed job; job disappears from list and disk."""
    with managed_app(
        {"project_root": tmp_path},
        analyzer=static_analyzer([]),
    ) as app:
        with app.test_client() as client:
            job_id, _report = flow_image_complete(client, CLEAN)

            resp = client.delete(f"/api/jobs/{job_id}")
            assert resp.status_code == 200
            assert resp.get_json().get("deleted_job_id") == job_id

            resp = client.get("/api/jobs")
            ids = [j["job_id"] for j in resp.get_json().get("jobs", [])]
            assert job_id not in ids

            job_dir = tmp_path / "outputs" / job_id
            assert not job_dir.exists()


# ---------------------------------------------------------------------------
# N8  统计接口
# ---------------------------------------------------------------------------
def test_n8_statistics_reflect_final_decisions(tmp_path: Path) -> None:
    """N8: stats endpoint counts jobs by final decision (or auto when not reviewed)."""
    with managed_app(
        {"project_root": tmp_path},
        analyzer=static_analyzer([]),
    ) as app:
        with app.test_client() as client:
            j1, _r1 = flow_image_complete(client, CLEAN, "QA统计1")
            flow_image_complete(client, CLEAN, "QA统计2")

            resp = client.get("/api/stats")
            assert resp.status_code == 200
            stats = resp.get_json().get("stats", {})
            assert stats.get("total", 0) >= 2

            client.patch(
                f"/api/jobs/{j1}/review",
                json={
                    "decision": "review",
                    "reviewer": "李佳铭",
                    "note": "改判为复核",
                },
            )

            resp = client.get("/api/stats")
            stats = resp.get_json().get("stats", {})
            assert stats.get("review", 0) >= 1


# ---------------------------------------------------------------------------
#  Health endpoint (always runnable)
# ---------------------------------------------------------------------------
def test_health_readiness_fields_are_live_not_hardcoded(tmp_path: Path) -> None:
    """Health endpoint: model_ready reflects disk truth."""
    with managed_app({"project_root": tmp_path}) as app:
        with app.test_client() as client:
            resp = client.get("/api/health")
            assert resp.status_code == 200
            payload = resp.get_json()
            assert payload["ok"] is True
            assert payload["status"] == "ok"
            assert payload["model_ready"] is False
            assert isinstance(payload["ffmpeg_ready"], bool)
            assert payload["storage_ready"] is True


def test_qa_make_app_ignores_runtime_model_env_for_isolated_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA temp projects must not inherit Docker's production model path."""
    from tests.fixtures import support

    monkeypatch.setenv(
        "AEGIS_MODEL_PATH",
        str(PROJECT_ROOT / "models" / "aegis_game_best.pt"),
    )
    app = support.make_app({"project_root": tmp_path})
    service = app.extensions["aegis_job_service"]
    try:
        with app.test_client() as client:
            payload = client.get("/api/health").get_json()
        assert payload["model_ready"] is False
    finally:
        service.shutdown(wait=True)


def test_poll_fails_fast_when_analysis_enters_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed analysis is terminal and must not be reported as a timeout."""
    from tests.fixtures import support

    monkeypatch.delenv("AEGIS_MODEL_PATH", raising=False)
    app = support.make_app({"project_root": tmp_path})
    service = app.extensions["aegis_job_service"]
    try:
        with app.test_client() as client:
            response = upload(client, CLEAN, "QA失败快速返回")
            job_id = response.get_json()["job"]["job_id"]
            assert client.post(f"/api/jobs/{job_id}/analyze").status_code == 202
            service.shutdown(wait=True)
            with pytest.raises(AssertionError, match="CV 分析组件尚未就绪"):
                support.poll(
                    client,
                    job_id,
                    "completed",
                    timeout=0.05,
                    interval=0.01,
                )
    finally:
        if not getattr(service._executor, "_shutdown", False):
            service.shutdown(wait=True)


@pytest.mark.parametrize(
    ("detections", "expected"),
    [
        ([], "pass"),
        (
            [
                {
                    "class_id": 0,
                    "class_name": "enemy",
                    "confidence": 0.42,
                    "bbox_xyxy": [1.0, 1.0, 20.0, 20.0],
                }
            ],
            "review",
        ),
        (
            [
                {
                    "class_id": 0,
                    "class_name": "enemy",
                    "confidence": 0.82,
                    "bbox_xyxy": [1.0, 1.0, 20.0, 20.0],
                }
            ],
            "reject",
        ),
    ],
)
def test_static_analyzer_drives_public_api_decisions(
    tmp_path: Path,
    detections: list[dict[str, Any]],
    expected: str,
) -> None:
    """The deterministic seam must still exercise the real CV artifact pipeline."""
    from tests.fixtures import support

    factory = getattr(support, "static_analyzer", None)
    managed = getattr(support, "managed_app", None)
    assert callable(factory), "static_analyzer QA seam is missing"
    assert callable(managed), "managed_app QA lifecycle helper is missing"

    with managed(
        {"project_root": tmp_path},
        analyzer=factory(detections),
    ) as app:
        with app.test_client() as client:
            job_id, report = flow_image_complete(client, CLEAN)

    assert report["job_id"] == job_id
    assert report["auto_decision"] == expected
    validate_artifact_dir(tmp_path / "outputs" / job_id)
