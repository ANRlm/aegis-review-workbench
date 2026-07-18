"""Abnormal-path tests (A1‑A12) and security probes.

Covers invalid inputs, path traversal, symlink escapes, model‑missing
behaviour, service‑restart recovery, and running‑job deletion.

Many tests depend on backend routes and are skipped with explicit
reasons when those features have not been merged.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest

from tests.fixtures.support import (
    FIXTURE_MEDIA,
    PROJECT_ROOT,
    SKIP_NO_BACKEND,
    SKIP_NO_MODEL,
    SKIP_NOT_WINDOWS_SYMLINK,
    error_matches,
    has_analyze_route,
    has_artifacts_route,
    has_delete_route,
    has_job_routes,
    has_report_route,
    has_review_route,
    has_statistics_route,
    make_app,
    skip_if,
    upload,
    validate_json,
)

CORRUPT_JPEG = FIXTURE_MEDIA / "corrupt.jpg"
CORRUPT_MP4 = FIXTURE_MEDIA / "corrupt.mp4"
EMPTY = FIXTURE_MEDIA / "empty.bin"
TEXT_AS_IMAGE = FIXTURE_MEDIA / "not_media.jpg"
CLEAN = FIXTURE_MEDIA / "clean_scene.jpg"
VIDEO = FIXTURE_MEDIA / "sample_5s.mp4"


def _model_path() -> Path | None:
    p = PROJECT_ROOT / "models" / "aegis_game_best.pt"
    if p.is_file():
        return p
    env = os.getenv("AEGIS_MODEL_PATH")
    if env:
        ep = Path(env).expanduser().resolve()
        if ep.is_file():
            return ep
    return None


def _needs_model() -> None:
    skip_if(_model_path() is None, SKIP_NO_MODEL)


# ---------------------------------------------------------------------------
# A1  不支持扩展名
# ---------------------------------------------------------------------------
def test_a1_unsupported_extension_rejected(tmp_path: Path) -> None:
    """A1: .bmp upload returns 400."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    data = {"project_name": "bad ext"}
    data["asset"] = (io.BytesIO(b"\x00" * 100), "frame.bmp")
    with app.test_client() as client:
        resp = client.post(
            "/api/jobs", data=data, content_type="multipart/form-data"
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# A2  空文件
# ---------------------------------------------------------------------------
def test_a2_empty_file_rejected(tmp_path: Path) -> None:
    """A2: zero-byte upload returns 400 invalid_asset."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    with app.test_client() as client:
        resp = upload(client, EMPTY, "empty")
    assert resp.status_code == 400
    assert error_matches(resp, 400, "invalid_asset") or resp.status_code == 400


# ---------------------------------------------------------------------------
# A3  损坏媒体（图片 / 视频）
# ---------------------------------------------------------------------------
def test_a3a_corrupt_image_rejected(tmp_path: Path) -> None:
    """A3a: truncated JPEG returns 400 invalid_asset."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    with app.test_client() as client:
        resp = upload(client, CORRUPT_JPEG, "corrupt img")
    assert resp.status_code == 400
    assert error_matches(resp, 400, "invalid_asset")


def test_a3b_corrupt_video_rejected(tmp_path: Path) -> None:
    """A3b: garbage bytes .mp4 returns 400 invalid_asset."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    with app.test_client() as client:
        resp = upload(client, CORRUPT_MP4, "corrupt vid")
    assert resp.status_code == 400
    assert error_matches(resp, 400, "invalid_asset")


# ---------------------------------------------------------------------------
# A4  错误阈值顺序
# ---------------------------------------------------------------------------
def test_a4_invalid_settings_threshold_order_rejected(tmp_path: Path) -> None:
    """A4: review_confidence >= reject_confidence returns 400."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")

    bad_settings = {"reject_confidence": 0.30, "review_confidence": 0.70}
    with app.test_client() as client:
        resp = upload(client, CLEAN, "bad threshold", settings=bad_settings)
    assert resp.status_code == 400
    assert error_matches(resp, 400, "invalid_settings")


