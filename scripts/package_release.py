"""Generate deterministic `<surname>_A_day08` release package.

Usage:
  python scripts/package_release.py          # build the archive
  python scripts/package_release.py --list   # dry-run file list
  python scripts/package_release.py --check  # validate gates, exit non-zero if blocked
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1].resolve()
TESTS_DIR = PROJECT_ROOT / "tests"
FIXTURE_SUPPORT = TESTS_DIR / "fixtures" / "support.py"

RELEASE_STAGING = PROJECT_ROOT / "tmp" / "release"
VALIDATION_OUTPUTS = "validation_outputs"

_HAS_FIXTURE_SUPPORT = FIXTURE_SUPPORT.is_file()
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_SCRIPTS_EXECUTABLE = sys.executable


def _load_hygiene() -> dict[str, str]:
    if not _HAS_FIXTURE_SUPPORT:
        return {}
    sys.path.insert(0, str(PROJECT_ROOT))
    from tests.fixtures.support import hygiene_scan
    return hygiene_scan(PROJECT_ROOT)


def _validate_zip(b: bytes) -> None:
    if _HAS_FIXTURE_SUPPORT:
        sys.path.insert(0, str(PROJECT_ROOT))
        from tests.fixtures.support import validate_zip
        validate_zip(b, "self-check")
        return
    with zipfile.ZipFile(io.BytesIO(b)) as zf:
        assert zf.testzip() is None


# ---------------------------------------------------------------------------
ROSTER = PROJECT_ROOT / "docs" / "TEAM_ROSTER.md"
ROSTER_RE = re.compile(r"\|\s*组长/产品与集成\s*\|.*?\|\s*(\S+)\s*\|")


def _extract_surname() -> str:
    if not ROSTER.is_file():
        raise SystemExit(f"missing {ROSTER}")
    text = ROSTER.read_text(encoding="utf-8")
    m = ROSTER_RE.search(text)
    if not m:
        raise SystemExit(f"cannot parse surname from {ROSTER}")
    full_name = m.group(1).strip()
    if not full_name:
        raise SystemExit("surname is empty")
    return full_name[0]


# ---------------------------------------------------------------------------
# Gate checks
# ---------------------------------------------------------------------------
def _git_available() -> bool:
    import shutil as _shutil
    return _shutil.which("git") is not None


def _validate_completed_job(job_dir: Path, job_id: str) -> list[str]:
    """Return a list of issues found; empty means valid."""
    issues: list[str] = []

    jf = job_dir / "job.json"
    if not jf.is_file():
        return [f"missing job.json in {job_dir.name}"]
    try:
        body = json.loads(jf.read_text(encoding="utf-8"))
    except Exception:
        return [f"unparseable job.json in {job_dir.name}"]
    if body.get("status") != "completed":
        issues.append(f"{job_dir.name}: status not completed")
    if body.get("job_id") != job_id:
        issues.append(f"{job_dir.name}: job_id mismatch")
    asset_type = body.get("asset_type", "")
    if asset_type not in ("image", "video"):
        issues.append(f"{job_dir.name}: unknown asset_type")
    asset_file = body.get("asset_file", "")
    original = job_dir / "input" / asset_file
    if not original.is_file() or original.stat().st_size == 0:
        issues.append(f"{job_dir.name}: missing or empty input/{asset_file}")

    # evidence
    evidence = job_dir / "evidence"
    if not evidence.is_dir():
        issues.append(f"{job_dir.name}: missing evidence dir")
    else:
        jpegs = [f for f in evidence.iterdir() if f.suffix.lower() in (".jpg", ".jpeg") and f.stat().st_size > 0]
        if not jpegs:
            issues.append(f"{job_dir.name}: no non-empty jpeg evidence frames")

    result = job_dir / "result"
    # analysis_report.json
    rpt_file = result / "analysis_report.json"
    if not rpt_file.is_file():
        issues.append(f"{job_dir.name}: missing analysis_report.json")
    else:
        try:
            rpt = json.loads(rpt_file.read_text(encoding="utf-8"))
        except Exception:
            issues.append(f"{job_dir.name}: unparseable analysis_report.json")
        else:
            if rpt.get("job_id") != job_id:
                issues.append(f"{job_dir.name}: report job_id mismatch")
            ad = rpt.get("auto_decision")
            if ad not in ("pass", "review", "reject"):
                issues.append(f"{job_dir.name}: invalid auto_decision {ad}")
            fd = rpt.get("final_decision")
            if fd and fd not in ("pass", "review", "reject"):
                issues.append(f"{job_dir.name}: invalid final_decision {fd}")
            for name in rpt.get("evidence_frames", []):
                if not (evidence / name).is_file():
                    issues.append(f"{job_dir.name}: evidence frame {name} missing on disk")

    # detections.csv
    csv_file = result / "detections.csv"
    if not csv_file.is_file():
        issues.append(f"{job_dir.name}: missing detections.csv")
    else:
        try:
            import csv as _csv
            with csv_file.open(encoding="utf-8") as fh:
                reader = _csv.DictReader(fh)
                _ = list(reader)
        except Exception:
            issues.append(f"{job_dir.name}: unreadable detections.csv")

    # audit_package.zip
    zip_file = result / "audit_package.zip"
    if not zip_file.is_file():
        issues.append(f"{job_dir.name}: missing audit_package.zip")
    else:
        try:
            with zipfile.ZipFile(str(zip_file)) as zf:
                if zf.testzip() is not None:
                    issues.append(f"{job_dir.name}: audit_package.zip CRC error")
        except Exception:
            issues.append(f"{job_dir.name}: unopenable audit_package.zip")

    return issues


def _all_gates_pass() -> dict[str, bool | str]:
    gates: dict[str, bool | str] = {}

    if _git_available():
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        gates["git_clean"] = result.stdout.strip() == ""
    else:
        gates["git_clean"] = "git not installed"

    # pytest_pass: use active interpreter
    pytest_diag = ""
    try:
        result = subprocess.run(
            [_SCRIPTS_EXECUTABLE, "-m", "pytest", "-q"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
            timeout=300,
        )
        if result.returncode != 0:
            pytest_diag = (result.stdout + result.stderr)[-500:]
    except subprocess.TimeoutExpired:
        pytest_diag = "timeout"
    except FileNotFoundError:
        pytest_diag = "pytest not found"
    except Exception as exc:
        pytest_diag = str(exc)[:200]
    gates["pytest_pass"] = pytest_diag == ""

    gates["model_present"] = (PROJECT_ROOT / "models" / "aegis_game_best.pt").is_file()

    # Completed image + video jobs with strict validation
    outputs = PROJECT_ROOT / "outputs"
    img_ok = vid_ok = False
    if outputs.is_dir():
        for job_dir in sorted(outputs.iterdir()):
            if not job_dir.is_dir():
                continue
            jf = job_dir / "job.json"
            if not jf.is_file():
                continue
            try:
                body = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            if body.get("status") != "completed":
                continue
            # Strict validation
            issues = _validate_completed_job(job_dir, job_dir.name)
            if issues:
                continue
            at = body.get("asset_type", "")
            if at == "image" and not img_ok:
                img_ok = True
            elif at == "video" and not vid_ok:
                vid_ok = True
    gates["completed_image_job"] = img_ok
    gates["completed_video_job"] = vid_ok

    # Bug gate: strict parsing
    bug_doc = PROJECT_ROOT / "docs" / "BUG_RECORD.md"
    bug_count = 0
    if bug_doc.is_file():
        text = bug_doc.read_text(encoding="utf-8")
        # Find Bug sections
        for m in re.finditer(r"## BUG-(\d+)", text):
            section = text[m.end():]
            next_section = re.search(r"\n## ", section)
            if next_section:
                section = section[:next_section.start()]
            # Requires: fix commit + regression result
            has_fix = bool(re.search(r"修复提交[：:]\s*([a-f0-9]{7,40})", section))
            has_regression = bool(re.search(r"回归结果[：:]\s*通过", section))
            if has_fix and has_regression:
                bug_count += 1
    gates["closed_bugs_ge_2"] = bug_count >= 2

    # Screenshots: exact 15 named files from SCREENSHOT_INDEX
    required_ss = [
        "workbench_full.png", "upload_success.png", "analysis_in_progress.png",
        "result_pass.png", "result_review.png", "result_reject.png",
        "evidence_frame.png", "manual_review.png", "history.png",
        "stats.png", "download_json.png", "download_csv.png",
        "download_zip.png", "error_unsupported.png", "docker_health.png",
    ]
    ss_dir = PROJECT_ROOT / "screenshots"
    missing_ss: list[str] = []
    if ss_dir.is_dir():
        for name in required_ss:
            path = ss_dir / name
            if not path.is_file() or path.stat().st_size == 0:
                missing_ss.append(name)
    else:
        missing_ss = list(required_ss)
    gates["screenshots_ok"] = len(missing_ss) == 0

    hygiene = _load_hygiene()
    gates["hygiene_clean"] = len(hygiene) == 0

    return gates


def _translate(gates: dict[str, bool | str]) -> tuple[bool, list[str]]:
    passed = all(v is True for v in gates.values())
    lines: list[str] = []
    for name, ok in sorted(gates.items()):
        mark = "[PASS]" if ok is True else "[FAIL]"
        lines.append(f"  {mark} {name}  ({ok})")
    return passed, lines


# ---------------------------------------------------------------------------
# File manifest
# ---------------------------------------------------------------------------
MANIFEST_PATTERNS = [
    "app.py", "requirements.txt", "environment.yml",
    "Dockerfile", "compose.yaml", ".dockerignore", ".editorconfig", "pytest.ini",
    "README.md", "AGENTS.md",
    "aegis_review/**/*.py",
    "static/**", "templates/**",
    "prompts/**/*.md",
    "scripts/*.py",
    "tests/**/*.py",
    "models/aegis_game_best.pt",
    "docs/**/*.md",
    "screenshots/*.png", "screenshots/*.jpg", "screenshots/*.jpeg",
    "dataset/**",
    "training_evidence/**",
]

EXCLUDE_PREFIXES = (
    ".git/", "__pycache__/", "node_modules/", "tmp/", "outputs/", ".pytest_cache/",
    "training_runs/", "runs/",
)
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".tmp", ".log")


def _collect_files() -> list[Path]:
    collected: list[Path] = []
    for pattern in MANIFEST_PATTERNS:
        for path in sorted(PROJECT_ROOT.glob(pattern)):
            if path.is_dir():
                continue
            rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
                continue
            if any(rel.endswith(s) for s in EXCLUDE_SUFFIXES):
                continue
            if "models/" in rel and path.suffix == ".pt" and path.name != "aegis_game_best.pt":
                continue
            if "last.pt" in rel:
                continue
            if rel not in (str(p.relative_to(PROJECT_ROOT)).replace("\\", "/") for p in collected):
                collected.append(path)
    collected.sort()
    return collected


# ---------------------------------------------------------------------------
# validation_outputs selection
# ---------------------------------------------------------------------------
def _select_validation_jobs() -> tuple[str | None, str | None]:
    """Return (image_job_id, video_job_id) – the first valid completed job of each type."""
    outputs = PROJECT_ROOT / "outputs"
    img_jid = vid_jid = None
    if not outputs.is_dir():
        return None, None
    for job_dir in sorted(outputs.iterdir()):
        if not job_dir.is_dir():
            continue
        jf = job_dir / "job.json"
        if not jf.is_file():
            continue
        try:
            body = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if body.get("status") != "completed":
            continue
        issues = _validate_completed_job(job_dir, job_dir.name)
        if issues:
            continue
        at = body.get("asset_type", "")
        if at == "image" and img_jid is None:
            img_jid = job_dir.name
        elif at == "video" and vid_jid is None:
            vid_jid = job_dir.name
        if img_jid and vid_jid:
            break
    return img_jid, vid_jid


def _copy_validation_outputs(staging_root: Path) -> None:
    img_jid, vid_jid = _select_validation_jobs()
    dest = staging_root / VALIDATION_OUTPUTS
    dest.mkdir(parents=True, exist_ok=True)

    outputs = PROJECT_ROOT / "outputs"
    for jid in (img_jid, vid_jid):
        if jid is None:
            continue
        src = outputs / jid
        dst = dest / jid
        if dst.exists():
            shutil.rmtree(dst)
        # Walk and copy, rejecting symlinks
        for item in src.rglob("*"):
            if item.is_symlink():
                raise SystemExit(f"refusing to package symlink in outputs: {item}")
            if item.is_dir():
                (dst / item.relative_to(src)).mkdir(parents=True, exist_ok=True)
            else:
                shutil.copy2(item, dst / item.relative_to(src))


# ---------------------------------------------------------------------------
# Build archive
# ---------------------------------------------------------------------------
def _build_archive(package_dir: Path) -> tuple[Path, str]:
    if RELEASE_STAGING.exists():
        shutil.rmtree(RELEASE_STAGING)
    RELEASE_STAGING.mkdir(parents=True)

    for src in _collect_files():
        dst = RELEASE_STAGING / src.relative_to(PROJECT_ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    _copy_validation_outputs(RELEASE_STAGING)

    archive_path = package_dir / f"{_extract_surname()}_A_day08.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(archive_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(RELEASE_STAGING.rglob("*")):
            if f.is_dir():
                continue
            arcname = str(f.relative_to(RELEASE_STAGING)).replace("\\", "/")
            info = zipfile.ZipInfo(arcname)
            info.date_time = _ZIP_EPOCH
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(f, "rb") as fh:
                zf.writestr(info, fh.read())

    sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return archive_path, sha


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="release package builder")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dest", default=str(PROJECT_ROOT))
    args = parser.parse_args()

    surname = _extract_surname()
    if not surname or not surname.strip():
        raise SystemExit("surname is empty")
    package_name = f"{surname}_A_day08"

    if args.list:
        print(f"# package: {package_name}.zip")
        for f in _collect_files():
            print(str(f.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        return

    if args.check:
        gates = _all_gates_pass()
        passed, lines = _translate(gates)
        print(f"# package_release --check  (target: {package_name}.zip)")
        for line in lines:
            print(line)
        if not passed:
            print(f"\nBLOCKED: {package_name} cannot be generated.")
        else:
            print(f"\nAll gates pass — ready for {package_name}.zip")
        sys.exit(0 if passed else 1)

    print("[package_release] checking gates ...")
    gates = _all_gates_pass()
    passed, lines = _translate(gates)
    for line in lines:
        print(line)
    if not passed:
        print(f"\nBLOCKED: {package_name}.zip refused.")
        sys.exit(1)

    print(f"\n[package_release] building {package_name}.zip ...")
    archive, sha = _build_archive(Path(args.dest))
    print(f"  {archive}")
    print(f"  SHA256: {sha}")
    _validate_zip(archive.read_bytes())
    print("  ZIP CRC: OK")
    print(f"\nDone: {package_name}.zip")


if __name__ == "__main__":
    main()
