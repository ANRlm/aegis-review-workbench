"""Published API blueprint.

Only the health endpoint is implemented in the contract scaffold. Feature
owners add job routes against the interfaces documented in docs/API.md.
"""

from __future__ import annotations

import shutil

from flask import Blueprint, current_app, jsonify

from .config import AppConfig


api = Blueprint("api", __name__, url_prefix="/api")


@api.get("/health")
def health():
    config: AppConfig = current_app.config["AEGIS_CONFIG"]
    return jsonify(
        {
            "ok": True,
            "status": "ok",
            "model_ready": config.model_path.is_file(),
            "ffmpeg_ready": shutil.which(config.ffmpeg_binary) is not None,
            "storage_ready": config.outputs_dir.is_dir(),
        }
    )
