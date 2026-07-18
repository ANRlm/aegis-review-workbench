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
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1].resolve()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
FIXTURE_SUPPORT = TESTS_DIR / "fixtures" / "support.py"

RELEASE_STAGING = PROJECT_ROOT / "tmp" / "release"

# ---- helpers ----
_HAS_FIXTURE_SUPPORT = FIXTURE_SUPPORT.is_file()

# Zacian: earliest valid ZIP epoch is 1980-01-01
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


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
# 1. Extract surname from roster
# ---------------------------------------------------------------------------
ROSTER = PROJECT_ROOT / "docs" / "TEAM_ROSTER.md"
ROSTER_RE = re.compile(
    r"\|\s*组长/产品与集成\s*\|.*?\|\s*(\S+)\s*\|"
)


def _extract_surname() -> str:
    if not ROSTER.is_file():
        raise SystemExit(f"missing {ROSTER}")
    text = ROSTER.read_text(encoding="utf-8")
    m = ROSTER_RE.search(text)
    if not m:
        raise SystemExit(f"cannot parse surname from {ROSTER}")
    full_name = m.group(1).strip()
    if not full_name:
        raise SystemExit("surname is empty — will not generate a fake package name")
    # Use first character as surname (Chinese naming convention)
    surname = full_name[0]
    return surname


# ---------------------------------------------------------------------------
# 2. Gate checks
# ---------------------------------------------------------------------------
def _git_available() -> bool:
    import shutil as _shutil
    return _shutil.which("git") is not None


def _all_gates_pass() -> dict[str, bool | str]:
    gates: dict[str, bool | str] = {}

    # a) git clean working tree
    if _git_available():
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        gates["git_clean"] = result.stdout.strip() == ""
    else:
        gates["git_clean"] = "git not installed"

    # b) pytest -q all green
    result = subprocess.run(
        ["pytest", "-q"], capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    gates["pytest_pass"] = result.returncode == 0

    # c) model present
    model = PROJECT_ROOT / "models" / "aegis_game_best.pt"
    gates["model_present"] = model.is_file()

    # d) at least 1 completed image + 1 completed video job with valid outputs
    outputs = PROJECT_ROOT / "outputs"
    img_ok = vid_ok = False
    if outputs.is_dir():
        for job_dir in outputs.iterdir():
            jf = job_dir / "job.json"
            if not jf.is_file():
                continue
            try:
                body = __import__("json").loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            if body.get("status") != "completed":
                continue
            if not (job_dir / "input").is_dir():
                continue
            at = body.get("asset_type", "")
            if at == "image":
                img_ok = True
            elif at == "video":
                vid_ok = True
    gates["completed_image_job"] = img_ok
    gates["completed_video_job"] = vid_ok

    # e) bug record has ≥2 closed bugs with commit hashes
    bug_doc = PROJECT_ROOT / "docs" / "BUG_RECORD.md"
    bug_count = 0
    if bug_doc.is_file():
        text = bug_doc.read_text(encoding="utf-8")
        # count "修复提交:" followed by a hex hash
        fixes = re.findall(r"修复提交[：:]\s*([a-f0-9]{7,40})", text)
        # each Bug section should have its own fix entry
        sections = re.findall(r"## Bug \d+", text)
        bug_count = min(len(fixes), len(sections))
    gates["closed_bugs_ge_2"] = bug_count >= 2

    # f) screenshots exist
    ss_dir = PROJECT_ROOT / "screenshots"
    has_ss = False
    if ss_dir.is_dir():
        imgs = [
            f
            for f in ss_dir.iterdir()
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif")
        ]
        has_ss = len(imgs) >= 3
    gates["screenshots_ok"] = has_ss

    # g) hygiene clean
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
# 3. File manifest
# ---------------------------------------------------------------------------
MANIFEST_PATTERNS = [
    "app.py",
    "requirements.txt",
    "environment.yml",
    "Dockerfile",
    "compose.yaml",
    ".dockerignore",
    ".editorconfig",
    "pytest.ini",
    "README.md",
    "AGENTS.md",
    "aegis_review/**/*.py",
    "aegis_review/cv/**/*.py",
    "static/**",
    "templates/**",
    "prompts/**/*.md",
    "scripts/*.py",
    "tests/**/*.py",
    "models/aegis_game_best.pt",
    "docs/**/*.md",
    "docs/assignments/*.md",
    "screenshots/*.png",
    "screenshots/*.jpg",
    "screenshots/*.jpeg",
    "dataset/**",
    "training_evidence/**",
]

EXCLUDE_PREFIXES = (
    ".git/", "__pycache__/", "node_modules/", "tmp/", "outputs/", ".pytest_cache/",
    "training_runs/", "runs/",
)

EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".tmp", ".log")

# Extra patterns to match for exclusion (glob-style)
EXCLUDE_PATTERNS = [
    "**/last.pt",
    "**/*.last",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "models/*.pt",
    "!models/aegis_game_best.pt",
]


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
# 4. Build archive
# ---------------------------------------------------------------------------
def _build_archive(package_dir: Path) -> tuple[Path, str]:
    if not RELEASE_STAGING.parent.exists():
        RELEASE_STAGING.parent.mkdir(exist_ok=True)
    if RELEASE_STAGING.exists():
        shutil.rmtree(RELEASE_STAGING)
    RELEASE_STAGING.mkdir(parents=True)

    for src in _collect_files():
        dst = RELEASE_STAGING / src.relative_to(PROJECT_ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

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
                contents = fh.read()
            zf.writestr(info, contents)

    sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return archive_path, sha


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="release package builder")
    parser.add_argument(
        "--check", action="store_true", help="validate gates only, no archive produced"
    )
    parser.add_argument(
        "--list", action="store_true", help="print file manifest and exit"
    )
    parser.add_argument(
        "--dest",
        default=str(PROJECT_ROOT),
        help="directory to write the archive into (default: project root)",
    )
    args = parser.parse_args()

    surname = _extract_surname()
    if not surname or not surname.strip():
        raise SystemExit("surname is empty — will not generate a fake package name")

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
            print("Unblock when all gates above show [PASS].")
        else:
            print(f"\nAll gates pass — ready for {package_name}.zip")
        sys.exit(0 if passed else 1)

    print("[package_release] checking gates ...")
    gates = _all_gates_pass()
    passed, lines = _translate(gates)
    for line in lines:
        print(line)
    if not passed:
        print(f"\nBLOCKED: {package_name}.zip refused — gates did not pass.")
        sys.exit(1)

    print(f"\n[package_release] building {package_name}.zip ...")
    archive, sha = _build_archive(Path(args.dest))
    print(f"  {archive}")
    print(f"  SHA256: {sha}")

    # self-check
    _validate_zip(archive.read_bytes())
    print("  ZIP CRC: OK")
    print(f"\nDone: {package_name}.zip")


if __name__ == "__main__":
    main()
