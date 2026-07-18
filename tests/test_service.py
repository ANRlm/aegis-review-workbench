from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import Event
from typing import Any, Callable

import pytest

from aegis_review.domain import (
    AnalysisReport,
    AssetInput,
    AuditDecision,
    AuditSettings,
    JobStatus,
    MediaType,
)
from aegis_review.service import (
    InvalidStatusTransition,
    JobExecutionError,
    JobService,
)
from aegis_review.storage import JobStorage


NOW = datetime.fromisoformat("2026-07-18T10:15:30+08:00")


class CapturingExecutor:
    def __init__(self, storage: JobStorage) -> None:
        self.storage = storage
        self.submitted_statuses: list[JobStatus] = []
        self.calls: list[tuple[Callable[..., Any], tuple[Any, ...]]] = []
        self.shutdown_calls: list[bool] = []

    def submit(self, function: Callable[..., Any], *args: Any) -> Future[Any]:
        self.submitted_statuses.append(self.storage.read(args[0]).status)
        self.calls.append((function, args))
        return Future()

    def run_next(self) -> None:
        function, args = self.calls.pop(0)
        function(*args)

    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_calls.append(wait)


class FailingExecutor:
    def submit(self, _function: Callable[..., Any], *_args: Any) -> Future[Any]:
        raise RuntimeError("/private/tmp/executor exploded")

    def shutdown(self, wait: bool = True) -> None:
        del wait


def make_asset() -> AssetInput:
    return AssetInput(
        original_name="clip.mp4",
        extension="mp4",
        media_type=MediaType.VIDEO,
        stream=BytesIO(b"video"),
    )


def successful_analyzer(
    input_path: Path,
    evidence_dir: Path,
    result_dir: Path,
    settings: AuditSettings,
) -> AnalysisReport:
    assert input_path.read_bytes() == b"video"
    assert settings == AuditSettings()
    evidence = evidence_dir / "frame_000001.jpg"
    evidence.write_bytes(b"frame")
    (result_dir / "detections.csv").write_text("class,confidence\n", encoding="utf-8")
    (result_dir / "audit_package.zip").write_bytes(b"zip")
    job_id = input_path.parents[1].name
    return AnalysisReport(
        job_id=job_id,
        evidence_frames=[evidence.name],
        rules=settings.to_dict(),
        auto_decision=AuditDecision.PASS,
        final_decision=AuditDecision.PASS,
        downloads={
            "csv": "detections.csv",
            "zip": "audit_package.zip",
        },
    )


def create_service(
    tmp_path: Path,
    analyzer: Callable[..., AnalysisReport] = successful_analyzer,
) -> tuple[JobService, JobStorage, CapturingExecutor]:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    executor = CapturingExecutor(storage)
    service = JobService(
        storage=storage,
        analyzer=analyzer,
        executor=executor,
        clock=lambda: NOW,
    )
    return service, storage, executor


def test_create_job_persists_created_record(tmp_path: Path) -> None:
    service, storage, _executor = create_service(tmp_path)

    job = service.create_job(make_asset(), "  项目名称  ", AuditSettings())

    assert job["status"] == "created"
    assert job["project_name"] == "项目名称"
    assert job["asset_name"] == "clip.mp4"
    assert job["asset_type"] == "video"
    assert job["asset_file"] == "original.mp4"
    assert job["created_at"] == NOW.isoformat(timespec="seconds")
    assert storage.read(job["job_id"]).status is JobStatus.CREATED


def test_enqueue_persists_queued_before_submitting_worker(tmp_path: Path) -> None:
    service, storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())

    queued = service.enqueue_analysis(job["job_id"])

    assert queued["status"] == "queued"
    assert storage.read(job["job_id"]).status is JobStatus.QUEUED
    assert executor.submitted_statuses == [JobStatus.QUEUED]


def test_worker_persists_report_and_completed_job(tmp_path: Path) -> None:
    service, storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])

    executor.run_next()

    completed = storage.read(job["job_id"])
    assert completed.status is JobStatus.COMPLETED
    assert completed.started_at == NOW.isoformat(timespec="seconds")
    assert completed.completed_at == NOW.isoformat(timespec="seconds")
    assert completed.result_file == "analysis_report.json"
    report = service.get_report(job["job_id"])
    assert report["job_id"] == job["job_id"]
    assert report["auto_decision"] == "pass"
    assert report["final_decision"] == "pass"


