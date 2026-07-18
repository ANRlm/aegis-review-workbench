from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from aegis_review.cv.exceptions import CvPipelineError, ModelMissingError
from aegis_review.cv.pipeline import analyze_asset
from aegis_review.domain import AuditDecision, AuditSettings


class FakeDetector:
    def __init__(self, detections: list[dict] | None = None) -> None:
        self.detections = list(detections or [])
        self.calls = 0

    def detect(self, frame: np.ndarray, confidence: float) -> list[dict]:
        assert isinstance(frame, np.ndarray)
        assert frame.size > 0
        self.calls += 1
        return [dict(item) for item in self.detections]


def _write_image(path: Path) -> None:
    image = np.zeros((40, 50, 3), dtype=np.uint8)
    image[:] = (40, 80, 120)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    encoded.tofile(str(path))


def _job_dirs(tmp_path: Path, job_id: str = "20260718_101530_a1b2c3d4") -> tuple[Path, Path, Path]:
    root = tmp_path / job_id
    evidence = root / "evidence"
    result = root / "result"
    evidence.mkdir(parents=True)
    result.mkdir(parents=True)
    (root / "job.json").write_text(
        json.dumps({"job_id": job_id, "status": "running"}),
        encoding="utf-8",
    )
    return root, evidence, result


def test_pipeline_image_with_enemy_reject(tmp_path: Path) -> None:
    root, evidence_dir, result_dir = _job_dirs(tmp_path)
    image_path = root / "input.jpg"
    _write_image(image_path)
    detector = FakeDetector(
        [
            {
                "class_id": 1,
                "class_name": "enemy",
                "confidence": 0.82,
                "bbox_xyxy": [1.0, 2.0, 20.0, 18.0],
            }
        ]
    )
    report = analyze_asset(
        image_path,
        evidence_dir,
        result_dir,
        AuditSettings(),
        detector,
    )
    assert report.auto_decision is AuditDecision.REJECT
    assert report.final_decision is AuditDecision.REJECT
    assert len(report.detections) == 1
    detection = report.detections[0]
    assert set(detection) == {
        "frame_index",
        "timestamp_seconds",
        "class_id",
        "class_name",
        "confidence",
        "bbox_xyxy",
        "evidence_file",
    }
    assert isinstance(detection["confidence"], float)
    assert isinstance(detection["bbox_xyxy"][0], float)
    assert report.evidence_frames
    assert (evidence_dir / report.evidence_frames[0]).is_file()
    assert (result_dir / "analysis_report.json").is_file()
    assert (result_dir / "detections.csv").is_file()
    assert (result_dir / "audit_package.zip").is_file()

    with (result_dir / "detections.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1

    with zipfile.ZipFile(result_dir / "audit_package.zip") as archive:
        names = set(archive.namelist())
    assert "job.json" in names
    assert "analysis_report.json" in names
    assert "detections.csv" in names
    assert any(name.startswith("evidence/") for name in names)
    assert not any("models/" in name or "dataset/" in name for name in names)


def test_pipeline_no_detection_still_saves_representative_frame(tmp_path: Path) -> None:
    root, evidence_dir, result_dir = _job_dirs(tmp_path)
    image_path = root / "empty.jpg"
    _write_image(image_path)
    report = analyze_asset(
        image_path,
        evidence_dir,
        result_dir,
        AuditSettings(),
        FakeDetector(),
    )
    assert report.auto_decision is AuditDecision.PASS
    assert report.note == "未发现规则目标"
    assert len(report.evidence_frames) == 1
    assert (evidence_dir / report.evidence_frames[0]).is_file()


def test_pipeline_review_band(tmp_path: Path) -> None:
    root, evidence_dir, result_dir = _job_dirs(tmp_path)
    image_path = root / "review.jpg"
    _write_image(image_path)
    detector = FakeDetector(
        [
            {
                "class_id": 1,
                "class_name": "enemy",
                "confidence": 0.42,
                "bbox_xyxy": [2.0, 2.0, 10.0, 10.0],
            }
        ]
    )
    report = analyze_asset(
        image_path,
        evidence_dir,
        result_dir,
        AuditSettings(),
        detector,
    )
    assert report.auto_decision is AuditDecision.REVIEW


def test_missing_model_raises_readable_error(tmp_path: Path) -> None:
    from aegis_review.cv.detector import UltralyticsDetector

    with pytest.raises(ModelMissingError, match="模型文件不存在"):
        UltralyticsDetector(tmp_path / "missing.pt")


def test_corrupt_media_raises_readable_error(tmp_path: Path) -> None:
    root, evidence_dir, result_dir = _job_dirs(tmp_path)
    bad = root / "broken.jpg"
    bad.write_bytes(b"nope")
    with pytest.raises(CvPipelineError):
        analyze_asset(
            bad,
            evidence_dir,
            result_dir,
            AuditSettings(),
            FakeDetector(),
        )


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "models" / "aegis_game_best.pt").is_file(),
    reason="final model not trained yet",
)
def test_real_model_smoke_image(tmp_path: Path) -> None:
    from aegis_review.cv.detector import UltralyticsDetector

    root, evidence_dir, result_dir = _job_dirs(tmp_path)
    image_path = root / "real.jpg"
    source = next(
        (Path(__file__).resolve().parents[1] / "dataset" / "images" / "val").glob("*")
    )
    image_path.write_bytes(source.read_bytes())
    detector = UltralyticsDetector(
        Path(__file__).resolve().parents[1] / "models" / "aegis_game_best.pt"
    )
    report = analyze_asset(
        image_path,
        evidence_dir,
        result_dir,
        AuditSettings(),
        detector,
    )
    assert report.auto_decision in {
        AuditDecision.PASS,
        AuditDecision.REVIEW,
        AuditDecision.REJECT,
    }
    assert report.evidence_frames
