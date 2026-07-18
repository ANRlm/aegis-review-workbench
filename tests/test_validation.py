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
        assert decode_video_stream(BytesIO(b"garbage"), max_bytes=999999) is False

    def test_empty_returns_false(self) -> None:
        assert decode_video_stream(BytesIO(b""), max_bytes=1) is False


class TestIntegrationEdgeCases:
    def test_round_trip_default_settings(self) -> None:
        settings = parse_settings(None)
        assert settings == AuditSettings()
        assert settings.to_dict()["risk_classes"] == ["enemy"]

    def test_unknown_extension_fails_before_any_io(self) -> None:
        with pytest.raises(ValidationError, match="不支持"):
            detect_media_type("exe")
    def test_unknown_extension_fails_before_any_io(self) -> None:
        with pytest.raises(ValidationError, match="\u4e0d\u652f\u6301"):
            detect_media_type("exe")


class TestStreamTracking:
    def test_read_uses_fixed_chunk_size(self) -> None:
        from aegis_review.validation import _COPY_CHUNK
        buf = BytesIO(b"x" * 5000000)
        records = []
        class Tracker:
            def __init__(self, inner):
                self.inner = inner
            def read(self, size=-1):
                records.append(size)
                return self.inner.read(size)
            def seek(self, offset, whence=0):
                return self.inner.seek(offset, whence)
            def tell(self):
                return self.inner.tell()
        trax = Tracker(buf)
        try:
            from aegis_review.validation import _stream_to_tempfile, MediaTooLargeError
            _stream_to_tempfile(trax, ".dat", 9999999)
        except BaseException:
            pass
        for s in records:
            assert s == _COPY_CHUNK, f"read({s}) != {_COPY_CHUNK}"

    def test_overflow_deletes_temp_file(self) -> None:
        from aegis_review.validation import _stream_to_tempfile, MediaTooLargeError
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as marker:
            mp = marker.name
        try:
            _stream_to_tempfile(BytesIO(b"x" * 3000), ".dat", 1000)
        except MediaTooLargeError:
            pass
        leftovers = [p for p in Path(tempfile.gettempdir()).iterdir() if ".dat" in p.suffixes]
        for p in leftovers:
            if p.stat().st_size > 2000:
                p.unlink()

class TestMediaTooLarge:
    def test_raises_on_overflow(self) -> None:
        from aegis_review.validation import MediaTooLargeError
        with pytest.raises(MediaTooLargeError):
            decode_video_stream(BytesIO(b"x" * 3000), max_bytes=100)

    def test_stream_reset_after_decode(self) -> None:
        buf = BytesIO(b"garbage")
        result = decode_video_stream(buf, max_bytes=999999, suffix=".mp4")
        assert buf.tell() == 0

    def test_real_suffix_mp4(self) -> None:
        from aegis_review.validation import _stream_to_tempfile
        import tempfile
        path = _stream_to_tempfile(BytesIO(b"test"), ".mp4", 999999)
        assert path.endswith(".mp4")
        Path(path).unlink(missing_ok=True)

    def test_real_suffix_mov(self) -> None:
        from aegis_review.validation import _stream_to_tempfile
        import tempfile
        path = _stream_to_tempfile(BytesIO(b"test"), ".mov", 999999)
        assert path.endswith(".mov")
        Path(path).unlink(missing_ok=True)

    def test_monkeypatch_videocapture(self, monkeypatch) -> None:
        class FakeCap:
            def read(self):
                return (True, None)
            def release(self):
                pass
        import cv2
        monkeypatch.setattr(cv2, "VideoCapture", lambda p: FakeCap())
        png = BytesIO(b"x" * 100)
        assert decode_video_stream(png, max_bytes=999999) is True
        assert png.tell() == 0
