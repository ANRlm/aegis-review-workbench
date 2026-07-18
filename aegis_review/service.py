"""Persistent job lifecycle and single-worker analysis orchestration."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Lock, RLock
from typing import Any, TypeAlias

from .domain import (
    AnalysisReport,
    AssetInput,
    AuditDecision,
    AuditSettings,
    JobRecord,
    JobStatus,
    MediaType,
)
from .storage import (
    JobAlreadyExistsError,
    JobStorage,
    atomic_write_json,
    read_json,
)


AnalysisRunner: TypeAlias = Callable[
    [Path, Path, Path, AuditSettings],
    AnalysisReport,
]
Clock: TypeAlias = Callable[[], datetime]


class JobServiceError(RuntimeError):
    """Base class for service-layer failures."""


class JobExecutionError(JobServiceError):
    """Raised when a job cannot be submitted to the background executor."""


class AnalysisContractError(JobServiceError):
    """Raised when an analyzer returns a report that violates the contract."""


class InvalidStatusTransition(JobServiceError, ValueError):
    """Raised when a job tries to skip or reverse its lifecycle."""


ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset({JobStatus.QUEUED}),
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.FAILED}),
    JobStatus.RUNNING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
}

SUPPORTED_EXTENSIONS: dict[MediaType, frozenset[str]] = {
    MediaType.IMAGE: frozenset({"jpg", "jpeg", "png"}),
    MediaType.VIDEO: frozenset({"mp4", "mov"}),
}


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    """Validate the published job lifecycle before persistent state changes."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidStatusTransition(
            f"invalid job status transition: {current.value} -> {target.value}"
        )


class JobService:
    """Coordinate durable job state without depending on Flask or Ultralytics."""

    def __init__(
        self,
        storage: JobStorage,
        analyzer: AnalysisRunner,
        *,
        executor: Executor | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.storage = storage
        self._analyzer = analyzer
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="aegis-analysis",
        )
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._locks: dict[str, RLock] = {}
        self._locks_guard = Lock()

    def _job_lock(self, job_id: str) -> RLock:
        with self._locks_guard:
            return self._locks.setdefault(job_id, RLock())

    def _now_iso(self) -> str:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise JobServiceError("任务时钟必须包含时区。")
        return value.isoformat(timespec="seconds")

    def create_job(
        self,
        asset: AssetInput,
        project_name: str,
        settings: AuditSettings,
    ) -> dict[str, Any]:
        if not isinstance(asset, AssetInput):
            raise TypeError("asset must be an AssetInput")
        if not isinstance(settings, AuditSettings):
            raise TypeError("settings must be an AuditSettings")
        if asset.extension not in SUPPORTED_EXTENSIONS[asset.media_type]:
            raise ValueError("不支持的素材扩展名。")

        last_collision: JobAlreadyExistsError | None = None
        for _attempt in range(5):
            job_id = self.storage.new_job_id(self._clock())
            record = JobRecord(
                job_id=job_id,
                project_name=project_name,
                asset_name=asset.original_name,
                asset_type=asset.media_type,
                asset_file=f"original.{asset.extension}",
                status=JobStatus.CREATED,
                created_at=self._now_iso(),
                started_at=None,
                completed_at=None,
                settings=settings.to_dict(),
                result_file=None,
                error=None,
            )
            try:
                return self.storage.create(record, asset).to_dict()
            except JobAlreadyExistsError as error:
                last_collision = error
        raise JobServiceError("无法创建唯一任务目录。") from last_collision

    def enqueue_analysis(self, job_id: str) -> dict[str, Any]:
        with self._job_lock(job_id):
            record = self.storage.read(job_id)
            validate_transition(record.status, JobStatus.QUEUED)
            if record.status is JobStatus.FAILED:
                self.storage.clear_results(job_id)
            record.status = JobStatus.QUEUED
            record.started_at = None
            record.completed_at = None
            record.result_file = None
            record.error = None
            self.storage.write(record)
            queued_payload = record.to_dict()
            try:
                self._executor.submit(self._run_job, job_id)
            except Exception as error:
                validate_transition(record.status, JobStatus.FAILED)
                record.status = JobStatus.FAILED
                record.completed_at = self._now_iso()
                record.error = "后台任务提交失败。"
                self.storage.write(record)
                raise JobExecutionError("后台任务提交失败。") from error
            return queued_payload

    def _run_job(self, job_id: str) -> None:
        try:
            with self._job_lock(job_id):
                record = self.storage.read(job_id)
                validate_transition(record.status, JobStatus.RUNNING)
                record.status = JobStatus.RUNNING
                record.started_at = self._now_iso()
                record.completed_at = None
                record.error = None
                self.storage.write(record)

            paths = self.storage.paths(job_id)
            settings = AuditSettings.from_dict(record.settings)
            report = self._analyzer(
                paths.input_dir / record.asset_file,
                paths.evidence_dir,
                paths.result_dir,
                settings,
            )
            self._validate_report(job_id, report)
            atomic_write_json(
                paths.result_dir / "analysis_report.json",
                report.to_dict(),
            )

            with self._job_lock(job_id):
                record = self.storage.read(job_id)
                validate_transition(record.status, JobStatus.COMPLETED)
                record.status = JobStatus.COMPLETED
                record.completed_at = self._now_iso()
                record.result_file = "analysis_report.json"
                record.error = None
                self.storage.write(record)
        except Exception as error:
            self._persist_worker_failure(job_id, error)

    def _validate_report(
        self,
        job_id: str,
        report: AnalysisReport,
    ) -> None:
        if not isinstance(report, AnalysisReport):
            raise AnalysisContractError("分析器没有返回有效报告。")
        if report.job_id != job_id:
            raise AnalysisContractError("分析报告与任务编号不一致。")
        if not isinstance(report.auto_decision, AuditDecision) or not isinstance(
            report.final_decision,
            AuditDecision,
        ):
            raise AnalysisContractError("分析报告缺少审核结论。")

    def _persist_worker_failure(
        self,
        job_id: str,
        error: Exception,
    ) -> None:
        message = (
            str(error)
            if isinstance(error, AnalysisContractError)
            else "分析任务执行失败。"
        )
        with self._job_lock(job_id):
            record = self.storage.read(job_id)
            if record.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
                return
            validate_transition(record.status, JobStatus.FAILED)
            record.status = JobStatus.FAILED
            record.completed_at = self._now_iso()
            record.result_file = None
            record.error = message
            self.storage.write(record)

    def list_jobs(
        self,
        status: JobStatus | str | None = None,
    ) -> list[dict[str, Any]]:
        expected_status = JobStatus(status) if status is not None else None
        return [
            record.to_dict()
            for record in self.storage.list_records()
            if expected_status is None or record.status is expected_status
        ]

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._job_lock(job_id):
            return self.storage.read(job_id).to_dict()

    def get_report(self, job_id: str) -> dict[str, Any]:
        with self._job_lock(job_id):
            record = self.storage.read(job_id)
            if record.status is not JobStatus.COMPLETED:
                raise InvalidStatusTransition(
                    "only completed jobs have reports"
                )
            paths = self.storage.paths(job_id)
            return AnalysisReport.from_dict(
                read_json(paths.result_dir / "analysis_report.json")
            ).to_dict()

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
