"""Published API blueprint with all job routes."""
from __future__ import annotations
import shutil
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request, send_file
from .config import AppConfig
from .domain import AssetInput, MediaType
from .errors import error_response, register_api_error_handlers
from .validation import (
    ValidationError, decode_image_stream, decode_video_stream,
    MediaTooLargeError, detect_media_type, parse_settings, validate_project_name,
)

api = Blueprint("api", __name__, url_prefix="/api")

# -- Serialization helpers --


def _serialize_job(job: dict) -> dict:
    """Make a safe HTTP copy of a job dict (no asset_file, add asset_url)."""
    result = dict(job)
    result.pop("asset_file", None)
    asset_fn = job.get("asset_file")
    if asset_fn:
        result["asset_url"] = f"/api/jobs/{job['job_id']}/artifacts/{asset_fn}"
    return result


def _serialize_report(report: dict, job_id: str) -> dict:
    """Make a safe HTTP copy of a report (downloads URLs)."""
    result = dict(report)
    downloads = result.get("downloads")
    if isinstance(downloads, dict):
        result["downloads"] = {
            label: f"/api/jobs/{job_id}/artifacts/{filename}"
            for label, filename in downloads.items()
        }
    return result


def _service():
    return current_app.extensions["aegis_job_service"]


# -- Routes --


@api.get("/health")
def health():
    config: AppConfig = current_app.config["AEGIS_CONFIG"]
    return jsonify({
        "ok": True, "status": "ok",
        "model_ready": config.model_path.is_file(),
        "ffmpeg_ready": shutil.which(config.ffmpeg_binary) is not None,
        "storage_ready": config.outputs_dir.is_dir(),
    })


@api.post("/jobs")
def create_job():
    assets = request.files.getlist("asset")
    if len(assets) != 1:
        return error_response("invalid_asset", "\u8bf7\u4e0a\u4f20\u4e14\u53ea\u80fd\u4e0a\u4f20\u4e00\u4e2a\u7d20\u6750\u6587\u4ef6\u3002", 400)
    asset_file = assets[0]
    original_name = asset_file.filename
    if not original_name or not original_name.strip():
        return error_response("invalid_asset", "\u7d20\u6750\u6587\u4ef6\u540d\u4e3a\u7a7a\u3002", 400)
    dot = original_name.rfind(".")
    if dot <= 0 or dot == len(original_name) - 1:
        return error_response("invalid_asset", "\u4e0d\u652f\u6301\u7684\u6587\u4ef6\u6269\u5c55\u540d\u3002", 400)
    extension = original_name[dot + 1:].lower()
    project_name_raw = request.form.get("project_name")
    if not project_name_raw:
        return error_response("invalid_request", "\u7f3a\u5c11 project_name \u5b57\u6bb5\u3002", 400)
    try:
        valid_name = validate_project_name(project_name_raw)
    except ValidationError as exc:
        return error_response("invalid_request", str(exc), 400)
    try:
        media_type = detect_media_type(extension)
    except ValidationError as exc:
        return error_response("invalid_asset", str(exc), 400)
    stream = asset_file.stream
    try:
        stream.seek(0, 2)
        size = stream.tell()
    except OSError:
        return error_response("invalid_asset", "\u65e0\u6cd5\u8bfb\u53d6\u4e0a\u4f20\u6587\u4ef6\u3002", 400)
    if size == 0:
        return error_response("invalid_asset", "\u4e0a\u4f20\u6587\u4ef6\u4e3a\u7a7a\u3002", 400)
    stream.seek(0)
    config: AppConfig = current_app.config["AEGIS_CONFIG"]
    if size > config.max_content_length:
        return error_response("payload_too_large", "\u4e0a\u4f20\u6587\u4ef6\u4e0d\u80fd\u8d85\u8fc7 200MB\u3002", 413)
    if media_type is MediaType.IMAGE:
        if not decode_image_stream(stream):
            return error_response("invalid_asset", "\u4e0a\u4f20\u6587\u4ef6\u65e0\u6cd5\u89e3\u7801\u3002", 400)
    elif media_type is MediaType.VIDEO:
        try:
            if not decode_video_stream(stream, config.max_content_length, suffix=f".{extension}"):
                return error_response("invalid_asset", "\u4e0a\u4f20\u6587\u4ef6\u65e0\u6cd5\u89e3\u7801\u3002", 400)
        except MediaTooLargeError:
            return error_response("payload_too_large", "\u4e0a\u4f20\u6587\u4ef6\u4e0d\u80fd\u8d85\u8fc7 200MB\u3002", 413)
    settings_raw = request.form.get("settings")
    try:
        settings = parse_settings(settings_raw)
    except ValidationError as exc:
        return error_response("invalid_settings", str(exc), 400)
    try:
        asset_input = AssetInput(
            original_name=original_name,
            extension=extension,
            media_type=media_type,
            stream=stream,
        )
    except (ValueError, TypeError) as exc:
        return error_response("invalid_asset", str(exc), 400)
    job = _service().create_job(asset_input, valid_name, settings)
    return jsonify({"ok": True, "job": {"job_id": job["job_id"], "status": job["status"]}}), 201


