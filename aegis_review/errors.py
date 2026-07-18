"""Consistent JSON error responses for the public API."""

from __future__ import annotations

from flask import jsonify


def error_response(code: str, message: str, status: int):
    return (
        jsonify(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                },
            }
        ),
        status,
    )


def register_api_error_handlers(api_blueprint):
    """Register exception-to-JSON-error mappings on the API blueprint."""
    from flask import current_app
    from .service import (
        ArtifactNotFoundError,
        InvalidStatusTransition,
        JobBusyError,
        JobServiceError,
    )
    from .validation import ValidationError

    @api_blueprint.errorhandler(JobServiceError)
    def handle_service_error(error):
        if isinstance(error, (JobBusyError, InvalidStatusTransition)):
            msg = str(error)
            return error_response("job_busy", msg, 409)
        if isinstance(error, ArtifactNotFoundError):
            msg = str(error)
            return error_response("artifact_not_found", msg, 404)
        msg = str(error)
        if "\u4e0d\u5b58\u5728" in msg:
            return error_response("job_not_found", "\u4efb\u52a1\u4e0d\u5b58\u5728\u3002", 404)
        current_app.logger.error(str(error))
        return error_response("internal_error", "\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef\u3002", 500)

    @api_blueprint.errorhandler(ValidationError)
    def handle_validation_error(error):
        return error_response("invalid_request", str(error), 400)

    @api_blueprint.errorhandler(ValueError)
    def handle_value_error(error):
        return error_response("invalid_request", str(error), 400)

    @api_blueprint.errorhandler(404)
    def handle_api_not_found(error):
        return error_response("not_found", "\u8bf7\u6c42\u7684\u63a5\u53e3\u4e0d\u5b58\u5728\u3002", 404)