def test_executor_submission_failure_is_persisted_without_path_leak(
    tmp_path: Path,
) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    service = JobService(
        storage=storage,
        analyzer=successful_analyzer,
        executor=FailingExecutor(),
        clock=lambda: NOW,
    )
    job = service.create_job(make_asset(), "项目", AuditSettings())

    with pytest.raises(JobExecutionError):
        service.enqueue_analysis(job["job_id"])

    failed = storage.read(job["job_id"])
    assert failed.status is JobStatus.FAILED
    assert failed.error == "后台任务提交失败。"
    assert "/private" not in failed.error


def test_analyzer_failure_is_persisted_without_exception_details(
    tmp_path: Path,
) -> None:
    def fail_analyzer(
        _input: Path,
        _evidence: Path,
        _result: Path,
        _settings: AuditSettings,
    ) -> AnalysisReport:
        raise RuntimeError("/Users/private/model failed")

    service, storage, executor = create_service(tmp_path, fail_analyzer)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])

    executor.run_next()

    failed = storage.read(job["job_id"])
    assert failed.status is JobStatus.FAILED
    assert failed.error == "分析任务执行失败。"
    assert "/Users" not in failed.error
    assert failed.result_file is None


def test_report_job_id_mismatch_marks_job_failed(tmp_path: Path) -> None:
    def wrong_report(
        _input: Path,
        _evidence: Path,
        _result: Path,
        settings: AuditSettings,
    ) -> AnalysisReport:
        report = AnalysisReport.new("20260718_101530_ffffffff", settings)
        report.auto_decision = AuditDecision.PASS
        report.final_decision = AuditDecision.PASS
        return report

    service, storage, executor = create_service(tmp_path, wrong_report)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])

    executor.run_next()

    failed = storage.read(job["job_id"])
    assert failed.status is JobStatus.FAILED
    assert failed.error == "分析报告与任务编号不一致。"


def test_running_analysis_does_not_block_status_reads(tmp_path: Path) -> None:
    started = Event()
    release = Event()

    def blocking_analyzer(
        input_path: Path,
        evidence_dir: Path,
        result_dir: Path,
        settings: AuditSettings,
    ) -> AnalysisReport:
        started.set()
        assert release.wait(timeout=2)
        return successful_analyzer(
            input_path,
            evidence_dir,
            result_dir,
            settings,
        )

    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    executor = ThreadPoolExecutor(max_workers=1)
    service = JobService(
        storage=storage,
        analyzer=blocking_analyzer,
        executor=executor,
        clock=lambda: NOW,
    )
    job = service.create_job(make_asset(), "项目", AuditSettings())

    queued = service.enqueue_analysis(job["job_id"])
    assert started.wait(timeout=2)

    assert queued["status"] == "queued"
    assert service.get_job(job["job_id"])["status"] == "running"
    release.set()
    service.shutdown(wait=True)
    assert service.get_job(job["job_id"])["status"] == "completed"


def test_completed_job_cannot_be_analyzed_again(tmp_path: Path) -> None:
    service, _storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()

    with pytest.raises(InvalidStatusTransition):
        service.enqueue_analysis(job["job_id"])


def test_failed_job_clears_old_results_before_retry(tmp_path: Path) -> None:
    attempts = 0

    def flaky_analyzer(
        input_path: Path,
        evidence_dir: Path,
        result_dir: Path,
        settings: AuditSettings,
    ) -> AnalysisReport:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            (evidence_dir / "partial.jpg").write_bytes(b"partial")
            (result_dir / "partial.json").write_text("{}", encoding="utf-8")
            raise RuntimeError("failed")
        assert list(evidence_dir.iterdir()) == []
        assert list(result_dir.iterdir()) == []
        return successful_analyzer(
            input_path,
            evidence_dir,
            result_dir,
            settings,
        )

    service, storage, executor = create_service(tmp_path, flaky_analyzer)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()
    assert storage.read(job["job_id"]).status is JobStatus.FAILED

    retried = service.enqueue_analysis(job["job_id"])
    executor.run_next()

    assert retried["status"] == "queued"
    assert storage.read(job["job_id"]).status is JobStatus.COMPLETED
