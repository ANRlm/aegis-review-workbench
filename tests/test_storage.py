from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
from pathlib import Path

import pytest

from aegis_review.domain import (
    AssetInput,
    AuditSettings,
    JobRecord,
    JobStatus,
    MediaType,
)
from aegis_review.storage import (
    AssetTooLargeError,
    CorruptJobError,
    InvalidJobIdError,
    JobStorage,
    UnsafePathError,
    atomic_write_json,
    read_json,
)


JOB_ID = "20260718_101530_a1b2c3d4"


def make_record(
    job_id: str = JOB_ID,
    *,
    created_at: str = "2026-07-18T10:15:30+08:00",
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        project_name="星港遗迹内容审核",
        asset_name="opening_scene.mp4",
        asset_type=MediaType.VIDEO,
        asset_file="original.mp4",
        status=JobStatus.CREATED,
        created_at=created_at,
        started_at=None,
        completed_at=None,
        settings=AuditSettings().to_dict(),
        result_file=None,
        error=None,
    )


def make_asset(payload: bytes = b"video-bytes") -> AssetInput:
    return AssetInput(
        original_name="opening_scene.mp4",
        extension="mp4",
        media_type=MediaType.VIDEO,
        stream=BytesIO(payload),
    )


def test_atomic_write_failure_preserves_previous_json_and_cleans_temp_files(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "job.json"
    original = {"status": "created"}
    atomic_write_json(destination, original)

    with pytest.raises(TypeError):
        atomic_write_json(destination, {"bad": object()})

    assert read_json(destination) == original
    assert list(tmp_path.glob(".job.json.*.tmp")) == []


def test_atomic_replace_failure_preserves_previous_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "job.json"
    original = {"status": "created"}
    atomic_write_json(destination, original)

    def fail_replace(_source: Path | str, _target: Path | str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("aegis_review.storage.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_json(destination, {"status": "queued"})

    assert read_json(destination) == original
    assert list(tmp_path.glob(".job.json.*.tmp")) == []


def test_new_job_id_skips_an_existing_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    now = datetime.fromisoformat("2026-07-18T10:15:30+08:00")
    existing = storage.outputs_dir / "20260718_101530_aaaaaaaa"
    existing.mkdir()
    tokens = iter(["aaaaaaaa", "bbbbbbbb"])
    monkeypatch.setattr(
        "aegis_review.storage.secrets.token_hex",
        lambda _length: next(tokens),
    )

    job_id = storage.new_job_id(now)

    assert job_id == "20260718_101530_bbbbbbbb"


def test_create_job_publishes_complete_layout_and_keeps_stream_open(
    tmp_path: Path,
) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    record = make_record()
    asset = make_asset()

    created = storage.create(record, asset)

    paths = storage.paths(JOB_ID)
    assert created.to_dict() == record.to_dict()
    assert paths.input_dir.joinpath("original.mp4").read_bytes() == b"video-bytes"
    assert paths.evidence_dir.is_dir()
    assert paths.result_dir.is_dir()
    assert read_json(paths.job_file) == record.to_dict()
    assert asset.stream.closed is False
    assert list(storage.outputs_dir.glob(".staging-*")) == []


def test_create_job_rejects_asset_larger_than_limit_and_cleans_staging(
    tmp_path: Path,
) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=4)

    with pytest.raises(AssetTooLargeError):
        storage.create(make_record(), make_asset(b"12345"))

    assert not storage.paths(JOB_ID, require_exists=False).root.exists()
    assert list(storage.outputs_dir.glob(".staging-*")) == []


def test_list_records_is_newest_first_and_ignores_non_job_directories(
    tmp_path: Path,
) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    older = make_record(
        "20260718_101530_a1b2c3d4",
        created_at="2026-07-18T10:15:30+08:00",
    )
    newer = make_record(
        "20260718_111530_b1c2d3e4",
        created_at="2026-07-18T11:15:30+08:00",
    )
    storage.create(older, make_asset())
    storage.create(newer, make_asset())
    (storage.outputs_dir / ".staging-leftover").mkdir()
    (storage.outputs_dir / "not-a-job").mkdir()

    records = storage.list_records()

    assert [record.job_id for record in records] == [newer.job_id, older.job_id]


def test_list_records_rejects_corrupt_job_json(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    storage.create(make_record(), make_asset())
    storage.paths(JOB_ID).job_file.write_text("{not json", encoding="utf-8")

    with pytest.raises(CorruptJobError, match=JOB_ID):
        storage.list_records()


@pytest.mark.parametrize(
    "job_id",
    ["../escape", "20260718_101530_A1B2C3D4", "bad", "", "/tmp/job"],
)
def test_paths_reject_invalid_job_ids(tmp_path: Path, job_id: str) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)

    with pytest.raises(InvalidJobIdError):
        storage.paths(job_id, require_exists=False)


def test_paths_reject_a_symlink_job_directory(
    tmp_path: Path,
) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    outside = tmp_path / "outside"
    outside.mkdir()
    (storage.outputs_dir / JOB_ID).symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafePathError):
        storage.paths(JOB_ID)


def test_delete_does_not_follow_a_symlink_job_directory(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    (storage.outputs_dir / JOB_ID).symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafePathError):
        storage.delete(JOB_ID)

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_clear_results_preserves_input_and_job_record(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    storage.create(make_record(), make_asset())
    paths = storage.paths(JOB_ID)
    (paths.evidence_dir / "old.jpg").write_bytes(b"old")
    (paths.result_dir / "old.json").write_text(
        json.dumps({"old": True}),
        encoding="utf-8",
    )

    storage.clear_results(JOB_ID)

    assert paths.input_dir.joinpath("original.mp4").read_bytes() == b"video-bytes"
    assert paths.job_file.is_file()
    assert list(paths.evidence_dir.iterdir()) == []
    assert list(paths.result_dir.iterdir()) == []
