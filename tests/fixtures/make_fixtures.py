"""Generate deterministic test fixtures for the Aegis Review QA suite.

All fixtures are produced with fixed seeds so that the same bytes
are written on every run.  Run inside the container to get ffmpeg:

    docker compose run --rm -v .:/workspace app \
        python tests/fixtures/make_fixtures.py

Or locally (images only – video is skipped without ffmpeg):

    python tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


MEDIA = Path(__file__).resolve().parent / "media"

SEED = 42


def _rng(seed: int = SEED) -> callable:
    """Simple deterministic LCG."""
    state = seed

    def randint(lo: int, hi: int) -> int:
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return lo + (state % (hi - lo + 1))

    return randint


def make_image(name: str, width: int, height: int, draw_fn: callable) -> Path:
    if not HAS_PIL:
        raise SystemExit("Pillow is required to generate image fixtures")
    img = Image.new("RGB", (width, height), (30, 30, 40))
    if draw_fn is not None:
        draw_fn(ImageDraw.Draw(img), width, height)
    path = MEDIA / name
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG" if name.endswith(".png") else "JPEG", quality=90)
    return path


def make_corrupt_jpeg(path: Path) -> None:
    """Write a JPEG header followed by zero bytes (truncated file)."""
    header = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00"
        b"\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + b"\x00" * 512)


def make_corrupt_video(path: Path) -> None:
    """Write random bytes with no valid container magic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rand = _rng(123)
    path.write_bytes(bytes(rand(0, 255) for _ in range(1024)))


def make_empty(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def make_text_disguised_as_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this is plain text, not an image\n", encoding="utf-8")


def make_sample_video(path: Path, duration: float = 5.0) -> None:
    """Generate 5 s H.264 test-source video via ffmpeg.

    If ffmpeg is not available the fixture is skipped with a
    descriptive message.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print("[make_fixtures] ffmpeg not found — skipping video fixture")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size=640x360:rate=24,"
        f"drawtext=text='Aegis QA':fontsize=36:fontcolor=white:"
        f"x=(w-text_w)/2:y=(h-text_h)/2",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-an",
        "-t",
        str(duration),
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"[make_fixtures] ffmpeg failed: {result.stderr}", file=sys.stderr)
        raise SystemExit(1)


def _hash_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    print("--- Generating QA fixtures ---")

    MEDIA.mkdir(parents=True, exist_ok=True)

    rand = _rng()

    # a  clean image (no "risk" shapes — passes automated review)
    make_image("clean_scene.jpg", 640, 480, None)

    # b  medium-risk scene (draws a few small red rectangles)
    def _draw_risk(draw: ImageDraw.Draw, w: int, h: int) -> None:
        for _ in range(3):
            x = rand(50, w - 25)
            y = rand(50, h - 25)
            draw.rectangle([x, y, x + rand(8, 16), y + rand(8, 16)], fill=(220, 50, 50))

    make_image("risk_scene.jpg", 640, 480, _draw_risk)

    # c  high-risk scene (many large red rectangles)
    def _draw_reject(draw: ImageDraw.Draw, w: int, h: int) -> None:
        for _ in range(12):
            x = rand(10, w - 40)
            y = rand(10, h - 40)
            draw.rectangle([x, y, x + rand(20, 45), y + rand(20, 45)], fill=(240, 30, 30))

    make_image("reject_scene.jpg", 640, 480, _draw_reject)

    # d  video (5 s H.264)
    make_sample_video(MEDIA / "sample_5s.mp4", duration=5.0)

    # e  corrupt / empty / extension spoof
    make_corrupt_jpeg(MEDIA / "corrupt.jpg")
    make_corrupt_video(MEDIA / "corrupt.mp4")
    make_empty(MEDIA / "empty.bin")
    make_text_disguised_as_image(MEDIA / "not_media.jpg")

    # --- manifest ---
    manifest: dict[str, str | None] = {}
    for name in sorted(
        p.name for p in MEDIA.iterdir() if p.is_file() and p.suffix != ".json"
    ):
        manifest[name] = _hash_file(MEDIA / name)

    (MEDIA / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("--- Fixtures complete ---")
    for name, sha in manifest.items():
        print(f"  {name}  sha256={sha[:16] if sha else 'SKIPPED'}")


if __name__ == "__main__":
    main()
