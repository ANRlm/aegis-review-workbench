from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from aegis_review.config import PROJECT_ROOT
from aegis_review.cv.classes import CLASS_NAMES, EXPECTED_LABEL_COUNTS
from aegis_review.cv.dataset import validate_dataset
from aegis_review.cv.exceptions import DatasetValidationError


def _copy_dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "dataset"
    shutil.copytree(PROJECT_ROOT / "dataset", destination)
    return destination


def test_real_dataset_passes_validation() -> None:
    summary = validate_dataset(PROJECT_ROOT / "dataset")
    assert summary["ok"] is True
    assert summary["splits"] == {
        "train": {"images": 96, "labels": 96},
        "val": {"images": 24, "labels": 24},
    }
    assert summary["label_counts"] == EXPECTED_LABEL_COUNTS
    assert summary["classes"] == list(CLASS_NAMES)
    assert summary["data_yaml_path"] == "dataset"
    payload = yaml.safe_load(
        (PROJECT_ROOT / "dataset" / "data.yaml").read_text(encoding="utf-8")
    )
    assert not Path(payload["path"]).is_absolute()
    assert "/workspace" not in str(payload["path"])


def test_data_yaml_paths_resolve_relative_to_project() -> None:
    dataset_dir = PROJECT_ROOT / "dataset"
    payload = yaml.safe_load((dataset_dir / "data.yaml").read_text(encoding="utf-8"))
    train_dir = dataset_dir / payload["train"]
    val_dir = dataset_dir / payload["val"]
    assert train_dir.is_dir()
    assert val_dir.is_dir()
    assert any(train_dir.iterdir())
    assert any(val_dir.iterdir())


def test_unpaired_image_label_fails(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    label = next((dataset / "labels" / "train").glob("*.txt"))
    label.unlink()
    with pytest.raises(DatasetValidationError, match="不配对"):
        validate_dataset(dataset)


def test_invalid_class_id_fails(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    label = next((dataset / "labels" / "train").glob("*.txt"))
    label.write_text("9 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="类别 ID"):
        validate_dataset(dataset)


def test_wrong_column_count_fails(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    label = next((dataset / "labels" / "train").glob("*.txt"))
    label.write_text("0 0.5 0.5 0.1\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="列数"):
        validate_dataset(dataset)


def test_non_numeric_coordinate_fails(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    label = next((dataset / "labels" / "train").glob("*.txt"))
    label.write_text("0 0.5 abc 0.1 0.1\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="坐标不是数值"):
        validate_dataset(dataset)


def test_coordinate_out_of_range_fails(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    label = next((dataset / "labels" / "train").glob("*.txt"))
    label.write_text("0 1.5 0.5 0.1 0.1\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="归一化坐标越界"):
        validate_dataset(dataset)


def test_empty_label_file_is_allowed_for_structure(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    label = next((dataset / "labels" / "train").glob("*.txt"))
    label.write_text("", encoding="utf-8")
    # Empty labels are structurally valid, but global instance counts change.
    with pytest.raises(DatasetValidationError, match="标签实例数不符"):
        validate_dataset(dataset)


def test_corrupt_image_fails(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    image = next((dataset / "images" / "train").iterdir())
    image.write_bytes(b"not-an-image")
    with pytest.raises(DatasetValidationError, match="损坏"):
        validate_dataset(dataset)


def test_wrong_split_count_fails(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    image = next((dataset / "images" / "val").iterdir())
    label = dataset / "labels" / "val" / f"{image.stem}.txt"
    image.unlink()
    label.unlink()
    with pytest.raises(DatasetValidationError, match="数量不符"):
        validate_dataset(dataset)


def test_wrong_class_order_fails(tmp_path: Path) -> None:
    dataset = _copy_dataset(tmp_path)
    (dataset / "data.yaml").write_text(
        """path: dataset
train: images/train
val: images/val
names:
  0: enemy
  1: player
  2: energy_orb
  3: treasure_chest
  4: health_potion
""",
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError, match="类别顺序不符"):
        validate_dataset(dataset)
