"""Aegis Review Flask application factory."""

from __future__ import annotations

from flask import Flask, render_template, request

from .api import api
from .config import AppConfig
from .errors import error_response


def create_app(config: AppConfig | None = None) -> Flask:
    """Create the Flask app from an explicit, testable project configuration."""
    app_config = config or AppConfig()
    app_config.ensure_directories()

    app = Flask(
        __name__,
        template_folder=str(app_config.project_root / "templates"),
        static_folder=str(app_config.project_root / "static"),
    )
    app.config.update(
        AEGIS_CONFIG=app_config,
        MAX_CONTENT_LENGTH=app_config.max_content_length,
        TESTING=app_config.testing,
        JSON_AS_ASCII=False,
    )
    app.register_blueprint(api)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.errorhandler(404)
    def not_found(_error: Exception):
        if request.path.startswith("/api/"):
            return error_response("not_found", "请求的接口不存在。", 404)
        return render_template("index.html"), 404

    @app.errorhandler(413)
    def payload_too_large(_error: Exception):
        return error_response(
            "payload_too_large",
            "上传文件不能超过 200MB。",
            413,
        )

    return app


__all__ = ["create_app"]
