"""Delivery‑artifact and repo‑hygiene checks.

These tests run without backend/CV/model flags.  They ensure:
- validator primitives work on synthetic samples
- output directory skeleton is respected
- repo is free of secrets, large blobs and privacy‑absolute paths
- compose.yaml / Dockerfile follow the documented contract
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from pathlib import Path

import pytest

from tests.fixtures.support import (
    JOB_ID_RE,
    MAX_FILE_SIZE,
    PROJECT_ROOT,
    SKIP_NO_SCRIPT,
    git_available,
    hygiene_scan,
    validate_artifact_dir,
    validate_csv,
    validate_json,
    validate_report_payload,
    validate_zip,
)

# ---------------------------------------------------------------------------
# D0  Self‑test: validators work on good / broken samples
# ---------------------------------------------------------------------------
def test_d0a_json_validator_rejects_bad_json() -> None:
    with pytest.raises(Exception):
        validate_json(b"[not json}", "bad-json")


def test_d0b_csv_validator_detects_missing_columns() -> None:
    sample = "col_a,col_b\n1,2\n"
    with pytest.raises(AssertionError):
        validate_csv(sample.encode(), expected_columns=["col_a", "col_z"], label="cols-missing")


def test_d0c_zip_validator_detects_corruption() -> None:
    good = io.BytesIO()
    with zipfile.ZipFile(good, "w") as zf:
        zf.writestr("a.txt", "hello")
    names = validate_zip(good.getvalue(), "clean-zip")
    assert "a.txt" in names

    with pytest.raises(Exception):
        validate_zip(b"this is not a zip file", "bad-zip")


# ---------------------------------------------------------------------------
# D1  Output directory skeleton
# ---------------------------------------------------------------------------
def test_d1_output_job_dirs_match_contract() -> None:
    """Scan outputs/ for job dirs; any that exist must match the skeleton."""
    outputs = PROJECT_ROOT / "outputs"
    if not outputs.is_dir():
        pytest.skip("outputs/ does not exist")
    jobs = [d for d in outputs.iterdir() if d.is_dir() and JOB_ID_RE.match(d.name)]
    if not jobs:
        pytest.skip("no job directories in outputs/")

    failures: list[str] = []
    for job_dir in jobs:
        try:
            validate_artifact_dir(job_dir)
        except AssertionError as exc:
            failures.append(f"{job_dir.name}: {exc}")

    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# D2  Repo hygiene: secrets / privacy / large files
# ---------------------------------------------------------------------------
def test_d2_no_secrets_or_privacy_paths_in_tracked_files() -> None:
    if not git_available():
        pytest.skip("git not installed — hygiene scan skipped")
    findings = hygiene_scan(PROJECT_ROOT)
    assert not findings, (
        f"hygiene issues found:\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(findings.items()))
    )


def test_d3_no_large_blobs_beyond_allowlist() -> None:
    """No tracked file (outside models/ and known large bins) exceeds MAX_FILE_SIZE."""
    if not git_available():
        pytest.skip("git not installed — large-blob scan skipped")
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("git ls-files failed")
    tracked = [
        PROJECT_ROOT / p
        for p in result.stdout.split("\0")
        if p.strip() and (PROJECT_ROOT / p).is_file()
    ]

    oversize: list[str] = []
    allowed = {".pt", ".pt", ".zip"}
    for f in sorted(tracked):
        if f.suffix in allowed:
            continue
        if "models" in f.parts:
            continue
        try:
            sz = f.stat().st_size
        except OSError:
            continue
        if sz > MAX_FILE_SIZE:
            oversize.append(f"{f.relative_to(PROJECT_ROOT)} {sz} bytes")

    assert not oversize, "oversized files:\n" + "\n".join(oversize)


def test_d4_outputs_dir_not_committed_except_keep() -> None:
    """Only outputs/.gitkeep should be tracked under outputs/."""
    if not git_available():
        pytest.skip("git not installed — outputs tracking scan skipped")
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "outputs"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    committed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    expected = {"outputs/.gitkeep"}
    extra = set(committed) - expected
    assert not extra, f"unexpected files committed in outputs/: {extra}"


# ---------------------------------------------------------------------------
# D3  compose.yaml / Dockerfile contract
# ---------------------------------------------------------------------------
def test_d5_compose_binds_outputs_rw_and_models_ro() -> None:
    compose = PROJECT_ROOT / "compose.yaml"
    text = compose.read_text(encoding="utf-8")
    assert "./outputs:/workspace/outputs" in text
    assert "./models:/workspace/models:ro" in text


def test_d6_dockerfile_exposes_7880_and_defines_healthcheck() -> None:
    df = PROJECT_ROOT / "Dockerfile"
    text = df.read_text(encoding="utf-8")
    assert "EXPOSE 7880" in text
    assert "HEALTHCHECK" in text


# ---------------------------------------------------------------------------
# D4  package_release script gate smoke test
# ---------------------------------------------------------------------------
def test_d7_release_script_rejects_when_gates_fail() -> None:
    """package_release.py --check should exit non‑zero when precondition fails."""
    script = PROJECT_ROOT / "scripts" / "package_release.py"
    if not script.is_file():
        pytest.skip(SKIP_NO_SCRIPT)

    import subprocess

    result = subprocess.run(
        ["python", str(script), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    # On a project without real model/job/Bugs the script MUST exit != 0
    assert result.returncode != 0, (
        f"release script passed --check but this project has no real model/jobs/bugs\n"
        f"stdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )
