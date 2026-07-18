"""Generate deterministic `<surname>_A_day08` release package."""

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
# Selected real jobs must land in the runtime directory so the extracted
# submission can reopen them immediately.
VALIDATION_OUTPUTS = "outputs"

_HAS_FIXTURE_SUPPORT = FIXTURE_SUPPORT.is_file()
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_SCRIPTS_EXECUTABLE = sys.executable

CSV_REQUIRED_COLUMNS = [
    "frame_index", "timestamp_seconds", "class_id", "class_name",
    "confidence", "bbox_xyxy", "evidence_file",
]

JOB_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}$")

# ---------------------------------------------------------------------------
# Helper: safe basename
# ---------------------------------------------------------------------------
def _safe_basename(name: str) -> bool:
    return (
        isinstance(name, str) and bool(name) and name not in {".", ".."}
        and "/" not in name and "\\" not in name
        and not Path(name).is_absolute()
    )


# ---------------------------------------------------------------------------
# Hygiene support
# ---------------------------------------------------------------------------
def _load_hygiene() -> dict[str, str]:
    if not _HAS_FIXTURE_SUPPORT:
        return {}
    sys.path.insert(0, str(PROJECT_ROOT))
    from tests.fixtures.support import hygiene_scan
    return hygiene_scan(PROJECT_ROOT)


def _validate_zip_bytes(b: bytes) -> None:
    if _HAS_FIXTURE_SUPPORT:
        sys.path.insert(0, str(PROJECT_ROOT))
        from tests.fixtures.support import validate_zip
        validate_zip(b, "self-check")
        return
    with zipfile.ZipFile(io.BytesIO(b)) as zf:
        assert zf.testzip() is None


# ---------------------------------------------------------------------------
# Surname
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
# Gate primitives — extracted for independent testing
# ---------------------------------------------------------------------------
def _git_available() -> bool:
    import shutil as _shutil

    if _shutil.which("git") is None:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _run_pytest_gate() -> bool | str:
    """Return True on pass, or a sanitised diagnostic string on failure/non-zero."""
    import re as _re
    try:
        result = subprocess.run(
            [_SCRIPTS_EXECUTABLE, "-m", "pytest", "-q"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return "pytest timeout (>300s)"
    except FileNotFoundError:
        return "pytest not found"
    except Exception as exc:
        return f"pytest invocation error: {type(exc).__name__}"

    if result.returncode == 0:
        return True

    combined = result.stdout + result.stderr
    # Sanitise absolute paths and user directories
    privacy_path = (
        r'(?:[A-Za-z]:\\Users\\|/' r'home/|/' r'Users/)[^/\s\\]+'
    )
    sanitised = _re.sub(privacy_path, '<user>/', combined)
    sanitised = _re.sub(r'(?:[A-Za-z]:/\S+?/aegis-review-workbench)', '<repo>', sanitised)
    tail = sanitised[-700:] if len(sanitised) > 700 else sanitised
    return f"pytest exit={result.returncode}: {tail}"


def _count_closed_bugs(text: str) -> int:
    """Count Bug sections that have both a fix commit hash and a passing regression result."""
    count = 0
    for m in re.finditer(r"## BUG-(\d+)", text):
        section = text[m.end():]
        ns = re.search(r"\n## ", section)
        if ns:
            section = section[:ns.start()]
        has_fix = bool(re.search(r"修复提交[：:]\s*([a-f0-9]{7,40})", section))
        has_reg = bool(re.search(r"回归结果[：:]\s*通过", section))
        if has_fix and has_reg:
            count += 1
    return count


_MISSING_SCREENSHOTS = [
    "workbench_full.png", "upload_success.png", "analysis_in_progress.png",
    "result_pass.png", "result_review.png", "result_reject.png",
    "evidence_frame.png", "manual_review.png", "history.png",
    "stats.png", "download_json.png", "download_csv.png",
    "download_zip.png", "error_unsupported.png", "docker_health.png",
]


def _missing_screenshots(root: Path) -> list[str]:
    """Return list of required screenshot filenames that are missing or empty."""
    ss_dir = root / "screenshots"
    missing: list[str] = []
    for name in _MISSING_SCREENSHOTS:
        path = ss_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
    return missing


# ---------------------------------------------------------------------------
# Completed job validation — strict
# ---------------------------------------------------------------------------
def _validate_completed_job(job_dir: Path, job_id: str) -> list[str]:
    """Return issues found; empty = valid."""
    issues: list[str] = []

    if not JOB_ID_RE.fullmatch(job_id):
        issues.append(f"{job_dir.name}: invalid job_id format")
        return issues
    if job_dir.is_symlink():
        return [f"{job_dir.name}: job directory is a symlink"]

    jf = job_dir / "job.json"
    if jf.is_symlink() or not jf.is_file():
        issues.append(f"{job_dir.name}: missing or symlink job.json")
        return issues
    try:
        body = json.loads(jf.read_text(encoding="utf-8"))
    except Exception:
        return [f"{job_dir.name}: unparseable job.json"]

    if body.get("status") != "completed":
        issues.append(f"{job_dir.name}: status not completed")
    if body.get("job_id") != job_id:
        issues.append(f"{job_dir.name}: job_id mismatch")
    asset_type = body.get("asset_type", "")
    if asset_type not in ("image", "video"):
        issues.append(f"{job_dir.name}: unknown asset_type")
    asset_file = body.get("asset_file", "")
    if not _safe_basename(asset_file):
        issues.append(f"{job_dir.name}: unsafe asset_file {asset_file!r}")
        return issues
    input_dir = job_dir / "input"
    original = input_dir / asset_file
    if original.is_symlink() or not original.is_file() or original.stat().st_size == 0:
        issues.append(f"{job_dir.name}: missing/empty/symlink input/{asset_file}")

    result = job_dir / "result"

    # analysis_report.json — read early so evidence_frames can reference it
    rpt_file = result / "analysis_report.json"
    rpt_body: dict | None = None
    if rpt_file.is_symlink() or not rpt_file.is_file():
        issues.append(f"{job_dir.name}: missing or symlink analysis_report.json")
    else:
        try:
            rpt_body = json.loads(rpt_file.read_text(encoding="utf-8"))
        except Exception:
            issues.append(f"{job_dir.name}: unparseable analysis_report.json")
            rpt_body = None
        else:
            if rpt_body.get("job_id") != job_id:
                issues.append(f"{job_dir.name}: report job_id mismatch")
            for field in ("auto_decision", "final_decision"):
                val = rpt_body.get(field)
                if val and val not in ("pass", "review", "reject"):
                    issues.append(f"{job_dir.name}: invalid {field} {val}")

    evidence = job_dir / "evidence"
    evidence_frames: list = rpt_body.get("evidence_frames", []) if rpt_body is not None else []
    if not evidence.is_dir():
        issues.append(f"{job_dir.name}: missing evidence dir")
    else:
        for name in evidence_frames:
            if not _safe_basename(name):
                issues.append(f"{job_dir.name}: unsafe evidence_frame {name!r}")
            else:
                fp = evidence / name
                if not fp.is_file() or fp.stat().st_size == 0:
                    issues.append(f"{job_dir.name}: evidence frame {name} missing/empty on disk")
        if not evidence_frames:
            issues.append(f"{job_dir.name}: evidence_frames list is empty")

    # detections.csv — strict columns
    csv_file = result / "detections.csv"
    if csv_file.is_symlink() or not csv_file.is_file():
        issues.append(f"{job_dir.name}: missing or symlink detections.csv")
    else:
        try:
            import csv as _csv
            with csv_file.open(encoding="utf-8") as fh:
                reader = _csv.DictReader(fh)
                cols = reader.fieldnames or []
                missing_cols = set(CSV_REQUIRED_COLUMNS) - set(cols)
                if missing_cols:
                    issues.append(f"{job_dir.name}: detections.csv missing columns {missing_cols}")
                list(reader)  # consume to validate readability
        except Exception as exc:
            issues.append(f"{job_dir.name}: unreadable detections.csv: {type(exc).__name__}")

    # audit_package.zip — CRC + required members
    zip_file = result / "audit_package.zip"
    if zip_file.is_symlink() or not zip_file.is_file():
        issues.append(f"{job_dir.name}: missing or symlink audit_package.zip")
    else:
        try:
            with zipfile.ZipFile(str(zip_file)) as zf:
                if zf.testzip() is not None:
                    issues.append(f"{job_dir.name}: audit_package.zip CRC error")
                    return issues
                members = zf.namelist()
                # Required members
                required_in_zip = {"analysis_report.json", "detections.csv", "job.json"}
                missing_zip = required_in_zip - set(members)
                if missing_zip:
                    issues.append(f"{job_dir.name}: audit_package.zip missing {missing_zip}")
                # Evidence frames declared in report must be in ZIP (if report loaded)
                if rpt_body:
                    for ef in rpt_body.get("evidence_frames", []):
                        member = f"evidence/{ef}"
                        if member not in members:
                            issues.append(
                                f"{job_dir.name}: evidence frame {member} "
                                "missing from ZIP"
                            )
                # No absolute paths or .. in members
                for name_ in members:
                    if ".." in name_ or name_.startswith("/"):
                        issues.append(f"{job_dir.name}: unsafe ZIP member {name_!r}")
                        break
        except Exception as exc:
            issues.append(f"{job_dir.name}: unopenable audit_package.zip: {type(exc).__name__}")

    return issues


# ---------------------------------------------------------------------------
# _all_gates_pass
# ---------------------------------------------------------------------------
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

    gates["pytest_pass"] = _run_pytest_gate()

    gates["model_present"] = (PROJECT_ROOT / "models" / "aegis_game_best.pt").is_file()

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

    bug_doc = PROJECT_ROOT / "docs" / "BUG_RECORD.md"
    bug_text = bug_doc.read_text(encoding="utf-8") if bug_doc.is_file() else ""
    gates["closed_bugs_ge_2"] = _count_closed_bugs(bug_text) >= 2

    gates["screenshots_ok"] = len(_missing_screenshots(PROJECT_ROOT)) == 0

    hygiene = _load_hygiene()
    gates["hygiene_clean"] = len(hygiene) == 0

    return gates


def _translate(gates: dict[str, bool | str]) -> tuple[bool, list[str]]:
    passed = all(v is True for v in gates.values())
    lines: list[str] = []
    for name, ok in sorted(gates.items()):
        mark = "[PASS]" if ok is True else "[FAIL]"
        label = repr(ok) if not isinstance(ok, bool) else str(ok)
        lines.append(f"  {mark} {name}")
        if not isinstance(ok, bool) or ok is False:
            lines[-1] += f"  ({label})"
    return passed, lines


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
MANIFEST_PATTERNS = [
    "app.py", "requirements.txt", "environment.yml",
    "Dockerfile", "compose.yaml", ".dockerignore", ".editorconfig", ".gitignore",
    "pytest.ini",
    "README.md", "AGENTS.md",
    "aegis_review/**/*.py",
    "static/**/*", "templates/**/*",
    "prompts/**/*.md",
    "scripts/*.py",
    "tests/**/*.py",
    "tests/fixtures/media/**/*",
    "models/aegis_game_best.pt",
    "docs/**/*.md",
    "screenshots/*.png", "screenshots/*.jpg", "screenshots/*.jpeg",
    "dataset/**/*",
    "training_evidence/**/*",
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
# Validation outputs selection
# ---------------------------------------------------------------------------
def _select_validation_jobs() -> tuple[str | None, str | None]:
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
        for item in src.rglob("*"):
            if item.is_symlink():
                raise SystemExit(f"refusing to package symlink in outputs: {item}")
            rel = item.relative_to(src)
            if item.is_dir():
                (dst / rel).mkdir(parents=True, exist_ok=True)
            else:
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst / rel)


# ---------------------------------------------------------------------------
# Build archive
# ---------------------------------------------------------------------------
def _build_archive(package_dir: Path) -> tuple[Path, str]:
    if RELEASE_STAGING.exists():
        shutil.rmtree(RELEASE_STAGING)
    RELEASE_STAGING.mkdir(parents=True)

    package_name = f"{_extract_surname()}_A_day08"
    submission_root = RELEASE_STAGING / package_name

    for src in _collect_files():
        dst = submission_root / src.relative_to(PROJECT_ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    _copy_validation_outputs(submission_root)

    demo_script = submission_root / "docs" / "DEMO_SCRIPT.md"
    demo_entry = submission_root / "demo" / "demo_script.md"
    demo_entry.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(demo_script, demo_entry)

    archive_path = package_dir / f"{package_name}.zip"
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
    if not surname.strip():
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
    _validate_zip_bytes(archive.read_bytes())
    print("  ZIP CRC: OK")
    print(f"\nDone: {package_name}.zip")


if __name__ == "__main__":
    main()
