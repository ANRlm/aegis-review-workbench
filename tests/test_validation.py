"""Tests for input validation functions (B1 boundary)."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from aegis_review.domain import AuditSettings, MediaType
from aegis_review.validation import (
    ValidationError,
    decode_image_stream,
    decode_video_stream,
    detect_media_type,
    parse_settings,
    validate_project_name,
)


_FULL_SETTINGS = {
    "risk_classes": ["enemy"],
    "reject_confidence": 0.60,
    "review_confidence": 0.35,
    "inference_confidence": 0.25,
    "min_evidence_frames": 1,
    "sample_interval_seconds": 1.0,
    "max_sample_frames": 120,
}


class TestValidateProjectName:
    def test_strips_spaces(self) -> None:
        assert validate_project_name("  项目审核  ") == "项目审核"

    def test_rejects_empty_after_strip(self) -> None:
        with pytest.raises(ValidationError, match="项目名称"):
            validate_project_name("   ")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValidationError, match="项目名称"):
            validate_project_name("a" * 81)

    def test_accepts_boundary_lengths(self) -> None:
        assert len(validate_project_name("a")) == 1
        name_80 = "a" * 80
        assert len(validate_project_name(name_80)) == 80


class TestDetectMediaType:
    def test_image_extensions(self) -> None:
        assert detect_media_type("jpg") is MediaType.IMAGE
        assert detect_media_type("jpeg") is MediaType.IMAGE
        assert detect_media_type("png") is MediaType.IMAGE

    def test_video_extensions(self) -> None:
        assert detect_media_type("mp4") is MediaType.VIDEO
        assert detect_media_type("mov") is MediaType.VIDEO

    def test_unsupported_extension(self) -> None:
        with pytest.raises(ValidationError, match="不支持"):
            detect_media_type("gif")
        with pytest.raises(ValidationError, match="不支持"):
            detect_media_type("txt")
        with pytest.raises(ValidationError, match="不支持"):
            detect_media_type("")


class TestParseSettings:
    def test_none_uses_defaults(self) -> None:
        result = parse_settings(None)
        assert isinstance(result, AuditSettings)
        assert result == AuditSettings()

    def test_valid_json(self) -> None:
        overrides = dict(_FULL_SETTINGS, reject_confidence=0.70)
        result = parse_settings(json.dumps(overrides))
        assert result.reject_confidence == 0.70
        assert result.risk_classes == ("enemy",)

    def test_invalid_json(self) -> None:
        with pytest.raises(ValidationError, match="JSON"):
            parse_settings("{bad json}")

    def test_not_a_dict(self) -> None:
        with pytest.raises(ValidationError, match="JSON 对象"):
            parse_settings('"hello"')

    def test_wrong_fields(self) -> None:
        with pytest.raises(ValidationError, match="settings 参数错误"):
            parse_settings(json.dumps({"unknown_field": 1}))

    def test_invalid_confidence_values(self) -> None:
        bad = dict(_FULL_SETTINGS, inference_confidence=0.7, review_confidence=0.3)
        with pytest.raises(ValidationError):
            parse_settings(json.dumps(bad))


class TestDecodeImageStream:
    def test_valid_png(self) -> None:
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="PNG")
        assert decode_image_stream(buf) is True

    def test_valid_jpeg(self) -> None:
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="JPEG")
        assert decode_image_stream(buf) is True

    def test_corrupted_stream(self) -> None:
        buf = BytesIO(b"not an image at all")
        assert decode_image_stream(buf) is False

    def test_empty_stream(self) -> None:
        buf = BytesIO(b"")
        assert decode_image_stream(buf) is False


class TestDecodeVideoStream:
    def test_invalid_stream_returns_false(self) -> None:
        assert decode_video_stream(BytesIO(b"garbage")) is False

    def test_empty_returns_false(self) -> None:
        assert decode_video_stream(BytesIO(b"")) is False


class TestIntegrationEdgeCases:
    def test_round_trip_default_settings(self) -> None:
        settings = parse_settings(None)
        assert settings == AuditSettings()
        assert settings.to_dict()["risk_classes"] == ["enemy"]

    def test_unknown_extension_fails_before_any_io(self) -> None:
        with pytest.raises(ValidationError, match="不支持"):
            detect_media_type("exe")
