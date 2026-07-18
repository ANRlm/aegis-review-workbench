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
    JobRecord,
    JobStatus,
    MediaType,
)
from aegis_review.service import (
    AnalysisContractError,
    ArtifactNotFoundError,
    InvalidStatusTransition,
    JobBusyError,
    JobExecutionError,
    JobService,
)
from aegis_review.storage import JobStorage, atomic_write_json


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


def test_constructor_recovers_interrupted_jobs_without_submitting_work(
    tmp_path: Path,
) -> None:
    storage = JobStorage(tmp_path / "outputs", max_asset_bytes=20)
    statuses = [
        JobStatus.CREATED,
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
    ]
    job_ids: dict[JobStatus, str] = {}
    for index, status in enumerate(statuses, start=1):
        job_id = f"20260718_10150{index}_{index:08x}"
        job_ids[status] = job_id
        record = storage.create(
            JobRecord(
                job_id=job_id,
                project_name="恢复测试",
                asset_name="clip.mp4",
                asset_type=MediaType.VIDEO,
                asset_file="original.mp4",
                status=status,
                created_at=NOW.isoformat(timespec="seconds"),
                started_at=(
                    NOW.isoformat(timespec="seconds")
                    if status is JobStatus.RUNNING
                    else None
                ),
                completed_at=(
                    NOW.isoformat(timespec="seconds")
                    if status in {JobStatus.COMPLETED, JobStatus.FAILED}
                    else None
                ),
                settings=AuditSettings().to_dict(),
                result_file=(
                    "analysis_report.json"
                    if status is JobStatus.COMPLETED
                    else None
                ),
                error="旧错误" if status is JobStatus.FAILED else None,
            ),
            make_asset(),
        )
        assert record.status is status
    executor = CapturingExecutor(storage)

    JobService(
        storage=storage,
        analyzer=successful_analyzer,
        executor=executor,
        clock=lambda: NOW,
    )

    assert storage.read(job_ids[JobStatus.CREATED]).status is JobStatus.CREATED
    assert storage.read(job_ids[JobStatus.COMPLETED]).status is JobStatus.COMPLETED
    assert storage.read(job_ids[JobStatus.FAILED]).error == "旧错误"
    for interrupted in (JobStatus.QUEUED, JobStatus.RUNNING):
        recovered = storage.read(job_ids[interrupted])
        assert recovered.status is JobStatus.FAILED
        assert recovered.completed_at == NOW.isoformat(timespec="seconds")
        assert recovered.error == "服务中断，任务未完成。"
    assert executor.calls == []


def test_delete_rejects_busy_jobs_and_deletes_terminal_jobs(
    tmp_path: Path,
) -> None:
    service, storage, _executor = create_service(tmp_path)
    created = service.create_job(make_asset(), "可删除", AuditSettings())
    busy = service.create_job(make_asset(), "运行中", AuditSettings())
    service.enqueue_analysis(busy["job_id"])

    with pytest.raises(JobBusyError):
        service.delete_job(busy["job_id"])

    service.delete_job(created["job_id"])
    assert not storage.paths(
        created["job_id"],
        require_exists=False,
    ).root.exists()


def test_review_updates_final_decision_and_preserves_automatic_decision(
    tmp_path: Path,
) -> None:
    service, _storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()

    report = service.review_job(
        job["job_id"],
        AuditDecision.REJECT,
        "  审核员  ",
        "  人工确认不通过  ",
    )

    assert report["auto_decision"] == "pass"
    assert report["final_decision"] == "reject"
    assert report["reviewer"] == "审核员"
    assert report["note"] == "人工确认不通过"
    assert service.get_job(job["job_id"])["status"] == "completed"


@pytest.mark.parametrize(
    ("reviewer", "note"),
    [
        ("", None),
        (" " * 5, None),
        ("审" * 41, None),
        ("审核员", "备" * 501),
    ],
)
def test_review_rejects_invalid_reviewer_or_note(
    tmp_path: Path,
    reviewer: str,
    note: str | None,
) -> None:
    service, _storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()

    with pytest.raises(ValueError):
        service.review_job(
            job["job_id"],
            AuditDecision.REVIEW,
            reviewer,
            note,
        )


