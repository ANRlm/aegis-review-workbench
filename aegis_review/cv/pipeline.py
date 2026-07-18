"""End-to-end asset analysis: sample → detect → decide → evidence → artifacts."""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from aegis_review.cv.detector import Detector
from aegis_review.cv.exceptions import CvPipelineError, MediaDecodeError
from aegis_review.cv.rules import decide_audit
from aegis_review.cv.sampler import SampledFrame, sample_media
from aegis_review.domain import AnalysisReport, AuditDecision, AuditSettings


DETECTION_FIELDS = (
    "frame_index",
    "timestamp_seconds",
    "class_id",
    "class_name",
    "confidence",
    "bbox_xyxy",
    "evidence_file",
)


def _job_id_from_dirs(evidence_dir: Path, result_dir: Path) -> str:
    parent = Path(evidence_dir).resolve().parent
    if Path(result_dir).resolve().parent != parent:
        raise CvPipelineError("证据目录与结果目录不在同一任务目录下。")
    return parent.name


def _json_native(value: Any) -> Any:
    if isinstance(value, Path):
        return value.name
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "item"):
        return value.item()
    raise CvPipelineError(f"无法序列化为 JSON 的类型：{type(value)!r}")


def _draw_detections(
    frame: np.ndarray,
    detections: list[dict[str, Any]],
) -> np.ndarray:
    canvas = frame.copy()
    for detection in detections:
        x1, y1, x2, y2 = [int(round(v)) for v in detection["bbox_xyxy"]]
        label = f"{detection['class_name']} {detection['confidence']:.2f}"
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 180, 255), 2)
        text_origin = (x1, max(16, y1 - 8))
        cv2.putText(
            canvas,
            label,
            text_origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            label,
            text_origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 220, 255),
            1,
            cv2.LINE_AA,
        )
    return canvas


def _write_jpeg(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise CvPipelineError(f"无法编码证据图：{path.name}。")
    try:
        encoded.tofile(str(path))
    except OSError as error:
        raise CvPipelineError(f"无法写入证据图：{path.name}。") from error


def _rank_key(detection: dict[str, Any], settings: AuditSettings) -> tuple:
    risk = detection["class_name"] in settings.risk_classes
    return (
        0 if risk else 1,
        -float(detection["confidence"]),
        float(detection["timestamp_seconds"]),
        int(detection["frame_index"]),
    )


def _select_evidence_frames(
    frames: list[SampledFrame],
    detections: list[dict[str, Any]],
    settings: AuditSettings,
) -> list[int]:
    """Return ordered unique frame_index values for evidence JPEGs."""
    if not frames:
        raise CvPipelineError("没有可用于证据的采样帧。")

    if not detections:
        return [frames[0].frame_index]

    ordered = sorted(detections, key=lambda item: _rank_key(item, settings))
    selected: list[int] = []
    for detection in ordered:
        frame_index = int(detection["frame_index"])
        if frame_index not in selected:
            selected.append(frame_index)
        if len(selected) >= settings.min_evidence_frames:
            break
    if not selected:
        selected = [frames[0].frame_index]
    return selected


def _write_detections_csv(path: Path, detections: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DETECTION_FIELDS))
        writer.writeheader()
        for detection in detections:
            row = {
                "frame_index": detection["frame_index"],
                "timestamp_seconds": detection["timestamp_seconds"],
                "class_id": detection["class_id"],
                "class_name": detection["class_name"],
                "confidence": detection["confidence"],
                "bbox_xyxy": json.dumps(
                    detection["bbox_xyxy"],
                    ensure_ascii=False,
                ),
                "evidence_file": detection["evidence_file"],
            }
            writer.writerow(row)


def _build_zip(
    zip_path: Path,
    *,
    job_json: Path | None,
    report_path: Path,
    csv_path: Path,
    evidence_dir: Path,
    evidence_names: list[str],
) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if job_json is not None and job_json.is_file():
            archive.write(job_json, arcname="job.json")
        archive.write(report_path, arcname=report_path.name)
        archive.write(csv_path, arcname=csv_path.name)
        for name in evidence_names:
            file_path = evidence_dir / name
            if file_path.is_file():
                archive.write(file_path, arcname=f"evidence/{name}")


def analyze_asset(
    input_path: Path,
    evidence_dir: Path,
    result_dir: Path,
    settings: AuditSettings,
    detector: Detector,
) -> AnalysisReport:
    """Run sampling, detection, rules, evidence, and export artifacts."""
    evidence_dir = Path(evidence_dir)
    result_dir = Path(result_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    job_id = _job_id_from_dirs(evidence_dir, result_dir)
    frames = sample_media(
        Path(input_path),
        sample_interval_seconds=settings.sample_interval_seconds,
        max_sample_frames=settings.max_sample_frames,
    )

    detections: list[dict[str, Any]] = []
    per_frame: dict[int, list[dict[str, Any]]] = {}
    try:
        for sampled in frames:
            raw = detector.detect(
                sampled.image,
                confidence=settings.inference_confidence,
            )
            frame_detections: list[dict[str, Any]] = []
            for item in raw:
                detection = {
                    "frame_index": int(sampled.frame_index),
                    "timestamp_seconds": float(sampled.timestamp_seconds),
                    "class_id": int(item["class_id"]),
                    "class_name": str(item["class_name"]),
                    "confidence": float(item["confidence"]),
                    "bbox_xyxy": [float(v) for v in item["bbox_xyxy"]],
                    "evidence_file": "",
                }
                frame_detections.append(detection)
                detections.append(detection)
            per_frame[sampled.frame_index] = frame_detections
    except MediaDecodeError:
        raise
    except CvPipelineError:
        raise
    except Exception as error:
        raise CvPipelineError("检测推理过程失败。") from error

    decision = decide_audit(detections, len(frames), settings)
    evidence_indices = _select_evidence_frames(frames, detections, settings)
    frame_lookup = {frame.frame_index: frame for frame in frames}
    evidence_names: list[str] = []
    evidence_for_frame: dict[int, str] = {}

    for order, frame_index in enumerate(evidence_indices):
        sampled = frame_lookup[frame_index]
        filename = f"evidence_{order:03d}_f{frame_index}.jpg"
        annotated = _draw_detections(
            sampled.image,
            per_frame.get(frame_index, []),
        )
        _write_jpeg(evidence_dir / filename, annotated)
        evidence_names.append(filename)
        evidence_for_frame[frame_index] = filename

    default_evidence = evidence_names[0]
    for detection in detections:
        detection["evidence_file"] = evidence_for_frame.get(
            int(detection["frame_index"]),
            default_evidence,
        )

    detections = _json_native(detections)
    report = AnalysisReport(
        job_id=job_id,
        detections=detections,
        evidence_frames=list(evidence_names),
        rules=settings.to_dict(),
        auto_decision=decision,
        final_decision=decision,
        reviewer=None,
        note=(
            None
            if detections
            else "未发现规则目标"
        ),
        downloads={
            "json": "analysis_report.json",
            "csv": "detections.csv",
            "zip": "audit_package.zip",
        },
    )

    report_path = result_dir / "analysis_report.json"
    csv_path = result_dir / "detections.csv"
    zip_path = result_dir / "audit_package.zip"
    try:
        report_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _write_detections_csv(csv_path, detections)
        _build_zip(
            zip_path,
            job_json=result_dir.parent / "job.json",
            report_path=report_path,
            csv_path=csv_path,
            evidence_dir=evidence_dir,
            evidence_names=evidence_names,
        )
    except OSError as error:
        raise CvPipelineError("无法写入分析结果文件。") from error

    return report
