"""Pure input validation functions for the API layer.

These functions validate HTTP input without any filesystem side effects.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from .domain import AuditSettings, MediaType, SUPPORTED_MEDIA_EXTENSIONS


class ValidationError(ValueError):
    """Raised when API input validation fails."""


def validate_project_name(name: object) -> str:
    """Strip and validate project_name (1-80 chars after strip)."""
    if not isinstance(name, str):
        raise ValidationError("project_name \u5fc5\u987b\u662f\u5b57\u7b26\u4e32\u3002")
    stripped = name.strip()
    if not stripped:
        raise ValidationError("\u9879\u76ee\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a\u3002")
    if len(stripped) > 80:
        raise ValidationError("\u9879\u76ee\u540d\u79f0\u4e0d\u80fd\u8d85\u8fc7 80 \u4e2a\u5b57\u7b26\u3002")
    return stripped


def detect_media_type(extension: str) -> MediaType:
    """Detect media type from a lowercased extension string."""
    if not isinstance(extension, str):
        raise ValidationError("\u4e0d\u652f\u6301\u7684\u6587\u4ef6\u6269\u5c55\u540d\u3002")
    ext = extension.lower().strip()
    if not ext:
        raise ValidationError("\u4e0d\u652f\u6301\u7684\u6587\u4ef6\u6269\u5c55\u540d\u3002")
    for media_type, extensions in SUPPORTED_MEDIA_EXTENSIONS.items():
        if ext in extensions:
            return media_type
    raise ValidationError(f"\u4e0d\u652f\u6301\u7684\u6587\u4ef6\u6269\u5c55\u540d: .{ext}")


def parse_settings(raw: object) -> AuditSettings:
    """Parse optional settings JSON string into an AuditSettings.

    Returns default AuditSettings when raw is None or empty.
    """
    if raw is None:
        return AuditSettings()
    if not isinstance(raw, str):
        raise ValidationError("settings \u5fc5\u987b\u662f JSON \u5b57\u7b26\u4e32\u3002")
    raw_stripped = raw.strip()
    if not raw_stripped:
        return AuditSettings()
    try:
        data = json.loads(raw_stripped)
    except json.JSONDecodeError as exc:
        raise ValidationError("settings \u4e0d\u662f\u5408\u6cd5\u7684 JSON\u3002") from exc
    if not isinstance(data, dict):
        raise ValidationError("settings \u5fc5\u987b\u662f JSON \u5bf9\u8c61\u3002")
    try:
        return AuditSettings.from_dict(data)
    except ValueError as exc:
        raise ValidationError(f"settings \u53c2\u6570\u9519\u8bef: {exc}") from exc


_COPY_CHUNK = 1024 * 1024  # 1 MB


def _stream_to_tempfile(stream: BinaryIO, suffix: str, max_bytes: int) -> str | None:
    """Copy stream to a temp file in 1 MB chunks, returning path or None on overflow."""
    total = 0
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        while True:
            chunk = stream.read(_COPY_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                return None
            tmp.write(chunk)
        tmp.flush()
        return tmp.name
    except BaseException:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        raise


def decode_image_stream(stream: BinaryIO) -> bool:
    """Verify that a byte stream can be decoded as a valid image."""
    try:
        stream.seek(0)
        from PIL import Image
        img = Image.open(stream)
        img.load()
        return True
    except Exception:
        return False
    finally:
        try:
            stream.seek(0)
        except OSError:
            pass


def decode_video_stream(stream: BinaryIO, max_bytes: int = 200 * 1024 * 1024) -> bool:
    """Verify that a byte stream can be opened as a video with at least one frame.

    Reads in 1 MB chunks to avoid loading the entire file into memory.
    Stream caller must reset position independently (this function does NOT
    restore the original offset, to allow outer validation to re-read).
    """
    import cv2
    try:
        stream.seek(0)
        ext = ".mp4"
        temp_path = _stream_to_tempfile(stream, ext, max_bytes)
        if temp_path is None:
            return False  # exceeds max_bytes
        cap = cv2.VideoCapture(temp_path)
        try:
            ret, _frame = cap.read()
            return bool(ret)
        finally:
            cap.release()
            Path(temp_path).unlink(missing_ok=True)
            stream.seek(0)
    except Exception:
        try:
            stream.seek(0)
        except OSError:
            pass
        return False