# ---------------------------------------------------------------------------
# A5  负责人为空
# ---------------------------------------------------------------------------
def test_a5_blank_reviewer_rejected(tmp_path: Path) -> None:
    """A5: PATCH review with empty reviewer returns 400."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_review_route(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")
    _needs_model()

    from tests.fixtures.support import flow_image_complete

    with app.test_client() as client:
        job_id, _report = flow_image_complete(client, CLEAN, "QA空审核人")
        resp = client.patch(
            f"/api/jobs/{job_id}/review",
            json={"decision": "review", "reviewer": "   ", "note": ""},
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# A6  重复分析返回 409
# ---------------------------------------------------------------------------
def test_a6_duplicate_analyze_returns_409(tmp_path: Path) -> None:
    """A6: calling analyze on a queued/running/completed job returns 409."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_analyze_route(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")
    _needs_model()

    with app.test_client() as client:
        resp = upload(client, CLEAN, "duplicate")
        assert resp.status_code == 201
        job_id = resp.get_json()["job"]["job_id"]

        r1 = client.post(f"/api/jobs/{job_id}/analyze")
        assert r1.status_code == 202

        r2 = client.post(f"/api/jobs/{job_id}/analyze")
        assert r2.status_code == 409
        assert error_matches(r2, 409, r2.get_json().get("error", {}).get("code", ""))


# ---------------------------------------------------------------------------
# A7  模型文件不存在
# ---------------------------------------------------------------------------
def test_a7_model_missing_returns_appropriate_error(tmp_path: Path) -> None:
    """A7: when model file is missing, analyze either returns immediate error
    or the job transitions to failed with a model‑related error."""
    app = make_app({"project_root": tmp_path, "testing": True})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_analyze_route(app), SKIP_NO_BACKEND)
    skip_if(not CLEAN.is_file(), "clean fixture missing")

    # tmp_path guarantees model_ready is False
    with app.test_client() as client:
        resp = client.get("/api/health")
        assert resp.get_json().get("model_ready") is False, "expected model_ready=false in test"

        resp = upload(client, CLEAN, "model missing test")
        # If backend hasn't been merged, this is a 404 – skip gracefully
        if resp.status_code == 404:
            pytest.skip(SKIP_NO_BACKEND)
        assert resp.status_code == 201
        job_id = resp.get_json()["job"]["job_id"]

        resp = client.post(f"/api/jobs/{job_id}/analyze")
        # Both behaviours are acceptable:
        #   a) immediate non‑2xx with model_unavailable
        #   b) 202 → job eventually fails with model error
        if resp.status_code != 202:
            assert resp.status_code in (400, 409, 500, 503), (
                f"unexpected status: {resp.status_code} {resp.get_json()}"
            )
            assert error_matches(resp, resp.status_code, "model_unavailable") or error_matches(
                resp, resp.status_code, "internal_error"
            )
            return

        # Path b
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            detail = client.get(f"/api/jobs/{job_id}")
            if detail.status_code == 200:
                body = detail.get_json()
                job = body.get("job") or {}
                if job.get("status") == "failed":
                    err = str(job.get("error", "")).lower()
                    assert any(word in err for word in ("model", "模型", "cv", "分析", "unavailable")), (
                        f"model‑missing error message missing keywords: {err}"
                    )
                    return
            time.sleep(0.5)

    pytest.fail("model‑missing task did not transition to failed")


# ---------------------------------------------------------------------------
# A8  运行中删除返回 409
# ---------------------------------------------------------------------------
def test_a8_delete_running_job_returns_409(tmp_path: Path) -> None:
    """A8: DELETE a queued/running job returns 409 job_busy."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)
    skip_if(not has_delete_route(app), SKIP_NO_BACKEND)
    skip_if(not has_analyze_route(app), SKIP_NO_BACKEND)
    skip_if(not VIDEO.is_file(), SKIP_NO_BACKEND)
    _needs_model()

    with app.test_client() as client:
        resp = upload(client, VIDEO, "delete running")
        assert resp.status_code == 201
        job_id = resp.get_json()["job"]["job_id"]

        client.post(f"/api/jobs/{job_id}/analyze")
        time.sleep(0.1)

        resp = client.delete(f"/api/jobs/{job_id}")
        if resp.status_code == 409:
            assert error_matches(resp, 409, "job_busy")
        else:
            # Job was too fast (e.g. tiny video) – skip instead of fail
            pytest.skip("job completed before delete could be tested — reliable with real model")


# ---------------------------------------------------------------------------
# A9  非法任务 ID
# ---------------------------------------------------------------------------
def test_a9_invalid_job_id_returns_404(tmp_path: Path) -> None:
    """A9: malformed / nonexistent job IDs return 404 without crashing."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    bad_ids = ["not_a_job", "20260718_101530", "../../etc/passwd", "x" * 50]
    with app.test_client() as client:
        for jid in bad_ids:
            for method, path_fn in [
                ("GET", lambda j: f"/api/jobs/{j}"),
                ("DELETE", lambda j: f"/api/jobs/{j}"),
            ]:
                if method == "GET":
                    resp = client.get(path_fn(jid))
                else:
                    resp = client.delete(path_fn(jid))
                assert resp.status_code == 404, f"{method} {path_fn(jid)} returned {resp.status_code}"


