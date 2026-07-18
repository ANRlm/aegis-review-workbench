"""Durable and path-safe local storage for Aegis Review jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
from typing import Any
import uuid

from .domain import (
    AssetInput,
    JOB_ID_PATTERN,
    JobRecord,
    SUPPORTED_MEDIA_EXTENSIONS,
)


COPY_CHUNK_BYTES = 1024 * 1024


class StorageError(RuntimeError):
    """Base class for safe, user-facing storage failures."""


class InvalidJobIdError(StorageError, ValueError):
    """Raised when a job ID does not match the published format."""


class JobNotFoundError(StorageError, FileNotFoundError):
    """Raised when a valid job directory does not exist."""


class JobAlreadyExistsError(StorageError, FileExistsError):
    """Raised when a generated job ID collides with an existing path."""


class UnsafePathError(StorageError):
    """Raised when a path could escape its trusted task directory."""


class CorruptJobError(StorageError):
    """Raised when a visible task record cannot be decoded or validated."""


class AssetTooLargeError(StorageError):
    """Raised when a streamed asset exceeds the configured byte limit."""


@dataclass(frozen=True, slots=True)
class JobPaths:
    root: Path
    input_dir: Path
    evidence_dir: Path
    result_dir: Path
    job_file: Path


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(destination: Path, payload: dict[str, Any]) -> None:
    """Atomically replace a JSON object without following a predictable temp path."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def read_json(source: Path) -> dict[str, Any]:
    with Path(source).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {source}")
    return payload


class JobStorage:
    """Own the on-disk layout and every trusted filesystem boundary."""

    def __init__(self, outputs_dir: Path, max_asset_bytes: int) -> None:
        if max_asset_bytes <= 0:
            raise ValueError("max_asset_bytes must be positive")
        self.outputs_dir = Path(outputs_dir).expanduser().resolve()
        self.max_asset_bytes = max_asset_bytes
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def new_job_id(self, now: datetime | None = None) -> str:
        timestamp = now or datetime.now().astimezone()
        for _attempt in range(100):
            candidate = (
                f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
            )
            if not os.path.lexists(self.outputs_dir / candidate):
                return candidate
        raise StorageError("无法生成唯一任务编号。")

    def paths(
        self,
        job_id: str,
        *,
        require_exists: bool = True,
    ) -> JobPaths:
        if not isinstance(job_id, str) or not JOB_ID_PATTERN.fullmatch(job_id):
            raise InvalidJobIdError("任务编号格式不正确。")
        root = self.outputs_dir / job_id
        if root.is_symlink():
            raise UnsafePathError("任务目录不能是符号链接。")
        resolved = root.resolve(strict=False)
        if resolved.parent != self.outputs_dir:
            raise UnsafePathError("任务目录超出输出目录。")
        if require_exists and not root.is_dir():
            raise JobNotFoundError("任务不存在。")
        return JobPaths(
            root=root,
            input_dir=root / "input",
            evidence_dir=root / "evidence",
            result_dir=root / "result",
            job_file=root / "job.json",
        )

    def create(self, record: JobRecord, asset: AssetInput) -> JobRecord:
        final_paths = self.paths(record.job_id, require_exists=False)
        if os.path.lexists(final_paths.root):
            raise JobAlreadyExistsError("任务编号已存在。")
        if asset.extension not in SUPPORTED_MEDIA_EXTENSIONS[asset.media_type]:
            raise StorageError("不支持的素材扩展名。")
        expected_asset_file = f"original.{asset.extension}"
        if record.asset_file != expected_asset_file:
            raise StorageError("任务素材文件名与上传扩展名不一致。")
        if record.asset_type is not asset.media_type:
            raise StorageError("任务素材类型与上传类型不一致。")

        staging = self.outputs_dir / (
            f".staging-{record.job_id}-{uuid.uuid4().hex}"
        )
        try:
            (staging / "input").mkdir(parents=True)
            (staging / "evidence").mkdir()
            (staging / "result").mkdir()
            self._copy_asset(
                asset,
                staging / "input" / expected_asset_file,
            )
            atomic_write_json(staging / "job.json", record.to_dict())
            staging.rename(final_paths.root)
            _fsync_directory(self.outputs_dir)
        except BaseException:
            if staging.exists() and not staging.is_symlink():
                shutil.rmtree(staging)
            raise
        return self.read(record.job_id)

    def _copy_asset(self, asset: AssetInput, destination: Path) -> None:
        try:
            asset.stream.seek(0)
        except (OSError, ValueError) as error:
            raise StorageError("上传素材流无法重新读取。") from error

        total = 0
        with destination.open("xb") as handle:
            while True:
                chunk = asset.stream.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise StorageError("上传素材流必须返回二进制数据。")
                total += len(chunk)
                if total > self.max_asset_bytes:
                    raise AssetTooLargeError("上传文件不能超过 200MB。")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())

    def read(self, job_id: str) -> JobRecord:
        paths = self.paths(job_id)
        if paths.job_file.is_symlink() or not paths.job_file.is_file():
            raise CorruptJobError(f"任务 {job_id} 的 job.json 无效。")
        try:
            record = JobRecord.from_dict(read_json(paths.job_file))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise CorruptJobError(
                f"任务 {job_id} 的 job.json 无法读取。"
            ) from error
        if record.job_id != job_id:
            raise CorruptJobError(f"任务 {job_id} 的记录编号不一致。")
        return record

    def write(self, record: JobRecord) -> JobRecord:
        paths = self.paths(record.job_id)
        if paths.job_file.is_symlink():
            raise UnsafePathError("job.json 不能是符号链接。")
        atomic_write_json(paths.job_file, record.to_dict())
        return self.read(record.job_id)

    def list_records(self) -> list[JobRecord]:
        records: list[JobRecord] = []
        for entry in self.outputs_dir.iterdir():
            if not JOB_ID_PATTERN.fullmatch(entry.name):
                continue
            if entry.is_symlink():
                raise UnsafePathError("任务目录不能是符号链接。")
            if not entry.is_dir():
                continue
            records.append(self.read(entry.name))
        return sorted(
            records,
            key=lambda record: datetime.fromisoformat(record.created_at),
            reverse=True,
        )

    def clear_results(self, job_id: str) -> None:
        paths = self.paths(job_id)
        self._reset_directory(paths.evidence_dir, paths.root)
        self._reset_directory(paths.result_dir, paths.root)

    def _reset_directory(self, directory: Path, job_root: Path) -> None:
        if directory.is_symlink():
            raise UnsafePathError("任务产物目录不能是符号链接。")
        resolved = directory.resolve(strict=False)
        if not resolved.is_relative_to(job_root.resolve()):
            raise UnsafePathError("任务产物目录超出任务边界。")
        if directory.exists():
            if not directory.is_dir():
                raise UnsafePathError("任务产物路径不是目录。")
            shutil.rmtree(directory)
        directory.mkdir()

    def delete(self, job_id: str) -> None:
        paths = self.paths(job_id)
        shutil.rmtree(paths.root)
        _fsync_directory(self.outputs_dir)
