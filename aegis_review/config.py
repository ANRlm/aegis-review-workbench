"""Project-wide configuration and filesystem boundaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class AppConfig:
    project_root: Path = PROJECT_ROOT
    testing: bool = False
    max_content_length: int = 200 * 1024 * 1024
    ffmpeg_binary: str = "ffmpeg"

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", Path(self.project_root).resolve())
        if self.max_content_length <= 0:
            raise ValueError("max_content_length must be positive")

    @property
    def outputs_dir(self) -> Path:
        return self.project_root / "outputs"

    @property
    def models_dir(self) -> Path:
        return self.project_root / "models"

    @property
    def model_path(self) -> Path:
        if self.testing:
            return self.models_dir / "aegis_game_best.pt"
        configured = os.getenv("AEGIS_MODEL_PATH")
        if configured:
            return Path(configured).expanduser().resolve()
        return self.models_dir / "aegis_game_best.pt"

    def ensure_directories(self) -> None:
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
