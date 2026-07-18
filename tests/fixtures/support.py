"""QA shared helpers that are importable by acceptance / security / delivery
test modules.

Keep this module self-contained; do NOT depend on conftest.py or other
role-owned files.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest  # allowed – tests/fixtures/ is QA-exclusive

# ---------------------------------------------------------------------------
# Skip‑reason constants (quoted verbatim in the test report)
# ---------------------------------------------------------------------------
SKIP_NO_BACKEND = "阻塞：后端 feature/backend-api 尚未合并，job API 不可用"
SKIP_NO_CV = "阻塞：CV feature/cv-pipeline 尚未合并，分析管线不可用"
SKIP_NO_MODEL = "阻塞：模型文件 aegis_game_best.pt 缺失，无法真实推理"
SKIP_NO_DETECTOR_SEAM = "阻塞：CV 注入式假 Detector 焊缝尚未暴露，待 CV 合并后启用"
SKIP_NO_FRONTEND = "阻塞：前端 feature/frontend-workbench 尚未合并"
SKIP_NOT_WINDOWS_SYMLINK = "Windows 开发模式未启用，无法创建符号链接"
SKIP_TIMING_RACE = "跳过：分析耗时不足以测量运行中删除（视频任务合并后可靠）"
SKIP_NO_SCRIPT = "阻塞：scripts/package_release.py 尚不存在（待阶段 5 提交）"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
FIXTURE_MEDIA = HERE / "media"
PROJECT_ROOT = HERE.parents[1]

JOB_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}$")

# ---------------------------------------------------------------------------
# Capability probes
# ---------------------------------------------------------------------------


def _has_route(app, method: str, path: str) -> bool:
    """True if `app` owns a handler for *exactly* this route."""
    adapter = app.url_map.bind("")
    try:
        adapter.match(path, method=method)
    except Exception:
        return False
    return True


def has_job_routes(app) -> bool:
    return _has_route(app, "POST", "/api/jobs")


def has_analyze_route(app) -> bool:
    return _has_route(app, "POST", "/api/jobs/ANY/analyze")


def has_report_route(app) -> bool:
    return _has_route(app, "GET", "/api/jobs/ANY/report")


def has_artifacts_route(app) -> bool:
    return _has_route(app, "GET", "/api/jobs/ANY/artifacts/filename")


def has_delete_route(app) -> bool:
    return _has_route(app, "DELETE", "/api/jobs/ANY")


def has_statistics_route(app) -> bool:
    return _has_route(app, "GET", "/api/stats")


def has_review_route(app) -> bool:
    return _has_route(app, "PATCH", "/api/jobs/ANY/review")


# ---------------------------------------------------------------------------
# Flask test‑client helpers
# ---------------------------------------------------------------------------


def make_app(config_kwargs=None):
    """Return a Flask app configured for QA testing.

    The app uses the *real* project root unless config_kwargs explicitly
    overrides it (e.g. ``project_root=tmp_path``).
    """
    from aegis_review import create_app
    from aegis_review.config import AppConfig

    cfg = AppConfig(**(config_kwargs or {}))
    return create_app(cfg)


def upload(client, asset_path: Path, project_name: str = "QA验收", settings=None):
    """POST /api/jobs with a file attachment.

    Returns the Flask test‑client response.
    """
    data = {"project_name": project_name}
    if settings is not None:
        data["settings"] = json.dumps(settings, ensure_ascii=False)
    with open(asset_path, "rb") as fh:
        data["asset"] = (fh, asset_path.name)
        return client.post(
            "/api/jobs",
            data=data,
            content_type="multipart/form-data",
        )


def poll(client, job_id: str, target: str, timeout: float = 30.0, interval: float = 0.5):
    """Call GET /api/jobs/<job_id> until status == *target* or *timeout*.

    Per docs/API.md, the response envelope is ``{"ok":true,"job":{...}}``.
    Returns the full response body (the outer dict) or raises TimeoutError.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        if resp.status_code == 200:
            body = resp.get_json() or {}
            job = body.get("job") or {}
            if job.get("status") == target:
                return body
        time.sleep(interval)
    raise TimeoutError(f"job {job_id} did not reach status={target} within {timeout}s")


# ---------------------------------------------------------------------------
# High‑level flow (for normal‑case tests)
# ---------------------------------------------------------------------------


def flow_image_complete(
    client, asset: Path, project_name: str = "QA验收图片", settings=None
):
    """POST → analyze → poll completed → get report.  Returns (job_id, report)."""
    resp = upload(client, asset, project_name, settings)
    assert resp.status_code == 201, resp.get_json()
    job_id = resp.get_json()["job"]["job_id"]
    assert JOB_ID_RE.match(job_id), f"bad job_id format: {job_id}"

    resp = client.post(f"/api/jobs/{job_id}/analyze")
    assert resp.status_code == 202, resp.get_json()

    poll(client, job_id, "completed")

    resp = client.get(f"/api/jobs/{job_id}/report")
    assert resp.status_code == 200, resp.get_json()
    report = resp.get_json()["report"]
    return job_id, report


# ---------------------------------------------------------------------------
# Validation helpers  (also used by scripts/package_release.py)
# ---------------------------------------------------------------------------


def validate_json(json_bytes: bytes, label: str = "JSON") -> dict[str, Any]:
    """Parse *json_bytes* and return the payload dict; raises on failure."""
    assert len(json_bytes) > 0, f"{label} is zero-length"
    payload = json.loads(json_bytes)
    assert isinstance(payload, dict), f"{label} root is not an object"
    return payload