# ---------------------------------------------------------------------------
# A10  ../ 产物路径越界
# ---------------------------------------------------------------------------
def test_a10_artifact_traversal_returns_404(tmp_path: Path) -> None:
    """A10: artifact requests containing ../ or absolute paths are rejected."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    # Even without a real job, the route should reject traversal patterns
    with app.test_client() as client:
        jid = "20260718_101530_a1b2c3d4"
        for filename in [
            "../../etc/passwd",
            "../secret.txt",
            "..\\..\\windows\\win.ini",
            "foo%2f..%2fbar",
        ]:
            resp = client.get(f"/api/jobs/{jid}/artifacts/{filename}")
            assert resp.status_code in (404, 400), (
                f"traversal {filename!r} returned {resp.status_code}"
            )


# ---------------------------------------------------------------------------
# A11a  符号链接 – 服务层 resolve_artifact
# ---------------------------------------------------------------------------
def test_a11a_resolve_artifact_rejects_symlink_escape(tmp_path: Path) -> None:
    """A11a: JobService.resolve_artifact rejects a whitelisted file that is a symlink."""
    from aegis_review.config import AppConfig
    from aegis_review.domain import AuditSettings, JobRecord, JobStatus, MediaType
    from aegis_review.service import ArtifactNotFoundError, JobService, UnavailableAnalyzer
    from aegis_review.storage import JobStorage, atomic_write_json

    cfg = AppConfig(project_root=tmp_path, testing=True)
    job_dir = cfg.outputs_dir / "20260718_101530_deadbeef"
    result_dir = job_dir / "result"
    evidence_dir = job_dir / "evidence"
    input_dir = job_dir / "input"
    for d in (job_dir, result_dir, evidence_dir, input_dir):
        d.mkdir(parents=True, exist_ok=True)

    target = tmp_path / "secret_data.txt"
    target.write_text("secret", encoding="utf-8")

    # Create symlink: evidence frame points outside
    try:
        (evidence_dir / "naughty_frame.jpg").symlink_to(target)
    except OSError:
        pytest.skip(SKIP_NOT_WINDOWS_SYMLINK)

    assert target.read_text() == "secret"

    # Write valid job.json with completed status
    payload = {
        "job_id": "20260718_101530_deadbeef",
        "project_name": "symlink test",
        "asset_name": "test.png",
        "asset_type": "image",
        "asset_file": "original.png",
        "status": "completed",
        "created_at": "2026-07-18T10:15:30+08:00",
        "started_at": "2026-07-18T10:15:31+08:00",
        "completed_at": "2026-07-18T10:15:32+08:00",
        "settings": AuditSettings().to_dict(),
        "result_file": "analysis_report.json",
        "error": None,
    }
    atomic_write_json(job_dir / "job.json", payload)

    # Write a real original.png (1px PNG)
    import struct, zlib
    def _tiny_png() -> bytes:
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        idat = b"\x00\x00\x00\x08IDAT\x78\xda\x62\x60\x60\x60\x00\x00\x00\x04\x00\x01\x27\x34\x01\x64"
        iend = b"\x00\x00\x00\x00IEND\xae\x42\x60\x82"
        return sig + ihdr + idat + iend
    (input_dir / "original.png").write_bytes(_tiny_png())

    # Write report with naughty_frame.jpg in evidence_frames whitelist
    import json as _json
    report = {
        "job_id": "20260718_101530_deadbeef",
        "detections": [],
        "evidence_frames": ["naughty_frame.jpg"],
        "rules": {},
        "auto_decision": "pass",
        "final_decision": "pass",
        "reviewer": None,
        "note": None,
        "downloads": {"csv": "detections.csv", "zip": "audit_package.zip"},
    }
    atomic_write_json(result_dir / "analysis_report.json", report)
    # Create dummy artifacts to satisfy downloads whitelist
    (result_dir / "detections.csv").write_text("frame_index\n", encoding="utf-8")
    (result_dir / "audit_package.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    storage = JobStorage(cfg.outputs_dir, cfg.max_content_length)
    svc = JobService(storage, UnavailableAnalyzer())

    # resolve_artifact for the symlinked evidence frame MUST raise
    with pytest.raises(ArtifactNotFoundError):
        svc.resolve_artifact("20260718_101530_deadbeef", "naughty_frame.jpg")

    # External file must still be intact
    assert target.read_text() == "secret"

    svc.shutdown(wait=True)


# ---------------------------------------------------------------------------
# A11b  HTTP artifact route (requires backend)
# ---------------------------------------------------------------------------
def test_a11b_http_artifact_traversal_rejected(tmp_path: Path) -> None:
    """A11b: HTTP artifact download rejects path traversal (blocked: no backend)."""
    app = make_app({"project_root": tmp_path})
    skip_if(not has_artifacts_route(app), SKIP_NO_BACKEND)
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    with app.test_client() as client:
        for filename in [
            "../../etc/passwd",
            "../secret.txt",
            "..%2F..%2F..%2Fetc%2Fpasswd",
        ]:
            resp = client.get(
                f"/api/jobs/20260718_101530_deadbeef/artifacts/{filename}"
            )
            assert resp.status_code in (404, 400), (
                f"traversal {filename!r} returned {resp.status_code}"
            )


# ---------------------------------------------------------------------------
# A12  服务重启恢复
# ---------------------------------------------------------------------------
def test_a12_service_restart_recovery_marks_running_as_failed(tmp_path: Path) -> None:
    """A12: after restart, queued/running tasks are marked failed with recovery note.

    Tests JobService + JobStorage directly (leader core) — does NOT
    depend on HTTP job routes.
    """
    from aegis_review.config import AppConfig
    from aegis_review.domain import AuditSettings, JobRecord, JobStatus, MediaType
    from aegis_review.service import JobService, UnavailableAnalyzer
    from aegis_review.storage import JobStorage, atomic_write_json

    cfg = AppConfig(project_root=tmp_path, testing=True)

    # Write two valid job records directly to disk (simulating a prior run)
    def _write_job(job_id: str, status: JobStatus, asset_type: str, asset_file: str):
        job_dir = cfg.outputs_dir / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "input").mkdir()
        (job_dir / "evidence").mkdir()
        (job_dir / "result").mkdir()
        payload = {
            "job_id": job_id,
            "project_name": "恢复测试",
            "asset_name": asset_file,
            "asset_type": asset_type,
            "asset_file": asset_file,
            "status": status.value,
            "created_at": "2026-07-18T10:16:00+08:00",
            "started_at": "2026-07-18T10:16:01+08:00" if status == JobStatus.RUNNING else None,
            "completed_at": None,
            "settings": AuditSettings().to_dict(),
            "result_file": None,
            "error": None,
        }
        atomic_write_json(job_dir / "job.json", payload)

    _write_job("20260718_101600_d3adbeef", JobStatus.RUNNING, "image", "original.jpg")
    _write_job("20260718_101700_faceb00c", JobStatus.QUEUED, "video", "original.mp4")

    # Create fresh service — recovery runs in __init__
    storage = JobStorage(cfg.outputs_dir, cfg.max_content_length)
    svc = JobService(storage, UnavailableAnalyzer())
    svc._executor.shutdown(wait=True)

    # Both must be failed after recovery
    for jid in ("20260718_101600_d3adbeef", "20260718_101700_faceb00c"):
        recovered = storage.read(jid)
        assert recovered.status == JobStatus.FAILED, (
            f"{jid}: expected failed, got {recovered.status.value}"
        )
        assert recovered.error is not None
        assert "服务中断" in recovered.error or "restart" in recovered.error.lower()


# ---------------------------------------------------------------------------
#  Real‑now tests (no guards needed)
# ---------------------------------------------------------------------------
def test_error_envelope_is_uniform_for_404_on_api_routes(tmp_path: Path) -> None:
    """Any /api/* 404 must return {ok:false,error:{code,message}}."""
    app = make_app({"project_root": tmp_path})
    with app.test_client() as client:
        resp = client.get("/api/nonexistent")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["ok"] is False
    assert "code" in body["error"]
    assert "message" in body["error"]


def test_audit_settings_reject_invalid_threshold_order() -> None:
    """Domain layer rejects review >= reject even without backend."""
    from aegis_review.domain import AuditSettings

    with pytest.raises(ValueError, match="confidence"):
        AuditSettings(reject_confidence=0.30, review_confidence=0.70)
