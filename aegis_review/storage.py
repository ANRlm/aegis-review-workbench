"""Small, reusable primitives for durable JSON task records."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(destination: Path, payload: dict[str, Any]) -> None:
    """Write JSON without exposing readers to a partially written document."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(destination)


def read_json(source: Path) -> dict[str, Any]:
    with Path(source).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {source}")
    return payload