def test_review_rejects_non_completed_job(tmp_path: Path) -> None:
    service, _storage, _executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())

    with pytest.raises(InvalidStatusTransition):
        service.review_job(
            job["job_id"],
            AuditDecision.REVIEW,
            "审核员",
            None,
        )


def test_resolve_artifact_allows_only_report_and_job_whitelist(
    tmp_path: Path,
) -> None:
    service, _storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()

    expected = {
        "original.mp4": b"video",
        "frame_000001.jpg": b"frame",
        "detections.csv": b"class,confidence\n",
        "audit_package.zip": b"zip",
    }
    for filename, content in expected.items():
        assert service.resolve_artifact(job["job_id"], filename).read_bytes() == content
    report_path = service.resolve_artifact(
        job["job_id"],
        "analysis_report.json",
    )
    assert report_path.name == "analysis_report.json"


@pytest.mark.parametrize(
    "filename",
    [
        "../original.mp4",
        "input/original.mp4",
        "input\\original.mp4",
        "/tmp/original.mp4",
        ".",
        "..",
        "not-in-report.txt",
    ],
)
def test_resolve_artifact_rejects_unlisted_or_unsafe_names(
    tmp_path: Path,
    filename: str,
) -> None:
    service, _storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()

    with pytest.raises(ArtifactNotFoundError):
        service.resolve_artifact(job["job_id"], filename)


def test_resolve_artifact_rejects_symlink_escape(tmp_path: Path) -> None:
    service, storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()
    evidence = storage.paths(job["job_id"]).evidence_dir / "frame_000001.jpg"
    evidence.unlink()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    evidence.symlink_to(outside)

    with pytest.raises(ArtifactNotFoundError):
        service.resolve_artifact(job["job_id"], evidence.name)


def test_get_report_rejects_symlink_file(tmp_path: Path) -> None:
    service, storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()
    report_file = storage.paths(job["job_id"]).result_dir / "analysis_report.json"
    report_file.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    report_file.symlink_to(outside)

    with pytest.raises(ArtifactNotFoundError):
        service.get_report(job["job_id"])


def test_get_report_wraps_malformed_report_payload(tmp_path: Path) -> None:
    service, storage, executor = create_service(tmp_path)
    job = service.create_job(make_asset(), "项目", AuditSettings())
    service.enqueue_analysis(job["job_id"])
    executor.run_next()
    report_path = (
        storage.paths(job["job_id"]).result_dir / "analysis_report.json"
    )
    malformed = service.get_report(job["job_id"])
    malformed["downloads"] = None
    atomic_write_json(report_path, malformed)

    with pytest.raises(AnalysisContractError, match="分析报告无法读取"):
        service.get_report(job["job_id"])


def test_stats_counts_all_jobs_and_prefers_final_decision(
    tmp_path: Path,
) -> None:
    outcomes: Any = iter(
        [
            AuditDecision.PASS,
            AuditDecision.REVIEW,
            AuditDecision.REJECT,
            RuntimeError("failed"),
        ]
    )

    def sequenced_analyzer(
        input_path: Path,
        _evidence: Path,
        _result: Path,
        settings: AuditSettings,
    ) -> AnalysisReport:
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        decision = outcome
        return AnalysisReport(
            job_id=input_path.parents[1].name,
            rules=settings.to_dict(),
            auto_decision=decision,
            final_decision=decision,
        )

    service, _storage, executor = create_service(tmp_path, sequenced_analyzer)
    completed_ids: list[str] = []
    for name in ("通过", "复核", "拒绝"):
        job = service.create_job(make_asset(), name, AuditSettings())
        completed_ids.append(job["job_id"])
        service.enqueue_analysis(job["job_id"])
        executor.run_next()
    service.review_job(
        completed_ids[0],
        AuditDecision.REJECT,
        "审核员",
        None,
    )
    service.create_job(make_asset(), "仅创建", AuditSettings())

    failed = service.create_job(make_asset(), "失败", AuditSettings())
    service.enqueue_analysis(failed["job_id"])
    executor.run_next()

    assert service.stats() == {
        "total": 5,
        "pass": 0,
        "review": 1,
        "reject": 2,
        "failed": 1,
    }
