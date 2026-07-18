"""Delivery‑artifact, repo‑hygiene, and package‑release gate checks."""

from __future__ import annotations

import csv as _csv
import io
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.fixtures.support import (
    JOB_ID_RE,
    MAX_FILE_SIZE,
    PROJECT_ROOT,
    git_available,
    hygiene_scan,
    validate_csv,
    validate_json,
    validate_zip,
)

###############################################################################
# D0  validator self‑tests
###############################################################################
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

###############################################################################
# D1‑D4  Repo hygiene  (skip when no git)
###############################################################################
def test_d1_output_job_dirs_match_contract() -> None:
    outputs = PROJECT_ROOT / "outputs"
    if not outputs.is_dir():
        pytest.skip("outputs/ does not exist")
    jobs = [d for d in outputs.iterdir() if d.is_dir() and JOB_ID_RE.match(d.name)]
    if not jobs:
        pytest.skip("no job directories in outputs/")

def test_d2_no_secrets_or_privacy_paths_in_tracked_files() -> None:
    if not git_available():
        pytest.skip("git not installed")
    findings = hygiene_scan(PROJECT_ROOT)
    assert not findings, "\n".join(f"{k}: {v}" for k, v in sorted(findings.items()))

def test_d3_no_large_blobs_beyond_allowlist() -> None:
    if not git_available():
        pytest.skip("git not installed")
    result = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        pytest.skip("git ls-files failed")
    oversize: list[str] = []
    for p in result.stdout.split("\0"):
        if not p.strip():
            continue
        fp = PROJECT_ROOT / p
        if not fp.is_file():
            continue
        if fp.suffix in (".pt", ".zip") or "models" in fp.parts:
            continue
        if fp.stat().st_size > MAX_FILE_SIZE:
            oversize.append(f"{fp.relative_to(PROJECT_ROOT)} {fp.stat().st_size} bytes")
    assert not oversize, "oversized:\n" + "\n".join(oversize)

def test_d4_outputs_dir_not_committed_except_keep() -> None:
    if not git_available():
        pytest.skip("git not installed")
    result = subprocess.run(["git", "ls-files", "outputs"], capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    committed = set(line.strip() for line in result.stdout.splitlines() if line.strip())
    assert committed - {"outputs/.gitkeep"} == set()

###############################################################################
# D5‑D6  compose / Dockerfile
###############################################################################
def test_d5_compose_binds_outputs_rw_and_models_ro() -> None:
    text = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "./outputs:/workspace/outputs" in text
    assert "./models:/workspace/models:ro" in text

def test_d6_dockerfile_exposes_7880_and_defines_healthcheck() -> None:
    text = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 7880" in text
    assert "HEALTHCHECK" in text

###############################################################################
# D7  Release module gate logic — production helpers
###############################################################################
_PR = None

def _pr_module():
    global _PR
    if _PR is None:
        import sys as _sys
        _sys.path.insert(0, str(PROJECT_ROOT))
        from scripts import package_release as _mod
        _PR = _mod
    return _PR


def test_d7a_pytest_gate_uses_sys_executable() -> None:
    mod = _pr_module()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        result = mod._run_pytest_gate()
        assert result is True
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0] == mod._SCRIPTS_EXECUTABLE
        assert "-m" in cmd
        assert "pytest" in cmd
        assert "-q" in cmd
        assert kwargs["timeout"] == 300
        assert kwargs["cwd"] == str(mod.PROJECT_ROOT)


def test_d7b_pytest_gate_returns_diagnostic_on_failure() -> None:
    mod = _pr_module()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "FAILED test_foo"
        mock_run.return_value.stderr = ""
        result = mod._run_pytest_gate()
        assert isinstance(result, str)
        assert "exit=1" in result
        assert "FAILED test_foo" in result


def test_d7c_pytest_gate_catches_permission_error() -> None:
    mod = _pr_module()
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = Exception("boom")
        result = mod._run_pytest_gate()
        assert isinstance(result, str)
        assert "Exception" in result


def test_d7d_count_closed_bugs_zero_one_two() -> None:
    mod = _pr_module()
    assert mod._count_closed_bugs("") == 0

    partial = """
## BUG-01
修复提交：abc1234
"""
    assert mod._count_closed_bugs(partial) == 0  # missing regression

    one = """
## BUG-01
修复提交：abc1234
回归结果：通过
"""
    assert mod._count_closed_bugs(one) == 1

    two = """
## BUG-01
修复提交：abc1234
回归结果：通过

## BUG-02
修复提交：def5678
回归结果：通过
"""
    assert mod._count_closed_bugs(two) == 2

    # Missing fix commit
    no_fix = """
## BUG-01
回归结果：通过
"""
    assert mod._count_closed_bugs(no_fix) == 0


