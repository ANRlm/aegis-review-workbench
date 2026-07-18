from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from aegis_review.cv.exceptions import CvPipelineError, ModelMissingError
from aegis_review.cv.pipeline import analyze_asset
from aegis_review.domain import AuditDecision, AuditSettings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeDetector:
    def __init__(self, detections: list[dict] | None = None) -> None:
        self.detections = list(detections or [])
        self.calls = 0

    def detect(self, frame: np.ndarray, confidence: float) -> list[dict]:
        assert isinstance(frame, np.ndarray)
        assert frame.size > 0
        self.calls += 1
        return [dict(item) for item in self.detections]


class SequenceDetector:
    """Return a fixed detection list per detect() call index."""

    def __init__(self, per_call: list[list[dict]]) -> None:
        self.per_call = [list(items) for items in per_call]
        self.calls = 0

    def detect(self, frame: np.ndarray, confidence: float) -> list[dict]:
        assert isinstance(frame, np.ndarray)
        assert frame.size > 0
        index = self.calls
        self.calls += 1
        if index >= len(self.per_call):
            return []
        return [dict(item) for item in self.per_call[index]]


def _write_image(path: Path) -> None:
    image = np.zeros((40, 50, 3), dtype=np.uint8)
    image[:] = (40, 80, 120)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    encoded.tofile(str(path))


def _write_video(path: Path, *, frame_count: int, fps: float) -> None:
    width, height = 64, 48
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    assert writer.isOpened()
    for index in range(frame_count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = ((index * 17) % 255, 40, 90)
        writer.write(frame)
    writer.release()


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


def _clean_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


def test_validate_dataset_script_runs_without_pythonpath() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "validate_dataset.py")],
        cwd=PROJECT_ROOT,
        env=_clean_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "VALIDATION OK" in completed.stdout


def test_train_model_help_runs_without_pythonpath() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "train_model.py"), "--help"],
        cwd=PROJECT_ROOT,
        env=_clean_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower() or "train" in completed.stdout.lower()


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
    assert report.evidence_frames == ["frame_000000.jpg"]
    assert detection["evidence_file"] == "frame_000000.jpg"
    assert (evidence_dir / "frame_000000.jpg").is_file()
    assert (result_dir / "analysis_report.json").is_file()
    assert (result_dir / "detections.csv").is_file()
    assert (result_dir / "audit_package.zip").is_file()

    with (result_dir / "detections.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["evidence_file"] == "frame_000000.jpg"

    with zipfile.ZipFile(result_dir / "audit_package.zip") as archive:
        names = set(archive.namelist())
    assert "job.json" in names
    assert "analysis_report.json" in names
    assert "detections.csv" in names
    assert "evidence/frame_000000.jpg" in names
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
    assert report.evidence_frames == ["frame_000000.jpg"]
    assert (evidence_dir / "frame_000000.jpg").is_file()


def test_pipeline_pads_evidence_to_min_evidence_frames(tmp_path: Path) -> None:
    root, evidence_dir, result_dir = _job_dirs(tmp_path)
    video_path = root / "pad.mp4"
    _write_video(video_path, frame_count=30, fps=10.0)
    # Three sampled frames (0,10,20); only the first has a detection.
    detector = SequenceDetector(
        [
            [
                {
                    "class_id": 1,
                    "class_name": "enemy",
                    "confidence": 0.71,
                    "bbox_xyxy": [3.0, 4.0, 20.0, 22.0],
                }
            ],
            [],
            [],
        ]
    )
    settings = AuditSettings(min_evidence_frames=3, sample_interval_seconds=1.0)
    report = analyze_asset(
        video_path,
        evidence_dir,
        result_dir,
        settings,
        detector,
    )
    assert report.evidence_frames == [
        "frame_000000.jpg",
        "frame_000010.jpg",
        "frame_000020.jpg",
    ]
    for name in report.evidence_frames:
        assert (evidence_dir / name).is_file()


def test_pipeline_video_analyze_asset_with_fake_detector(tmp_path: Path) -> None:
    root, evidence_dir, result_dir = _job_dirs(tmp_path)
    video_path = root / "clip.mp4"
    _write_video(video_path, frame_count=30, fps=10.0)
    detector = SequenceDetector(
        [
            [
                {
                    "class_id": 0,
                    "class_name": "player",
                    "confidence": 0.55,
                    "bbox_xyxy": [1.0, 1.0, 12.0, 12.0],
                }
            ],
            [
                {
                    "class_id": 1,
                    "class_name": "enemy",
                    "confidence": 0.44,
                    "bbox_xyxy": [5.0, 6.0, 18.0, 19.0],
                }
            ],
            [],
        ]
    )
    settings = AuditSettings(min_evidence_frames=3, sample_interval_seconds=1.0)
    report = analyze_asset(
        video_path,
        evidence_dir,
        result_dir,
        settings,
        detector,
    )

    assert detector.calls == 3
    assert report.auto_decision is AuditDecision.REVIEW
    assert len(report.detections) == 2
    assert report.detections[0]["timestamp_seconds"] == pytest.approx(0.0)
    assert report.detections[1]["timestamp_seconds"] == pytest.approx(1.0)
    assert report.detections[0]["frame_index"] == 0
    assert report.detections[1]["frame_index"] == 10
    assert isinstance(report.detections[0]["confidence"], float)
    assert isinstance(report.detections[1]["bbox_xyxy"][0], float)
    assert report.evidence_frames == [
        "frame_000010.jpg",
        "frame_000000.jpg",
        "frame_000020.jpg",
    ]
    for name in report.evidence_frames:
        assert name.startswith("frame_") and name.endswith(".jpg")
        assert (evidence_dir / name).is_file()

    payload = json.loads((result_dir / "analysis_report.json").read_text(encoding="utf-8"))
    assert payload["evidence_frames"] == report.evidence_frames
    assert payload["detections"][1]["class_name"] == "enemy"

    with (result_dir / "detections.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[1]["evidence_file"] == "frame_000010.jpg"

    with zipfile.ZipFile(result_dir / "audit_package.zip") as archive:
        names = set(archive.namelist())
    assert "job.json" in names
    assert "analysis_report.json" in names
    assert "detections.csv" in names
    assert "evidence/frame_000000.jpg" in names
    assert "evidence/frame_000010.jpg" in names
    assert "evidence/frame_000020.jpg" in names


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
    assert report.evidence_frames == ["frame_000000.jpg"]


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
    not (PROJECT_ROOT / "models" / "aegis_game_best.pt").is_file(),
    reason="final model not trained yet",
)
def test_real_model_smoke_image(tmp_path: Path) -> None:
    from aegis_review.cv.detector import UltralyticsDetector

    root, evidence_dir, result_dir = _job_dirs(tmp_path)
    image_path = root / "real.jpg"
    source = next((PROJECT_ROOT / "dataset" / "images" / "val").glob("*"))
    image_path.write_bytes(source.read_bytes())
    detector = UltralyticsDetector(PROJECT_ROOT / "models" / "aegis_game_best.pt")
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
    assert all(name.startswith("frame_") for name in report.evidence_frames)
