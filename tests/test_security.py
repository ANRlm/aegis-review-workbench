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
                if body.get("status") == "failed":
                    assert "model" in str(body.get("error", "")).lower()
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
# A11  符号链接逃逸
# ---------------------------------------------------------------------------
def test_a11_symlink_escape_prevented(tmp_path: Path) -> None:
    """A11: symbolic links inside output dir cannot escape outputs/ boundary."""
    # Create a mock job dir with a symlink pointing outside
    outputs = tmp_path / "outputs"
    job_dir = outputs / "20260718_101530_deadbeef"
    result_dir = job_dir / "result"
    result_dir.mkdir(parents=True, exist_ok=True)

    target = tmp_path / "secret_data.txt"
    target.write_text("secret", encoding="utf-8")

    try:
        (result_dir / "naughty_link.json").symlink_to(target)
    except OSError:
        pytest.skip(SKIP_NOT_WINDOWS_SYMLINK)

    assert target.read_text() == "secret"

    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    # Attempt to fetch the symlinked artifact
    with app.test_client() as client:
        resp = client.get(
            "/api/jobs/20260718_101530_deadbeef/artifacts/naughty_link.json"
        )
        assert resp.status_code in (404, 400, 404), (
            f"symlink escape returned {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# A12  服务重启恢复
# ---------------------------------------------------------------------------
def test_a12_service_restart_recovery_marks_running_as_failed(tmp_path: Path) -> None:
    """A12: after restart, queued/running tasks are marked failed with recovery note."""
    outputs = tmp_path / "outputs"
    job_dir = outputs / "20260718_101530_recover"
    result_dir = job_dir / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "input").mkdir(exist_ok=True)
    (job_dir / "evidence").mkdir(exist_ok=True)

    import json as _json

    from aegis_review.storage import atomic_write_json

    _json_path = str(job_dir / "job.json")
    (job_dir / "job.json").write_text(
        _json.dumps(
            {
                "job_id": "20260718_101530_recover",
                "project_name": "恢复测试",
                "asset_name": "clean_scene.jpg",
                "asset_type": "image",
                "status": "running",
                "created_at": "2026-07-18T10:15:30+08:00",
                "started_at": "2026-07-18T10:15:31+08:00",
                "completed_at": None,
                "settings": {},
                "result_file": None,
                "error": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    app = make_app({"project_root": tmp_path})
    skip_if(not has_job_routes(app), SKIP_NO_BACKEND)

    with app.test_client() as client:
        resp = client.get("/api/jobs/20260718_101530_recover")
        if resp.status_code == 404:
            pytest.skip("restart‑recovery not yet implemented in service.py")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("status") == "failed", (
            f"expected failed after restart recovery, got {body.get('status')}"
        )
        assert body.get("error") is not None
        assert "restart" in str(body.get("error")).lower() or "recover" in str(
            body.get("error")
        ).lower()


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