def validate_csv(
    csv_bytes: bytes,
    expected_columns: list[str] | None = None,
    min_rows: int = 0,
    label: str = "CSV",
) -> tuple[list[str], list[dict[str, str]]]:
    """Parse *csv_bytes*; return (columns, rows)."""
    assert len(csv_bytes) > 0, f"{label} is zero-length"
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    rows = list(reader)
    columns = reader.fieldnames or []
    if expected_columns is not None:
        missing = set(expected_columns) - set(columns)
        assert not missing, f"{label} missing columns: {missing}"
    assert len(rows) >= min_rows, f"{label}: {len(rows)} rows, expected >= {min_rows}"
    return columns, rows


def validate_zip(zip_bytes: bytes, label: str = "ZIP") -> list[str]:
    """Verify *zip_bytes* via ``zipfile.testzip()``; return namelist."""
    assert len(zip_bytes) > 0, f"{label} is zero-length"
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert zf.testzip() is None, f"{label} CRC error in: {zf.testzip()}"
        return zf.namelist()


def validate_artifact_dir(job_dir: Path) -> None:
    """Check that *job_dir* contains the expected output skeleton."""
    assert job_dir.is_dir(), f"missing job dir: {job_dir}"
    for name in ("job.json", "input", "evidence", "result"):
        assert (job_dir / name).exists(), f"missing {name} in {job_dir}"
    result = job_dir / "result"
    for name in ("analysis_report.json", "detections.csv", "audit_package.zip"):
        assert (result / name).is_file(), f"missing {name} in {result}"


def validate_report_payload(report: dict[str, Any]) -> None:
    """Required fields per docs/API.md."""
    assert "job_id" in report
    assert isinstance(report.get("detections"), list)
    assert isinstance(report.get("evidence_frames"), list)
    assert "auto_decision" in report
    assert "final_decision" in report


def error_matches(resp, status: int, code: str) -> bool:
    """Check that *resp* has error envelope matching status+code."""
    if resp.status_code != status:
        return False
    body = resp.get_json() or {}
    return body.get("ok") is False and body.get("error", {}).get("code") == code


# ---------------------------------------------------------------------------
# Repo‑hygiene helpers
# ---------------------------------------------------------------------------
SECRET_PATTERNS: list[tuple[str, str]] = [
    (
        r"A(?:KIA|SIA|WS)[A-Z0-9]{16,}",
        "probable AWS access key",
    ),
    (
        r"-----BEGIN\s(?:RSA|EC|DSA|OPENSSH)\sPRIVATE\sKEY",
        "private key header",
    ),
    (
        r"ghp_[A-Za-z0-9]{36}",
        "GitHub personal access token (classic)",
    ),
    (
        r"github_pat_[A-Za-z0-9_]{22,}",
        "GitHub fine-grained token",
    ),
]

PRIVACY_PATTERNS: list[str] = [
    r"C:\\Users\\[^\\\s]+",
    r"/home/[^/\s]+",
    r"/Users/[^/\s]+",
    r"\\Users\\[^\\\s]+",
]

MAX_FILE_SIZE = 5 * 1024 * 1024

# Extensions we entirely skip for text scanning (binary / too large)
BINARY_EXTENSIONS = frozenset({".pt", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mov", ".ico"})

IGNORED_FILES = frozenset({"poetry.lock", "package-lock.json", "yarn.lock"})

# File-level whitelist for privacy paths (exact relative paths).
# These specific files intentionally contain example absolute paths for testing.
_PRIVACY_PATH_WHITELIST: frozenset[str] = frozenset({
    "tests/test_service.py",
})


def git_available() -> bool:
    """True if ``git`` is on PATH (needed for hygiene / delivery scans)."""
    import shutil as _shutil

    return _shutil.which("git") is not None


def hygiene_scan(project_root: Path) -> dict[str, str]:
    """Scan tracked files for secrets, privacy paths and oversized blobs.

    Returns ``{finding: description}``.  Empty dict means clean.
    Returns ``{"git": "not installed"}`` when git is unavailable.
    """
    import subprocess

    if not git_available():
        return {"git": "not installed — cannot scan tracked files"}

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
        check=False,
    )
    if result.returncode != 0:
        return {"hygiene": "git ls-files failed"}

    tracked = [
        project_root / p
        for p in result.stdout.split("\0")
        if p.strip() and (project_root / p).is_file()
    ]

    findings: dict[str, str] = {}
    for file_path in tracked:
        if (
            str(file_path).startswith(str(project_root / "models") + os.sep)
            and file_path.suffix == ".pt"
        ):
            continue  # white‑listed model weights

        size = file_path.stat().st_size
        # Large‑file check applies to ALL files regardless of extension
        if size > MAX_FILE_SIZE and file_path.suffix not in (".pt", ".zip"):
            findings[str(file_path.relative_to(project_root))] = (
                f"large file {size} bytes > {MAX_FILE_SIZE}"
            )

        # Skip binary extensions for text scanning
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            continue
        if file_path.name in IGNORED_FILES:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pattern, desc in SECRET_PATTERNS:
            m = re.search(pattern, text)
            if m:
                findings[str(file_path.relative_to(project_root))] = (
                    f"{desc}: ...{m.group()[:30]}..."
                )

        for pattern in PRIVACY_PATTERNS:
            m = re.search(pattern, text)
            if m:
                rel = str(file_path.relative_to(project_root)).replace("\\", "/")
                if rel not in _PRIVACY_PATH_WHITELIST:
                    findings[rel] = f"absolute path: {m.group()}"

    return findings


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
def skip_if(condition: bool, reason: str) -> None:
    """Convenience: call ``pytest.skip`` when *condition* is True."""
    if condition:
        pytest.skip(reason)
