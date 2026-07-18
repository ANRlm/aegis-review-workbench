from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import app as app_entrypoint

from aegis_review import create_app
from aegis_review.config import AppConfig, PROJECT_ROOT
from aegis_review.domain import (
    AssetInput,
    AuditSettings,
    JobRecord,
    JobStatus,
    MediaType,
)
from aegis_review.service import JobService
from aegis_review.storage import JobStorage


NOW = datetime.fromisoformat("2026-07-18T10:15:30+08:00")


def make_asset() -> AssetInput:
    return AssetInput(
        original_name="clip.mp4",
        extension="mp4",
        media_type=MediaType.VIDEO,
        stream=BytesIO(b"video"),
    )


def test_create_app_registers_an_injected_job_service(tmp_path: Path) -> None:
    injected_service = object()

    flask_app = create_app(
        AppConfig(project_root=tmp_path, testing=True),
        job_service=injected_service,
    )

    assert flask_app.extensions["aegis_job_service"] is injected_service


def test_default_job_service_recovers_interrupted_records(tmp_path: Path) -> None:
    config = AppConfig(project_root=tmp_path, testing=True)
    storage = JobStorage(config.outputs_dir, config.max_content_length)
    job_id = "20260718_101530_a1b2c3d4"
    storage.create(
        JobRecord(
            job_id=job_id,
            project_name="恢复测试",
            asset_name="clip.mp4",
            asset_type=MediaType.VIDEO,
            asset_file="original.mp4",
            status=JobStatus.QUEUED,
            created_at=NOW.isoformat(timespec="seconds"),
            started_at=None,
            completed_at=None,
            settings=AuditSettings().to_dict(),
            result_file=None,
            error=None,
        ),
        make_asset(),
    )

    flask_app = create_app(config)
    service = flask_app.extensions["aegis_job_service"]

    assert isinstance(service, JobService)
    assert service.get_job(job_id)["status"] == "failed"
    assert service.get_job(job_id)["error"] == "服务中断，任务未完成。"
    service.shutdown()


def test_default_unavailable_analyzer_leaves_retryable_failed_job(
    tmp_path: Path,
) -> None:
    flask_app = create_app(AppConfig(project_root=tmp_path, testing=True))
    service: JobService = flask_app.extensions["aegis_job_service"]
    job = service.create_job(make_asset(), "项目", AuditSettings())

    queued = service.enqueue_analysis(job["job_id"])
    service.shutdown(wait=True)

    assert queued["status"] == "queued"
    failed = service.get_job(job["job_id"])
    assert failed["status"] == "failed"
    assert failed["error"] == "CV 分析组件尚未就绪。"


def test_default_job_service_uses_trained_model_when_present(
    tmp_path: Path,
) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "aegis_game_best.pt").write_bytes(
        (PROJECT_ROOT / "models" / "aegis_game_best.pt").read_bytes()
    )
    image_bytes = next(
        (PROJECT_ROOT / "dataset" / "images" / "val").glob("*.jpg")
    ).read_bytes()

    flask_app = create_app(AppConfig(project_root=tmp_path, testing=True))
    service: JobService = flask_app.extensions["aegis_job_service"]
    job = service.create_job(
        AssetInput(
            original_name="real.jpg",
            extension="jpg",
            media_type=MediaType.IMAGE,
            stream=BytesIO(image_bytes),
        ),
        "真实模型集成",
        AuditSettings(),
    )

    service.enqueue_analysis(job["job_id"])
    service.shutdown(wait=True)

    completed = service.get_job(job["job_id"])
    assert completed["status"] == "completed"
    report = service.get_report(job["job_id"])
    assert report["job_id"] == job["job_id"]
    assert report["evidence_frames"]


def test_entrypoint_disables_reloader_even_in_debug_mode(
    monkeypatch: Any,
) -> None:
    run_calls: list[dict[str, Any]] = []

    class FakeApp:
        def run(self, **kwargs: Any) -> None:
            run_calls.append(kwargs)

    monkeypatch.setattr(app_entrypoint, "create_app", lambda: FakeApp())

    result = app_entrypoint.main(
        ["--host", "0.0.0.0", "--port", "7999", "--debug"]
    )

    assert result == 0
    assert run_calls == [
        {
            "host": "0.0.0.0",
            "port": 7999,
            "debug": True,
            "use_reloader": False,
        }
    ]
