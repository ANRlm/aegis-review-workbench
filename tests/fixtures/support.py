"""QA shared helpers that are importable by acceptance / security / delivery
test modules.

Keep this module self-contained; do NOT depend on conftest.py or other
role-owned files.
"""

from __future__ import annotations

import csv
from contextlib import contextmanager
import io
import json
import os
import re
from threading import Event
import zipfile
from pathlib import Path
from typing import Any, Iterator

SKIP_NOT_WINDOWS_SYMLINK = "Windows 开发模式未启用，无法创建符号链接"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
FIXTURE_MEDIA = HERE / "media"
PROJECT_ROOT = HERE.parents[1]

JOB_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}$")


class StaticDetector:
    """Return deterministic JSON-native detections for every sampled frame."""

    def __init__(self, detections: list[dict[str, Any]]) -> None:
        self._detections = detections

    def detect(
        self,
        _frame: Any,
        confidence: float,
    ) -> list[dict[str, Any]]:
        return [
            {
                **detection,
                "bbox_xyxy": list(detection["bbox_xyxy"]),
            }
            for detection in self._detections
            if float(detection["confidence"]) >= float(confidence)
        ]


class BlockingAnalyzer:
    """Hold a real AnalysisRunner until a test explicitly releases it."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.started = Event()
        self.release = Event()

    def __call__(
        self,
        input_path: Path,
        evidence_dir: Path,
        result_dir: Path,
        settings: Any,
    ) -> Any:
        self.started.set()
        if not self.release.wait(timeout=10):
            raise RuntimeError("QA blocking analyzer was not released")
        return self._delegate(
            input_path,
            evidence_dir,
            result_dir,
            settings,
        )


def static_analyzer(detections: list[dict[str, Any]]) -> Any:
    """Bind a deterministic Detector to the production CV pipeline."""
    from aegis_review.cv import bind_analyzer

    return bind_analyzer(detector=StaticDetector(detections))


def real_model_analyzer() -> Any:
    """Bind the repository's trained model independently of temp project roots."""
    from aegis_review.cv import bind_analyzer

    return bind_analyzer(
        model_path=PROJECT_ROOT / "models" / "aegis_game_best.pt",
    )


# ---------------------------------------------------------------------------
# Flask test‑client helpers
# ---------------------------------------------------------------------------


def make_app(config_kwargs=None, *, analyzer=None):
    """Return a Flask app configured for QA testing.

    Temp projects default to ``testing=True`` so production environment
    variables cannot redirect their model path.  A supplied analyzer is
    injected through the public application-factory seam.
    """
    from aegis_review import create_app
    from aegis_review.config import AppConfig
    from aegis_review.service import JobService
    from aegis_review.storage import JobStorage

    kwargs = dict(config_kwargs or {})
    kwargs.setdefault("testing", True)
    cfg = AppConfig(**kwargs)
    if analyzer is None:
        return create_app(cfg)
    service = JobService(
        storage=JobStorage(
            cfg.outputs_dir,
            cfg.max_content_length,
        ),
        analyzer=analyzer,
    )
    return create_app(cfg, job_service=service)


@contextmanager
def managed_app(config_kwargs=None, *, analyzer=None) -> Iterator[Any]:
    """Yield a QA app and always stop its executor before deleting temp files."""
    app = make_app(config_kwargs, analyzer=analyzer)
    try:
        yield app
    finally:
        app.extensions["aegis_job_service"].shutdown(wait=True)


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
            if job.get("status") == "failed":
                raise AssertionError(
                    f"job {job_id} failed: {job.get('error') or '未知错误'}"
                )
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
