from __future__ import annotations

from io import BytesIO

import pytest

from aegis_review.domain import (
    AnalysisReport,
    AssetInput,
    AuditDecision,
    AuditSettings,
    JobRecord,
    JobStatus,
    MediaType,
)


def test_asset_input_keeps_a_seekable_stream_without_taking_ownership() -> None:
    stream = BytesIO(b"image-bytes")

    asset = AssetInput(
        original_name="poster.png",
        extension="png",
        media_type=MediaType.IMAGE,
        stream=stream,
    )

    assert asset.original_name == "poster.png"
    assert asset.extension == "png"
    assert asset.media_type is MediaType.IMAGE
    assert asset.stream is stream
    assert stream.closed is False


@pytest.mark.parametrize(
    "extension",
    ["", ".mp4", "MP4", "../mp4", "m/p4", "m\\p4"],
)
def test_asset_input_rejects_non_normalized_extensions(extension: str) -> None:
    with pytest.raises(ValueError, match="extension"):
        AssetInput(
            original_name="clip.mp4",
            extension=extension,
            media_type=MediaType.VIDEO,
            stream=BytesIO(b"video"),
        )


def test_asset_input_requires_a_seekable_binary_stream() -> None:
    with pytest.raises(TypeError, match="stream"):
        AssetInput(
            original_name="clip.mp4",
            extension="mp4",
            media_type=MediaType.VIDEO,
            stream=object(),
        )


def test_job_record_round_trips_the_persisted_schema() -> None:
    payload = {
        "job_id": "20260718_101530_a1b2c3d4",
        "project_name": "星港遗迹内容审核",
        "asset_name": "opening_scene.mp4",
        "asset_type": "video",
        "asset_file": "original.mp4",
        "status": "created",
        "created_at": "2026-07-18T10:15:30+08:00",
        "started_at": None,
        "completed_at": None,
        "settings": AuditSettings().to_dict(),
        "result_file": None,
        "error": None,
    }

    record = JobRecord.from_dict(payload)

    assert record.job_id == "20260718_101530_a1b2c3d4"
    assert record.asset_type is MediaType.VIDEO
    assert record.status is JobStatus.CREATED
    assert record.to_dict() == payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("asset_file", "../original.mp4"),
        ("asset_file", "input/original.mp4"),
        ("asset_file", "/tmp/original.mp4"),
        ("result_file", "../analysis_report.json"),
        ("result_file", "result/analysis_report.json"),
    ],
)
def test_job_record_rejects_non_basename_disk_fields(
    field: str,
    value: str,
) -> None:
    payload = {
        "job_id": "20260718_101530_a1b2c3d4",
        "project_name": "项目",
        "asset_name": "clip.mp4",
        "asset_type": "video",
        "asset_file": "original.mp4",
        "status": "created",
        "created_at": "2026-07-18T10:15:30+08:00",
        "started_at": None,
        "completed_at": None,
        "settings": AuditSettings().to_dict(),
        "result_file": None,
        "error": None,
    }
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        JobRecord.from_dict(payload)


def test_job_record_requires_timezone_aware_timestamps() -> None:
    payload = {
        "job_id": "20260718_101530_a1b2c3d4",
        "project_name": "项目",
        "asset_name": "clip.mp4",
        "asset_type": "video",
        "asset_file": "original.mp4",
        "status": "created",
        "created_at": "2026-07-18T10:15:30",
        "started_at": None,
        "completed_at": None,
        "settings": AuditSettings().to_dict(),
        "result_file": None,
        "error": None,
    }

    with pytest.raises(ValueError, match="created_at"):
        JobRecord.from_dict(payload)


def test_audit_settings_round_trip_from_json_types() -> None:
    settings = AuditSettings.from_dict(AuditSettings().to_dict())

    assert settings == AuditSettings()


def test_analysis_report_round_trips_decisions_and_downloads() -> None:
    payload = {
        "job_id": "20260718_101530_a1b2c3d4",
        "detections": [],
        "evidence_frames": ["frame_000001.jpg"],
        "rules": AuditSettings().to_dict(),
        "auto_decision": "review",
        "final_decision": "reject",
        "reviewer": "审核员",
        "note": "复核后拒绝",
        "downloads": {
            "csv": "detections.csv",
            "zip": "audit_package.zip",
        },
    }

    report = AnalysisReport.from_dict(payload)

    assert report.auto_decision is AuditDecision.REVIEW
    assert report.final_decision is AuditDecision.REJECT
    assert report.to_dict() == payload
