"""Consistent JSON error responses and exception-to-HTTP mappings."""
from __future__ import annotations
from flask import jsonify


def error_response(code: str, message: str, status: int):
    return (
        jsonify({
            "ok": False,
            "error": {"code": code, "message": message},
        }),
        status,
    )


def register_api_error_handlers(api_blueprint):
    """Register exception-to-JSON-error mappings on the API blueprint."""
    from werkzeug.exceptions import HTTPException
    from werkzeug.exceptions import BadRequest, HTTPException, MethodNotAllowed, NotFound, RequestEntityTooLarge
    from .service import (
        ArtifactNotFoundError, InvalidStatusTransition,
        JobBusyError, JobExecutionError, JobServiceError,
    )
    from .storage import AssetTooLargeError, InvalidJobIdError, JobNotFoundError
    from .validation import MediaTooLargeError, ValidationError

    # -- Specific HTTPException handlers (blueprint-level) --

    @api_blueprint.errorhandler(BadRequest)
    def handle_bad_request(error):
        return error_response("invalid_request", "\u8bf7\u6c42\u53c2\u6570\u9519\u8bef\u3002", 400)

    @api_blueprint.errorhandler(NotFound)
    def handle_not_found(error):
        return error_response("not_found", "\u8bf7\u6c42\u7684\u63a5\u53e3\u4e0d\u5b58\u5728\u3002", 404)

    @api_blueprint.errorhandler(MethodNotAllowed)
    def handle_method_not_allowed(error):
        return error_response("invalid_request", "\u8bf7\u6c42\u65b9\u6cd5\u4e0d\u5141\u8bb8\u3002", 405)

    @api_blueprint.errorhandler(RequestEntityTooLarge)
    def handle_entity_too_large(error):
        return error_response("payload_too_large", "\u4e0a\u4f20\u6587\u4ef6\u4e0d\u80fd\u8d85\u8fc7 200MB\u3002", 413)

    @api_blueprint.errorhandler(HTTPException)
    def handle_other_http_exception(error):
        code = error.code if hasattr(error, "code") else 500
        if 400 <= code < 500:
            return error_response("invalid_request", "\u8bf7\u6c42\u9519\u8bef\u3002", code)
        return error_response("internal_error", "\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef\u3002", 500)

    # -- Service exceptions --

    @api_blueprint.errorhandler(InvalidStatusTransition)
    def handle_invalid_status(error):
        return error_response("invalid_status", str(error), 409)

    @api_blueprint.errorhandler(JobBusyError)
    def handle_busy(error):
        return error_response("job_busy", "\u4efb\u52a1\u6b63\u5728\u6267\u884c\uff0c\u6682\u65f6\u4e0d\u80fd\u64cd\u4f5c\u3002", 409)

    @api_blueprint.errorhandler(ArtifactNotFoundError)
    def handle_artifact_not_found(error):
        return error_response("artifact_not_found", "\u4efb\u52a1\u4ea7\u7269\u4e0d\u5b58\u5728\u3002", 404)

    @api_blueprint.errorhandler(JobExecutionError)
    def handle_execution_error(error):
        return error_response("internal_error", "\u540e\u53f0\u4efb\u52a1\u63d0\u4ea4\u5931\u8d25\u3002", 500)

    @api_blueprint.errorhandler(JobServiceError)
    def handle_generic_service_error(error):
        from flask import current_app
        current_app.logger.exception("Unhandled service error: %s", error)
        return error_response("internal_error", "\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef\u3002", 500)

    # -- Storage exceptions --

    @api_blueprint.errorhandler(JobNotFoundError)
    def handle_job_not_found(error):
        return error_response("job_not_found", "\u4efb\u52a1\u4e0d\u5b58\u5728\u3002", 404)

    @api_blueprint.errorhandler(InvalidJobIdError)
    def handle_invalid_job_id(error):
        return error_response("job_not_found", "\u4efb\u52a1\u7f16\u53f7\u683c\u5f0f\u9519\u8bef\u3002", 404)

    @api_blueprint.errorhandler(AssetTooLargeError)
    def handle_asset_too_large(error):
        return error_response("payload_too_large", "\u4e0a\u4f20\u6587\u4ef6\u4e0d\u80fd\u8d85\u8fc7 200MB\u3002", 413)

    # -- Validation exceptions --

    @api_blueprint.errorhandler(MediaTooLargeError)
    def handle_media_too_large(error):
        return error_response("payload_too_large", "\u4e0a\u4f20\u6587\u4ef6\u4e0d\u80fd\u8d85\u8fc7 200MB\u3002", 413)

    @api_blueprint.errorhandler(ValidationError)
    def handle_validation_error(error):
        return error_response("invalid_request", str(error), 400)

    @api_blueprint.errorhandler(ValueError)
    def handle_value_error(error):
        return error_response("invalid_request", str(error), 400)

    # -- Catch-all (non-HTTP only) --

    @api_blueprint.errorhandler(Exception)
    def handle_unknown_exception(error):
        from flask import current_app
        current_app.logger.exception("Unhandled exception: %s", error)
        return error_response("internal_error", "\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef\u3002", 500)

    # -- Generic blueprint 404 (fallback for unmatched API routes) --

    @api_blueprint.errorhandler(404)
    def handle_api_not_found(error):
        return error_response("not_found", "\u8bf7\u6c42\u7684\u63a5\u53e3\u4e0d\u5b58\u5728\u3002", 404)