@api.post("/jobs/<job_id>/analyze")
def analyze_job(job_id: str):
    result = _service().enqueue_analysis(job_id)
    return jsonify({"ok": True, "job_id": result["job_id"], "status": result["status"]}), 202


@api.get("/jobs")
def list_jobs():
    status = request.args.get("status")
    if status is not None:
        from aegis_review.domain import JobStatus
        try:
            JobStatus(status)
        except ValueError:
            return error_response("invalid_request", "\u65e0\u6548\u7684 status \u53c2\u6570\u3002", 400)
    jobs = _service().list_jobs(status=status)
    return jsonify({"ok": True, "jobs": [_serialize_job(j) for j in jobs], "total": len(jobs)})


@api.get("/jobs/<job_id>")
def get_job(job_id: str):
    job = _service().get_job(job_id)
    return jsonify({"ok": True, "job": _serialize_job(job)})


@api.delete("/jobs/<job_id>")
def delete_job(job_id: str):
    _service().delete_job(job_id)
    return jsonify({"ok": True, "deleted_job_id": job_id})


@api.patch("/jobs/<job_id>/review")
def review_job(job_id: str):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("invalid_request", "\u8bf7\u63d0\u4f9b JSON \u5bf9\u8c61\u8bf7\u6c42\u4f53\u3002", 400)
    decision = body.get("decision")
    reviewer = body.get("reviewer")
    note = body.get("note")
    if decision not in ("pass", "review", "reject"):
        return error_response("invalid_request", "decision \u5fc5\u987b\u662f pass/review/reject\u3002", 400)
    if not reviewer or not isinstance(reviewer, str) or not reviewer.strip():
        return error_response("invalid_request", "reviewer \u4e0d\u80fd\u4e3a\u7a7a\u3002", 400)
    if len(reviewer.strip()) > 40:
        return error_response("invalid_request", "reviewer \u4e0d\u80fd\u8d85\u8fc7 40 \u4e2a\u5b57\u7b26\u3002", 400)
    if note is not None and (not isinstance(note, str) or len(note) > 500):
        return error_response("invalid_request", "note \u4e0d\u80fd\u8d85\u8fc7 500 \u5b57\u3002", 400)
    report = _service().review_job(job_id, decision, reviewer.strip(), note)
    return jsonify({"ok": True, "report": _serialize_report(report, job_id)})


@api.get("/jobs/<job_id>/report")
def get_report(job_id: str):
    report = _service().get_report(job_id)
    return jsonify({"ok": True, "report": _serialize_report(report, job_id)})


_INLINE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "gif", "mp4", "mov", "webm"})


@api.get("/jobs/<job_id>/artifacts/<filename>")
def get_artifact(job_id: str, filename: str):
    filepath = _service().resolve_artifact(job_id, filename)
    is_inline = Path(filename).suffix.lstrip(".").lower() in _INLINE_EXTENSIONS
    return send_file(str(filepath), as_attachment=not is_inline, download_name=Path(filename).name)


@api.get("/stats")
def stats():
    data = _service().stats()
    return jsonify({"ok": True, "stats": data})


register_api_error_handlers(api)
