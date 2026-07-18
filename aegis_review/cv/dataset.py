"""Validate the five-class YOLO dataset used by Aegis Review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from aegis_review.config import PROJECT_ROOT
from aegis_review.cv.classes import (
    CLASS_NAMES,
    EXPECTED_LABEL_COUNTS,
    EXPECTED_TRAIN_IMAGES,
    EXPECTED_VAL_IMAGES,
)
from aegis_review.cv.exceptions import DatasetValidationError

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DatasetValidationError("data.yaml 必须是映射对象。")
    return payload


def _image_stem_map(directory: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.stem in mapping:
            raise DatasetValidationError(
                f"重复图片主名：{directory.name}/{path.stem}"
            )
        mapping[path.stem] = path
    return mapping


def _validate_image_readable(path: Path) -> None:
    data = path.read_bytes()
    if not data:
        raise DatasetValidationError(f"图片为空：{path}")
    # Minimal signature checks without requiring OpenCV at import time.
    head = data[:16]
    jpeg = head.startswith(b"\xff\xd8")
    png = head.startswith(b"\x89PNG\r\n\x1a\n")
    if not (jpeg or png):
        raise DatasetValidationError(f"图片损坏或格式无法识别：{path}")


def _validate_label_file(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    class_ids: list[int] = []
    if text.strip() == "":
        return class_ids
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise DatasetValidationError(
                f"标签列数错误：{path.name}:{line_number}"
            )
        class_token, *coords = parts
        try:
            class_id = int(class_token)
        except ValueError as error:
            raise DatasetValidationError(
                f"类别 ID 不是整数：{path.name}:{line_number}"
            ) from error
        if class_id < 0 or class_id > 4:
            raise DatasetValidationError(
                f"类别 ID 越界：{path.name}:{line_number} -> {class_id}"
            )
        try:
            values = [float(token) for token in coords]
        except ValueError as error:
            raise DatasetValidationError(
                f"坐标不是数值：{path.name}:{line_number}"
            ) from error
        if any(value < 0.0 or value > 1.0 for value in values):
            raise DatasetValidationError(
                f"归一化坐标越界：{path.name}:{line_number}"
            )
        class_ids.append(class_id)
    return class_ids


def validate_dataset(dataset_dir: Path) -> dict[str, object]:
    """Validate pairing, classes, coordinates, and expected split sizes."""
    dataset_dir = Path(dataset_dir)
    data_yaml = dataset_dir / "data.yaml"
    if not data_yaml.is_file():
        raise DatasetValidationError("缺少 data.yaml。")

    payload = _load_yaml(data_yaml)
    path_value = payload.get("path")
    if not isinstance(path_value, str) or Path(path_value).is_absolute():
        raise DatasetValidationError(
            "data.yaml 的 path 必须是项目内相对路径，不能是绝对路径。"
        )
    if "/workspace" in path_value.replace("\\", "/"):
        raise DatasetValidationError(
            "data.yaml 不得包含 /workspace 绝对路径。"
        )

    names = payload.get("names")
    if isinstance(names, dict):
        ordered = [str(names[index]) for index in range(len(names))]
    elif isinstance(names, list):
        ordered = [str(name) for name in names]
    else:
        raise DatasetValidationError("data.yaml names 字段无效。")
    if tuple(ordered) != CLASS_NAMES:
        raise DatasetValidationError(
            f"类别顺序不符：期望 {list(CLASS_NAMES)}，实际 {ordered}"
        )

    label_counts = {name: 0 for name in CLASS_NAMES}
    summary_splits: dict[str, dict[str, int]] = {}

    for split, expected in (
        ("train", EXPECTED_TRAIN_IMAGES),
        ("val", EXPECTED_VAL_IMAGES),
    ):
        image_dir = dataset_dir / "images" / split
        label_dir = dataset_dir / "labels" / split
        if not image_dir.is_dir() or not label_dir.is_dir():
            raise DatasetValidationError(f"缺少 {split} 图片或标签目录。")

        images = _image_stem_map(image_dir)
        labels = {
            path.stem: path
            for path in sorted(label_dir.glob("*.txt"))
            if path.is_file()
        }
        if set(images) != set(labels):
            missing_labels = sorted(set(images) - set(labels))
            missing_images = sorted(set(labels) - set(images))
            raise DatasetValidationError(
                "图片与标签不配对："
                f"missing_labels={missing_labels[:5]} "
                f"missing_images={missing_images[:5]}"
            )
        if len(images) != expected:
            raise DatasetValidationError(
                f"{split} 数量不符：期望 {expected}，实际 {len(images)}"
            )

        for stem, image_path in images.items():
            _validate_image_readable(image_path)
            class_ids = _validate_label_file(labels[stem])
            for class_id in class_ids:
                label_counts[CLASS_NAMES[class_id]] += 1

        summary_splits[split] = {
            "images": len(images),
            "labels": len(labels),
        }

    if label_counts != EXPECTED_LABEL_COUNTS:
        raise DatasetValidationError(
            f"标签实例数不符：期望 {EXPECTED_LABEL_COUNTS}，实际 {label_counts}"
        )

    return {
        "ok": True,
        "dataset_dir": str(dataset_dir),
        "classes": list(CLASS_NAMES),
        "splits": summary_splits,
        "label_counts": label_counts,
        "data_yaml_path": path_value,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "dataset",
        help="Dataset directory containing data.yaml",
    )
    args = parser.parse_args(argv)
    try:
        summary = validate_dataset(args.dataset)
    except DatasetValidationError as error:
        print(f"VALIDATION FAILED: {error}", file=sys.stderr)
        return 1
    print("VALIDATION OK")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
