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
    SUPPORTED_MEDIA_EXTENSIONS,
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


class JobBusyError(JobServiceError):
    """Raised when a running or queued job cannot be deleted."""


class ArtifactNotFoundError(JobServiceError, FileNotFoundError):
    """Raised when an artifact name is unsafe, unlisted, or unavailable."""


class InvalidStatusTransition(JobServiceError, ValueError):
    """Raised when a job tries to skip or reverse its lifecycle."""


ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset({JobStatus.QUEUED}),
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.FAILED}),
    JobStatus.RUNNING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
}

SUPPORTED_EXTENSIONS = SUPPORTED_MEDIA_EXTENSIONS


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    """Validate the published job lifecycle before persistent state changes."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidStatusTransition(
            f"invalid job status transition: {current.value} -> {target.value}"
        )


class UnavailableAnalyzer:
    """Keep the service bootable until the CV branch provides a bound runner."""

    def __call__(
        self,
        _input_path: Path,
        _evidence_dir: Path,
        _result_dir: Path,
        _settings: AuditSettings,
    ) -> AnalysisReport:
        raise AnalysisContractError("CV 分析组件尚未就绪。")


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
        self.recover_interrupted()

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
            return self._load_report(record).to_dict()

    def recover_interrupted(self) -> None:
        for visible_record in self.storage.list_records():
            if visible_record.status not in {
                JobStatus.QUEUED,
                JobStatus.RUNNING,
            }:
                continue
            with self._job_lock(visible_record.job_id):
                record = self.storage.read(visible_record.job_id)
                if record.status not in {
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                }:
                    continue
                validate_transition(record.status, JobStatus.FAILED)
                record.status = JobStatus.FAILED
                record.completed_at = self._now_iso()
                record.result_file = None
                record.error = "服务中断，任务未完成。"
                self.storage.write(record)

    def delete_job(self, job_id: str) -> None:
        with self._job_lock(job_id):
            record = self.storage.read(job_id)
            if record.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                raise JobBusyError("任务正在处理，暂时不能删除。")
            self.storage.delete(job_id)

    def review_job(
        self,
        job_id: str,
        decision: AuditDecision | str,
        reviewer: str,
        note: str | None,
    ) -> dict[str, Any]:
        try:
            final_decision = AuditDecision(decision)
        except ValueError as error:
            raise ValueError("decision must be pass, review, or reject") from error
        if not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 40:
            raise ValueError("reviewer must contain between 1 and 40 characters")
        normalized_note: str | None
        if note is None:
            normalized_note = None
        elif not isinstance(note, str) or len(note.strip()) > 500:
            raise ValueError("note must contain no more than 500 characters")
        else:
            normalized_note = note.strip() or None

        with self._job_lock(job_id):
            record = self.storage.read(job_id)
            if record.status is not JobStatus.COMPLETED:
                raise InvalidStatusTransition(
                    "only completed jobs can be reviewed"
                )
            report = self._load_report(record)
            report.final_decision = final_decision
            report.reviewer = reviewer.strip()
            report.note = normalized_note
            report_path = self._known_file(
                self.storage.paths(job_id).result_dir / record.result_file,
                self.storage.paths(job_id).root,
            )
            atomic_write_json(report_path, report.to_dict())
            return report.to_dict()

    def resolve_artifact(self, job_id: str, filename: str) -> Path:
        if not self._is_safe_basename(filename):
            raise ArtifactNotFoundError("任务产物不存在。")
        with self._job_lock(job_id):
            record = self.storage.read(job_id)
            paths = self.storage.paths(job_id)
            allowed: dict[str, Path] = {
                record.asset_file: paths.input_dir / record.asset_file,
            }
            if record.status is JobStatus.COMPLETED:
                report = self._load_report(record)
                if record.result_file is not None:
                    allowed[record.result_file] = (
                        paths.result_dir / record.result_file
                    )
                for evidence_name in report.evidence_frames:
                    if not self._is_safe_basename(evidence_name):
                        raise ArtifactNotFoundError("证据文件名不安全。")
                    allowed[evidence_name] = paths.evidence_dir / evidence_name
                for download_name in report.downloads.values():
                    if not self._is_safe_basename(download_name):
                        raise ArtifactNotFoundError("下载文件名不安全。")
                    allowed[download_name] = paths.result_dir / download_name
            selected = allowed.get(filename)
            if selected is None:
                raise ArtifactNotFoundError("任务产物不存在。")
            return self._known_file(selected, paths.root)

    def stats(self) -> dict[str, int]:
        records = self.storage.list_records()
        result = {
            "total": len(records),
            "pass": 0,
            "review": 0,
            "reject": 0,
            "failed": 0,
        }
        for record in records:
            if record.status is JobStatus.FAILED:
                result["failed"] += 1
                continue
            if record.status is not JobStatus.COMPLETED:
                continue
            report = self._load_report(record)
            decision = report.final_decision or report.auto_decision
            if decision is None:
                raise AnalysisContractError("分析报告缺少审核结论。")
            result[decision.value] += 1
        return result

    def _load_report(self, record: JobRecord) -> AnalysisReport:
        if record.result_file is None:
            raise AnalysisContractError("已完成任务缺少报告文件。")
        paths = self.storage.paths(record.job_id)
        report_path = self._known_file(
            paths.result_dir / record.result_file,
            paths.root,
        )
        try:
            return AnalysisReport.from_dict(read_json(report_path))
        except (OSError, TypeError, ValueError) as error:
            raise AnalysisContractError("分析报告无法读取。") from error

    @staticmethod
    def _is_safe_basename(filename: object) -> bool:
        return (
            isinstance(filename, str)
            and bool(filename)
            and filename not in {".", ".."}
            and "/" not in filename
            and "\\" not in filename
            and not Path(filename).is_absolute()
        )

    @staticmethod
    def _known_file(candidate: Path, job_root: Path) -> Path:
        if candidate.is_symlink() or not candidate.is_file():
            raise ArtifactNotFoundError("任务产物不存在。")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise ArtifactNotFoundError("任务产物不存在。") from error
        if not resolved.is_relative_to(job_root.resolve()):
            raise ArtifactNotFoundError("任务产物超出任务目录。")
        return resolved

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
