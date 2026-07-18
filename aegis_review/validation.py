"""Pure input validation functions for the API layer.

These functions validate HTTP input without any filesystem side effects.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

import cv2
from PIL import Image

from .domain import AuditSettings, MediaType, SUPPORTED_MEDIA_EXTENSIONS


class ValidationError(ValueError):
    """Raised when API input validation fails."""


def validate_project_name(name: object) -> str:
    """Strip and validate project_name (1-80 chars after strip)."""
    if not isinstance(name, str):
        raise ValidationError("project_name 必须是字符串。")
    stripped = name.strip()
    if not stripped:
        raise ValidationError("项目名称不能为空。")
    if len(stripped) > 80:
        raise ValidationError("项目名称不能超过 80 个字符。")
    return stripped


def detect_media_type(extension: str) -> MediaType:
    """Detect media type from a lowercased extension string."""
    if not isinstance(extension, str):
        raise ValidationError("不支持的文件扩展名。")
    ext = extension.lower().strip()
    if not ext:
        raise ValidationError("不支持的文件扩展名。")
    for media_type, extensions in SUPPORTED_MEDIA_EXTENSIONS.items():
        if ext in extensions:
            return media_type
    raise ValidationError(f"不支持的文件扩展名: .{ext}")


def parse_settings(raw: object) -> AuditSettings:
    """Parse optional settings JSON string into an AuditSettings.

    Returns default AuditSettings when raw is None or empty.
    """
    if raw is None:
        return AuditSettings()
    if not isinstance(raw, str):
        raise ValidationError("settings 必须是 JSON 字符串。")
    raw_stripped = raw.strip()
    if not raw_stripped:
        return AuditSettings()
    try:
        data = json.loads(raw_stripped)
    except json.JSONDecodeError as exc:
        raise ValidationError("settings 不是合法的 JSON。") from exc
    if not isinstance(data, dict):
        raise ValidationError("settings 必须是 JSON 对象。")
    try:
        return AuditSettings.from_dict(data)
    except ValueError as exc:
        raise ValidationError(f"settings 参数错误: {exc}") from exc


def decode_image_stream(stream: BinaryIO) -> bool:
    """Verify that a byte stream can be decoded as a valid image."""
    try:
        stream.seek(0)
        img = Image.open(stream)
        img.load()
        return True
    except Exception:
        return False


def decode_video_stream(stream: BinaryIO) -> bool:
    """Verify that a byte stream can be opened as a video with at least one frame."""
    try:
        stream.seek(0)
        data = stream.read()
        if not data:
            return False
        temp_path = None
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(data)
            temp_path = tmp.name
        cap = cv2.VideoCapture(temp_path)
        try:
            ret, _frame = cap.read()
            return bool(ret)
        finally:
            cap.release()
            if temp_path is not None:
                Path(temp_path).unlink(missing_ok=True)
    except Exception:
        return False