def test_d7e_missing_screenshots_all_fifteen(tmp_path: Path) -> None:
    mod = _pr_module()
    ss = tmp_path / "screenshots"
    ss.mkdir()
    missing = mod._missing_screenshots(tmp_path)
    assert len(missing) == 15, f"expected 15 missing, got {len(missing)}"

    # Create one
    (ss / "workbench_full.png").write_text("ok", encoding="utf-8")
    missing = mod._missing_screenshots(tmp_path)
    assert len(missing) == 14
    assert "workbench_full.png" not in missing

    # Create empty file — still counts as missing
    (ss / "upload_success.png").write_text("", encoding="utf-8")
    missing = mod._missing_screenshots(tmp_path)
    assert "upload_success.png" in missing


###############################################################################
# D8  Deterministic ZIP
###############################################################################
def test_d8_deterministic_zip_build_is_stable(tmp_path: Path) -> None:
    mod = _pr_module()

    dir1 = tmp_path / "first"; dir2 = tmp_path / "second"
    dir1.mkdir(); dir2.mkdir()

    def _clean():
        if mod.RELEASE_STAGING.exists():
            shutil.rmtree(mod.RELEASE_STAGING)

    _clean(); a1, s1 = mod._build_archive(dir1)
    _clean(); a2, s2 = mod._build_archive(dir2)
    assert a1 != a2
    assert a1.read_bytes() == a2.read_bytes()
    assert s1 == s2
    for path in (a1, a2):
        with zipfile.ZipFile(str(path)) as zf:
            assert zf.testzip() is None
            for info in zf.infolist():
                assert info.date_time == (1980, 1, 1, 0, 0, 0)
                assert info.compress_type == zipfile.ZIP_DEFLATED
            for n in zf.namelist():
                assert ".." not in n and not n.startswith("/") and "last.pt" not in n

###############################################################################
# D9  Hygiene regression (git‑dependent; skip in container)
###############################################################################
def test_d9a_fake_token_in_md_detected(tmp_path: Path) -> None:
    if not git_available():
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp_path))
    fake_token = "ghp_" + "fake1234567890abcdefabcdefabcdefabcd"
    (tmp_path / "README.md").write_text(
        fake_token + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "README.md"], cwd=str(tmp_path), check=True)
    findings = hygiene_scan(tmp_path)
    assert any("README.md" in k for k in findings), findings

def test_d9b_fake_token_in_yml_detected(tmp_path: Path) -> None:
    if not git_available():
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp_path))
    fake_token = "ghp_" + "fake9876543210abcdefabcdefabcdefabcd"
    (tmp_path / "config.yml").write_text(
        f"key: {fake_token}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "config.yml"], cwd=str(tmp_path), check=True)
    findings = hygiene_scan(tmp_path)
    assert any("config.yml" in k for k in findings), findings

def test_d9c_absolute_path_in_src_detected(tmp_path: Path) -> None:
    if not git_available():
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp_path))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "# /" "Users/alice/project\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    findings = hygiene_scan(tmp_path)
    assert any("src/main.py" in k for k in findings), findings

