#!/usr/bin/env python
"""Deterministic Day08 YOLO fine-tune entrypoint (CPU by default)."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aegis_review.config import PROJECT_ROOT
from aegis_review.cv.classes import CLASS_NAMES

DEFAULT_SEED = 20260718
DEFAULT_EPOCHS = 30
DEFAULT_IMGSZ = 640
DEFAULT_BATCH = 2
RUN_NAME = "day08_game_audit"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def train(
    *,
    project_root: Path = PROJECT_ROOT,
    epochs: int = DEFAULT_EPOCHS,
    imgsz: int = DEFAULT_IMGSZ,
    batch: int = DEFAULT_BATCH,
    device: str = "cpu",
    seed: int = DEFAULT_SEED,
    weights: Path | None = None,
) -> dict[str, object]:
    """Train YOLO11n on the migrated dataset and publish evidence artifacts."""
    project_root = Path(project_root)
    dataset_yaml = project_root / "dataset" / "data.yaml"
    init_weights = Path(weights) if weights else project_root / "models" / "yolo11n.pt"
    if not dataset_yaml.is_file():
        raise FileNotFoundError(f"missing dataset yaml: {dataset_yaml}")
    if not init_weights.is_file():
        raise FileNotFoundError(f"missing init weights: {init_weights}")

    runs_root = project_root / "training_runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    evidence_dir = project_root / "training_evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    models_dir = project_root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO

    model = YOLO(str(init_weights))
    started = time.time()
    results = model.train(
        data=str(dataset_yaml),
        epochs=int(epochs),
        imgsz=int(imgsz),
        batch=int(batch),
        device=device,
        seed=int(seed),
        project=str(runs_root),
        name=RUN_NAME,
        exist_ok=True,
        pretrained=True,
        workers=0,
        plots=True,
        deterministic=True,
    )
    elapsed = time.time() - started

    run_dir = Path(results.save_dir)
    best_src = run_dir / "weights" / "best.pt"
    if not best_src.is_file():
        raise FileNotFoundError(f"training did not produce best.pt under {run_dir}")

    best_dst = models_dir / "aegis_game_best.pt"
    shutil.copy2(best_src, best_dst)
    digest = _sha256(best_dst)

    results_csv = run_dir / "results.csv"
    if results_csv.is_file():
        shutil.copy2(results_csv, evidence_dir / "results.csv")

    for curve_name in (
        "results.png",
        "BoxPR_curve.png",
        "confusion_matrix.png",
    ):
        source = run_dir / curve_name
        if source.is_file():
            shutil.copy2(source, evidence_dir / curve_name)

    metrics = {}
    if hasattr(results, "results_dict") and isinstance(results.results_dict, dict):
        metrics = {
            key: float(value)
            for key, value in results.results_dict.items()
            if isinstance(value, (int, float))
        }

    summary = {
        "classes": list(CLASS_NAMES),
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "device": device,
        "seed": seed,
        "init_weights": str(init_weights.relative_to(project_root)),
        "best_weights": str(best_dst.relative_to(project_root)),
        "sha256": digest,
        "elapsed_seconds": round(elapsed, 2),
        "run_dir": str(run_dir.relative_to(project_root)),
        "metrics": metrics,
    }
    (evidence_dir / "train_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (evidence_dir / "aegis_game_best.sha256").write_text(
        f"{digest}  models/aegis_game_best.pt\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--weights",
        type=Path,
        default=None,
        help="Initialization weights (default: models/yolo11n.pt)",
    )
    args = parser.parse_args(argv)
    summary = train(
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        seed=args.seed,
        weights=args.weights,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