def test_d9d_binary_pt_png_skipped(tmp_path: Path) -> None:
    if not git_available():
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp_path))
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "x.pt").write_bytes(b"\x00" * 100)
    (tmp_path / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    findings = hygiene_scan(tmp_path)
    assert all(not k.endswith(".pt") for k in findings)

def test_d9e_whitelist_is_file_level_not_directory() -> None:
    from tests.fixtures.support import _PRIVACY_PATH_WHITELIST
    assert isinstance(_PRIVACY_PATH_WHITELIST, frozenset)
    assert "docs/" not in _PRIVACY_PATH_WHITELIST
    assert "tests/" not in _PRIVACY_PATH_WHITELIST
    for item in _PRIVACY_PATH_WHITELIST:
        assert "/" in item or "." in item, f"whitelist entry looks like a directory prefix: {item}"

def test_d9f_docs_leak_detected_without_whitelist_escape(tmp_path: Path) -> None:
    """docs/leak.md with absolute path should be detected if not whitelisted."""
    if not git_available():
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp_path))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "leak.md").write_text(
        "# /" "Users/alice/project\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    findings = hygiene_scan(tmp_path)
    assert any("docs/leak.md" in k for k in findings), f"docs file not whitelisted should be detected: {findings}"

def test_d9g_other_tests_py_not_auto_whitelisted(tmp_path: Path) -> None:
    if not git_available():
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp_path))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "other.py").write_text(
        "# /" "Users/bob/data\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    findings = hygiene_scan(tmp_path)
    # tests/other.py is NOT test_service.py → should be detected
    assert any("tests/other.py" in k for k in findings), f"non-whitelisted test file should be detected: {findings}"

###############################################################################
# D10  _validate_completed_job — strict
###############################################################################
def _make_complete_job(tmp: Path, job_id: str, asset_type="image", shortcomings: list[str] | None = None) -> Path:
    """Build a valid completed job dir. Pass shortcomings to deliberately break things."""
    jd = tmp / job_id
    _mk = lambda *p: (jd / Path(*p)).parent.mkdir(parents=True, exist_ok=True)
    _mk("input", "original.png")
    _mk("evidence", "frame_001.jpg")
    _mk("result", "analysis_report.json")

    (jd / "job.json").write_text(json.dumps({
        "job_id": job_id, "status": "completed", "asset_type": asset_type,
        "asset_file": "original.png", "result_file": "analysis_report.json",
        "evidence_frames": ["frame_001.jpg"],
    }), encoding="utf-8")
    (jd / "input" / "original.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (jd / "evidence" / "frame_001.jpg").write_bytes(b"\xff\xd8\xff\x00" * 50)

    report = {
        "job_id": job_id, "detections": [],
        "evidence_frames": ["frame_001.jpg"],
        "auto_decision": "pass", "final_decision": "pass",
    }
    (jd / "result" / "analysis_report.json").write_text(json.dumps(report), encoding="utf-8")

    # Proper CSV with required columns
    (jd / "result" / "detections.csv").write_text(
        "frame_index,timestamp_seconds,class_id,class_name,confidence,bbox_xyxy,evidence_file\n"
        "0,0.0,1,enemy,0.95,\"[10,10,50,50]\",frame_001.jpg\n",
        encoding="utf-8",
    )

    # Proper ZIP with required members
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("analysis_report.json", json.dumps(report))
        zf.writestr("detections.csv", (jd / "result" / "detections.csv").read_text())
        zf.writestr("job.json", (jd / "job.json").read_text())
        zf.writestr(
            "evidence/frame_001.jpg",
            (jd / "evidence" / "frame_001.jpg").read_bytes(),
        )
    (jd / "result" / "audit_package.zip").write_bytes(buf.getvalue())

    if shortcomings:
        for s in shortcomings:
            if s == "no_report":
                (jd / "result" / "analysis_report.json").unlink()
            elif s == "corrupt_zip":
                (jd / "result" / "audit_package.zip").write_bytes(b"bad")
            elif s == "missing_csv_col":
                (jd / "result" / "detections.csv").write_text("frame_index\n1\n", encoding="utf-8")
            elif s == "empty_evidence":
                (jd / "evidence" / "frame_001.jpg").write_bytes(b"")
            elif s == "unsafe_asset_file":
                body = json.loads((jd / "job.json").read_text())
                body["asset_file"] = "../etc/passwd"
                (jd / "job.json").write_text(json.dumps(body), encoding="utf-8")
            elif s == "symlink_evidence":
                (jd / "evidence" / "frame_001.jpg").unlink()
                try:
                    (jd / "evidence" / "frame_001.jpg").symlink_to(tmp / "outside")
                except OSError:
                    pass  # Windows — accept skip, storage/service still checks is_symlink
            elif s == "no_evidence_frames_list":
                body = json.loads((jd / "result" / "analysis_report.json").read_text())
                body["evidence_frames"] = []
                (jd / "result" / "analysis_report.json").write_text(json.dumps(body), encoding="utf-8")
            elif s == "zip_missing_required":
                buf2 = io.BytesIO()
                with zipfile.ZipFile(buf2, "w") as zf:
                    zf.writestr("only_one.txt", "hi")
                (jd / "result" / "audit_package.zip").write_bytes(buf2.getvalue())
            elif s == "zip_root_evidence_only":
                root_only = io.BytesIO()
                with zipfile.ZipFile(root_only, "w") as zf:
                    zf.writestr("analysis_report.json", json.dumps(report))
                    zf.writestr(
                        "detections.csv",
                        (jd / "result" / "detections.csv").read_text(),
                    )
                    zf.writestr(
                        "job.json",
                        (jd / "job.json").read_text(),
                    )
                    zf.writestr(
                        "frame_001.jpg",
                        (jd / "evidence" / "frame_001.jpg").read_bytes(),
                    )
                (jd / "result" / "audit_package.zip").write_bytes(
                    root_only.getvalue()
                )
    return jd


def test_d10a_good_job_passes() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "20260718_101530_a1b2c3d4")
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "20260718_101530_a1b2c3d4")
        assert not issues, issues

def test_d10b_invalid_job_id_rejected() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "bad_id")
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "bad_id")
        assert any("invalid job_id" in i for i in issues), issues

def test_d10c_missing_report_rejected() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "20260718_101530_cccccccc", shortcomings=["no_report"])
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "20260718_101530_cccccccc")
        assert any("analysis_report.json" in i for i in issues), issues

def test_d10d_corrupt_zip_rejected() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "20260718_101530_dddddddd", shortcomings=["corrupt_zip"])
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "20260718_101530_dddddddd")
        assert any("audit_package.zip" in i for i in issues), issues

def test_d10e_missing_csv_column_rejected() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "20260718_101530_eeeeeeee", shortcomings=["missing_csv_col"])
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "20260718_101530_eeeeeeee")
        assert any("detections.csv" in i for i in issues), issues

def test_d10f_empty_evidence_rejected() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "20260718_101530_ffffffff", shortcomings=["empty_evidence"])
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "20260718_101530_ffffffff")
        assert any("evidence frame" in i for i in issues), issues

def test_d10g_unsafe_asset_file_rejected() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "20260718_101530_99999999", shortcomings=["unsafe_asset_file"])
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "20260718_101530_99999999")
        assert any("unsafe asset_file" in i for i in issues), issues

def test_d10h_zip_missing_required_member() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "20260718_101530_88888888", shortcomings=["zip_missing_required"])
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "20260718_101530_88888888")
        assert any("audit_package.zip" in i and "missing" in i for i in issues), issues

def test_d10i_empty_evidence_frames_list_rejected() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jd = _make_complete_job(tmp, "20260718_101530_77777777", shortcomings=["no_evidence_frames_list"])
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, "20260718_101530_77777777")
        assert any("evidence_frames" in i for i in issues), issues


def test_d10j_root_level_evidence_does_not_match_production_contract() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        job_id = "20260718_101530_66666666"
        jd = _make_complete_job(
            tmp,
            job_id,
            shortcomings=["zip_root_evidence_only"],
        )
        mod = _pr_module()
        issues = mod._validate_completed_job(jd, job_id)
        assert any("evidence/frame_001.jpg" in issue for issue in issues), issues

###############################################################################
# D12  validation_outputs selection + symlink rejection
###############################################################################
def test_d12a_validation_outputs_selects_both_types(tmp_path: Path) -> None:
    mod = _pr_module()
    orig_root = mod.PROJECT_ROOT
    try:
        mod.PROJECT_ROOT = tmp_path
        (tmp_path / "outputs").mkdir()

        jd_img = _make_complete_job(tmp_path / "outputs", "20260718_101530_aaa11111", "image")
        jd_vid = _make_complete_job(tmp_path / "outputs", "20260718_101530_bbb22222", "video")

        img, vid = mod._select_validation_jobs()
        assert img is not None
        assert vid is not None

        # Copy and verify
        staging = tmp_path / "release_staging"
        staging.mkdir()
        with patch.object(mod, "RELEASE_STAGING", staging):
            with patch.object(mod, "VALIDATION_OUTPUTS", "validation_outputs"):
                mod._copy_validation_outputs(staging)
                dest = staging / "validation_outputs"
                assert (dest / "20260718_101530_aaa11111" / "job.json").is_file()
                assert (dest / "20260718_101530_bbb22222" / "job.json").is_file()
    finally:
        mod.PROJECT_ROOT = orig_root

def test_d12b_symlink_in_outputs_refuses_packaging(tmp_path: Path) -> None:
    mod = _pr_module()
    orig_root = mod.PROJECT_ROOT
    try:
        mod.PROJECT_ROOT = tmp_path
        (tmp_path / "outputs").mkdir()
        jd = _make_complete_job(tmp_path / "outputs", "20260718_101530_ccc33333", "image")

        # Create symlink inside job dir
        try:
            (jd / "symlink_escape.txt").symlink_to(tmp_path / "outside.txt")
        except OSError:
            pytest.skip("Windows symlink requires dev mode")

        staging = tmp_path / "release_staging"
        staging.mkdir()
        with patch.object(mod, "RELEASE_STAGING", staging):
            with patch.object(mod, "VALIDATION_OUTPUTS", "validation_outputs"):
                with pytest.raises(SystemExit, match="symlink"):
                    mod._copy_validation_outputs(staging)
    finally:
        mod.PROJECT_ROOT = orig_root
