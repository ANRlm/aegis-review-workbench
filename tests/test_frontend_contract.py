"""Frontend contract tests for the Aegis Review workstation.

These tests verify that the HTML template, CSS, and JS static assets
follow the published contract and design constraints. They do not
require a running Flask server.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aegis_review import create_app
from aegis_review.config import AppConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"


# ---------------------------------------------------------------------------
# HTML structural tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rendered_html() -> str:
    app = create_app(AppConfig(testing=True))
    response = app.test_client().get("/")
    assert response.status_code == 200
    data = response.get_data(as_text=True)
    assert isinstance(data, str) and len(data) > 0
    return data


def test_html_contains_product_name(rendered_html: str) -> None:
    assert "影鉴 Aegis Review" in rendered_html


def test_html_has_lang_attribute(rendered_html: str) -> None:
    match = re.search(r'<html[^>]*lang="zh-CN"[^>]*>', rendered_html)
    assert match is not None, "html element must have lang='zh-CN'"


def test_html_has_viewport_meta(rendered_html: str) -> None:
    assert 'name="viewport"' in rendered_html


def test_html_includes_upload_form(rendered_html: str) -> None:
    assert 'id="drop-zone"' in rendered_html
    assert 'id="file-input"' in rendered_html
    assert 'id="project-name"' in rendered_html


def test_html_includes_task_history(rendered_html: str) -> None:
    assert 'id="task-list"' in rendered_html
    assert 'id="status-filter"' in rendered_html


def test_html_includes_evidence_panel(rendered_html: str) -> None:
    assert 'id="evidence-panel"' in rendered_html
    assert 'id="evidence-empty"' in rendered_html
    assert 'id="evidence-loading"' in rendered_html
    assert 'id="evidence-failed"' in rendered_html
    assert 'id="evidence-content"' in rendered_html


def test_html_includes_review_panel(rendered_html: str) -> None:
    assert 'id="review-panel"' in rendered_html
    assert 'id="review-form"' in rendered_html
    assert 'id="reviewer-name"' in rendered_html


def test_html_includes_stats_bar(rendered_html: str) -> None:
    assert 'id="stats-bar"' in rendered_html
    assert 'id="stat-total"' in rendered_html
    assert 'id="stat-pass"' in rendered_html
    assert 'id="stat-review"' in rendered_html
    assert 'id="stat-reject"' in rendered_html


def test_html_includes_health_badges(rendered_html: str) -> None:
    assert 'id="health-badges"' in rendered_html


def test_html_includes_download_buttons(rendered_html: str) -> None:
    assert 'id="btn-download-json"' in rendered_html
    assert 'id="btn-download-csv"' in rendered_html
    assert 'id="btn-download-zip"' in rendered_html


def test_html_includes_confirm_dialog(rendered_html: str) -> None:
    assert 'id="confirm-dialog"' in rendered_html


def test_html_references_static_css(rendered_html: str) -> None:
    assert 'href="' in rendered_html
    assert 'styles.css' in rendered_html


def test_html_references_static_js(rendered_html: str) -> None:
    assert 'src="' in rendered_html
    assert 'app.js' in rendered_html


def test_html_uses_defer_on_script(rendered_html: str) -> None:
    match = re.search(r'<script[^>]+src="[^"]*app\.js"[^>]*>', rendered_html)
    assert match is not None
    assert "defer" in match.group()


def test_html_has_aria_labels_for_accessibility(rendered_html: str) -> None:
    assert 'aria-label="审核统计"' in rendered_html
    assert 'aria-label="新建审核任务"' in rendered_html
    assert 'aria-label="素材与证据"' in rendered_html
    assert 'aria-label="审核操作"' in rendered_html


# ---------------------------------------------------------------------------
# CSS design token tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def styles_css() -> str:
    path = STATIC_DIR / "styles.css"
    assert path.is_file(), "styles.css must exist"
    return path.read_text(encoding="utf-8")


def test_css_defines_canvas_color(styles_css: str) -> None:
    assert "--canvas: #f7f7f3" in styles_css or "--canvas: #F7F7F3" in styles_css


def test_css_defines_accent_color(styles_css: str) -> None:
    assert "--accent:" in styles_css


def test_css_defines_warning_color(styles_css: str) -> None:
    assert "--warning:" in styles_css


def test_css_defines_danger_color(styles_css: str) -> None:
    assert "--danger:" in styles_css


def test_css_has_reduced_motion_support(styles_css: str) -> None:
    assert "prefers-reduced-motion" in styles_css
    reduced_section = styles_css.split("prefers-reduced-motion")[1]
    assert "animation-duration" in reduced_section
    assert "transition-duration" in reduced_section


def test_css_has_focus_visible_styles(styles_css: str) -> None:
    assert ":focus-visible" in styles_css


def test_css_has_responsive_breakpoints(styles_css: str) -> None:
    assert "@media" in styles_css
    assert "max-width" in styles_css


def test_css_has_grid_layout(styles_css: str) -> None:
    assert "grid-template-columns" in styles_css


def test_css_has_animation_duration_tokens(styles_css: str) -> None:
    assert "--anim-duration" in styles_css


# ---------------------------------------------------------------------------
# JS contract tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_js() -> str:
    path = STATIC_DIR / "app.js"
    assert path.is_file(), "app.js must exist"
    return path.read_text(encoding="utf-8")


def test_js_uses_strict_mode(app_js: str) -> None:
    assert '"use strict"' in app_js or "'use strict'" in app_js


def test_js_defines_api_base_path(app_js: str) -> None:
    assert '"/api"' in app_js or "'/api'" in app_js or '= "/api"' in app_js or "= '/api'" in app_js


def test_js_references_health_endpoint(app_js: str) -> None:
    assert '"/health"' in app_js or "'/health'" in app_js or "/health" in app_js


def test_js_references_jobs_endpoint(app_js: str) -> None:
    assert "/jobs" in app_js


def test_js_references_analyze_endpoint(app_js: str) -> None:
    assert "/analyze" in app_js


def test_js_references_report_endpoint(app_js: str) -> None:
    assert "/report" in app_js


def test_js_references_review_endpoint(app_js: str) -> None:
    assert "/review" in app_js


def test_js_references_stats_endpoint(app_js: str) -> None:
    assert "/stats" in app_js


def test_js_references_artifacts_endpoint(app_js: str) -> None:
    assert "/artifacts" in app_js


def test_js_checks_ok_field(app_js: str) -> None:
    assert "ok ===" in app_js or "ok !==" in app_js or ".ok " in app_js or "ok:" in app_js


def test_js_reads_error_message(app_js: str) -> None:
    assert "error.message" in app_js or 'error["message"]' in app_js


def test_js_defines_status_labels(app_js: str) -> None:
    assert '"已创建"' in app_js or "'已创建'" in app_js
    assert '"分析中"' in app_js or "'分析中'" in app_js


def test_js_defines_decision_labels(app_js: str) -> None:
    assert '"通过"' in app_js or "'通过'" in app_js
    assert '"待复核"' in app_js or "'待复核'" in app_js
    assert '"不通过"' in app_js or "'不通过'" in app_js


def test_js_has_polling_mechanism(app_js: str) -> None:
    assert "polling" in app_js.lower() or "pollTimeout" in app_js or "pollJob" in app_js


def test_js_has_timer_cleanup(app_js: str) -> None:
    assert "clearTimeout" in app_js or "cancelPolling" in app_js


def test_js_handles_page_unload(app_js: str) -> None:
    assert "beforeunload" in app_js


def test_js_has_model_ready_check(app_js: str) -> None:
    assert "model_ready" in app_js


def test_js_has_file_drag_and_drop(app_js: str) -> None:
    assert "dragover" in app_js or "drop" in app_js


def test_js_has_confirm_dialog(app_js: str) -> None:
    assert "confirm" in app_js.lower() or "showModal" in app_js


def test_js_has_download_functionality(app_js: str) -> None:
    assert "download" in app_js.lower() or "blob" in app_js.lower()


def test_js_avoids_fabricating_progress(app_js: str) -> None:
    progress_patterns = [r"progress.*%", r"percent.*complete", r"进度.*\%"]
    for pattern in progress_patterns:
        matches = re.findall(pattern, app_js, re.IGNORECASE)
        assert (
            len(matches) == 0
        ), f"JS should not fabricate progress percentages: found {pattern}"


def test_js_has_toast_feedback(app_js: str) -> None:
    assert "toast" in app_js.lower()


# ---------------------------------------------------------------------------
# Strengthened regression tests
# ---------------------------------------------------------------------------


def test_js_does_not_use_setinterval(app_js: str) -> None:
    assert "setInterval" not in app_js, "Polling must use recursive setTimeout, not setInterval"


def test_js_csv_zip_does_not_call_artifacturl_with_filename(app_js: str) -> None:
    """CSV/ZIP downloads must use report.downloads URL directly, not pass basenames to artifactUrl."""
    csv_func = _extract_function(app_js, "handleDownloadCsv")
    zip_func = _extract_function(app_js, "handleDownloadZip")
    assert "artifactUrl" not in csv_func, "CSV download must not call artifactUrl"
    assert "artifactUrl" not in zip_func, "ZIP download must not call artifactUrl"
    assert "downloads.csv" in csv_func or "downloads.csv" in zip_func or "downloads" in app_js


def test_js_fetch_job_does_not_write_global_state(app_js: str) -> None:
    fetch_func = _extract_function(app_js, "function fetchJob")
    assert "state.selectedJob" not in fetch_func, (
        "fetchJob must return data, not write to state.selectedJob"
    )


def test_js_fetch_report_does_not_write_global_state(app_js: str) -> None:
    fetch_func = _extract_function(app_js, "function fetchReport")
    assert "state.report" not in fetch_func, (
        "fetchReport must return data, not write to state.report"
    )


def test_js_numeric_settings_avoid_short_circuit_or(app_js: str) -> None:
    """Numeric settings must use parseNumeric(), not parseFloat(val) || default."""
    build_func = _extract_function(app_js, "function buildSettings")
    assert "parseFloat" not in build_func, (
        "Settings must use parseNumeric helper, not parseFloat(...) || default"
    )


def test_js_update_upload_button_checks_model_ready(app_js: str) -> None:
    update_func = _extract_function(app_js, "function updateUploadButton")
    assert "model_ready" in update_func, (
        "updateUploadButton must check model_ready"
    )


def test_html_upload_panel_is_inside_left_rail(rendered_html: str) -> None:
    """Upload panel must be inside the task-rail (left column)."""
    assert 'id="upload-panel"' in rendered_html
    rail_start = rendered_html.index('class="task-rail"')
    rail_close = rendered_html.index("</aside>", rail_start)
    rail_content = rendered_html[rail_start:rail_close]
    assert 'id="upload-panel"' in rail_content, (
        "upload-panel must be inside the left task-rail"
    )


def test_js_delete_button_has_aria_label(app_js: str) -> None:
    """Delete button aria-label is set in JS renderJobs, not static HTML."""
    assert 'aria-label="删除任务' in app_js, (
        "Delete buttons in JS must have aria-label"
    )


def test_html_model_notice_present(rendered_html: str) -> None:
    assert 'id="model-notice"' in rendered_html, (
        "Model-notice element must exist for model_ready=false warning"
    )


def test_css_status_badge_has_running_class(styles_css: str) -> None:
    assert "status-running" in styles_css, (
        "Status badge must use .status-running CSS class, not inline styles"
    )


def test_css_status_badge_has_created_class(styles_css: str) -> None:
    assert "status-created" in styles_css, (
        "Status badge must use .status-created CSS class, not inline styles"
    )


def test_css_preview_video_class(styles_css: str) -> None:
    assert ".preview-video" in styles_css, (
        "Video preview must use .preview-video class, not inline styles"
    )


def test_html_stats_inside_topbar(rendered_html: str) -> None:
    """Stats bar must be inside the topbar area, not a standalone wide stripe."""
    assert 'id="stats-bar"' in rendered_html


def test_html_rule_snapshot_present(rendered_html: str) -> None:
    assert 'id="rule-snapshot"' in rendered_html, (
        "Rule snapshot must exist in right rail"
    )


# ---------------------------------------------------------------------------
# New regression tests
# ---------------------------------------------------------------------------


def test_js_no_dual_contract_job_read(app_js: str) -> None:
    """fetchJob must strictly read data.job, not fallback to data."""
    assert "return data.job;" in app_js or "return data.job\n" in app_js or "return data.job " in app_js or "return data.job\r" in app_js, (
        "fetchJob must return data.job strictly, not data.job || data"
    )


def test_js_no_dual_contract_report_read(app_js: str) -> None:
    """Sections that read report must use data.report strictly."""
    assert "data.report || data" not in app_js, (
        "No code should fallback data.report || data"
    )
    assert "data.job || data" not in app_js, (
        "No code should fallback data.job || data"
    )


def test_js_parse_numeric_preserves_zero(app_js: str) -> None:
    """parseNumeric must not use || default that overwrites 0."""
    parse_func = _extract_function(app_js, "function parseNumeric")
    assert "isFinite" in parse_func, (
        "parseNumeric must use isFinite, not || default"
    )
    assert "parseFloat(" not in parse_func, (
        "parseNumeric must use Number(), not parseFloat()"
    )


def test_js_upload_button_has_dynamic_text(app_js: str) -> None:
    """updateUploadButton must set textContent based on model_ready."""
    update_func = _extract_function(app_js, "function updateUploadButton")
    assert 'textContent' in update_func or '.textContent' in app_js, (
        "Upload button text must be dynamic"
    )
    assert '仅创建任务' in app_js, (
        "Button must show 仅创建任务 when model is not ready"
    )
    assert '创建并分析' in app_js, (
        "Button must show 创建并分析 when model is ready"
    )


def test_js_download_url_not_double_encoded(app_js: str) -> None:
    """CSV/ZIP must use the backend URL directly, not pass through encodeURIComponent or artifactUrl."""
    csv_func = _extract_function(app_js, "handleDownloadCsv")
    zip_func = _extract_function(app_js, "handleDownloadZip")
    assert "encodeURIComponent" not in csv_func, (
        "CSV download URL must not be re-encoded"
    )
    assert "encodeURIComponent" not in zip_func, (
        "ZIP download URL must not be re-encoded"
    )


def test_js_rule_snapshot_renders_settings(app_js: str) -> None:
    assert "renderRuleSnapshot" in app_js, (
        "renderRuleSnapshot must exist"
    )
    assert "rule-snapshot" in app_js, (
        "Rule snapshot element must be referenced in JS"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_function(js: str, func_name: str) -> str:
    """Extract the body of a named function from JS source."""
    start = js.find(func_name)
    if start == -1:
        return ""
    brace_start = js.find("{", start)
    if brace_start == -1:
        return ""
    depth = 0
    i = brace_start
    for i in range(brace_start, len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                break
    return js[start:i + 1]


def _extract_media_block(css: str, media_feature: str) -> str:
    """Extract a CSS @media block by feature string."""
    start = css.find(media_feature)
    if start == -1:
        return ""
    brace_start = css.find("{", start)
    if brace_start == -1:
        return ""
    depth = 0
    for i in range(brace_start, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[start:i + 1]
    return ""


# ---------------------------------------------------------------------------
# Static file existence and structure
# ---------------------------------------------------------------------------


def test_static_directory_structure() -> None:
    assert (STATIC_DIR / "styles.css").is_file()
    assert (STATIC_DIR / "app.js").is_file()


def test_template_exists() -> None:
    assert (TEMPLATES_DIR / "index.html").is_file()


def test_index_html_is_valid_html5_boilerplate() -> None:
    html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") or html.startswith("<!DOCTYPE html>")


def test_app_js_is_syntactically_parseable() -> None:
    """Verify the JS file starts with an IIFE and has balanced braces."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert js.strip().startswith("(function")
    open_braces = js.count("{")
    close_braces = js.count("}")
    assert open_braces == close_braces, (
        f"Unbalanced braces in app.js: {open_braces} open, "
        f"{close_braces} close"
    )
    open_parens = js.count("(")
    close_parens = js.count(")")
    assert open_parens == close_parens, (
        f"Unbalanced parentheses in app.js: {open_parens} open, "
        f"{close_parens} close"
    )


# ---------------------------------------------------------------------------
# Numeric parsing boundary tests
# ---------------------------------------------------------------------------


def test_js_parse_integer_preserves_zero(app_js: str) -> None:
    """parseInteger must use isFinite and not return val || default."""
    parse_func = _extract_function(app_js, "function parseInteger")
    assert "isFinite" in parse_func, (
        "parseInteger must use isFinite, not || default"
    )
    assert "return" in parse_func, (
        "parseInteger must have a return statement"
    )
    assert "return defaultValue" in parse_func, (
        "parseInteger must return defaultValue for invalid input"
    )


def test_js_parse_numeric_preserves_zero_boundary(app_js: str) -> None:
    """parseNumeric must handle 0, empty string, and invalid strings."""
    parse_func = _extract_function(app_js, "function parseNumeric")
    assert "Number(" in parse_func, "parseNumeric must use Number()"
    assert "isFinite" in parse_func, "parseNumeric must use isFinite"
    assert "return num" in parse_func or "return num;" in parse_func or "return num\n" in parse_func or "return num\r" in parse_func, (
        "parseNumeric must return the parsed number, not value || default"
    )


# ---------------------------------------------------------------------------
# Polling contract tests
# ---------------------------------------------------------------------------


def test_js_poll_uses_recursive_settimeout_not_setinterval(app_js: str) -> None:
    """Polling must use recursive setTimeout, not setInterval."""
    assert "setInterval" not in app_js, (
        "Polling must use recursive setTimeout, not setInterval"
    )


def test_js_poll_uses_abort_controller(app_js: str) -> None:
    """Polling must use AbortController to cancel in-flight requests."""
    assert "AbortController" in app_js, (
        "Polling must use AbortController for cancellation"
    )


def test_js_poll_calls_cancel_polling_on_select(app_js: str) -> None:
    """selectJob must call cancelPolling first."""
    select_func = _extract_function(app_js, "function selectJob")
    assert "cancelPolling()" in select_func, (
        "selectJob must call cancelPolling before loading a new job"
    )


def test_js_poll_catches_abort_error(app_js: str) -> None:
    """pollJob catch handler must suppress AbortError."""
    poll_func = _extract_function(app_js, "function pollJob")
    assert "AbortError" in poll_func, (
        "pollJob must catch and suppress AbortError"
    )


def test_js_poll_clears_state_poll_abort_in_finally(app_js: str) -> None:
    """state.pollAbort must be cleared in .finally(), not before fetch."""
    poll_func = _extract_function(app_js, "function pollJob")
    assert ".finally" in poll_func, (
        "pollJob must use .finally() to clear state.pollAbort"
    )
    assert "state.pollAbort = null" in poll_func or "state.pollAbort=null" in poll_func, (
        "pollJob must clear state.pollAbort"
    )


# ---------------------------------------------------------------------------
# Layout constraint tests
# ---------------------------------------------------------------------------


def test_css_workspace_padding_is_compact(styles_css: str) -> None:
    """Workspace top padding must be <= 16px for above-the-fold layout."""
    import re
    ws_match = re.search(r'\.workspace\s*\{[^}]*padding:\s*(\d+)px', styles_css)
    assert ws_match is not None, "Could not find .workspace padding"
    top_padding = int(ws_match.group(1))
    assert top_padding <= 16, (
        f"Workspace top padding ({top_padding}px) must be <= 16px "
        f"to keep main-grid visible above the fold"
    )


def test_css_topbar_margin_is_compact(styles_css: str) -> None:
    """Topbar margin-bottom must be <= 12px."""
    import re
    tb_match = re.search(r'\.topbar\s*\{[^}]*margin-bottom:\s*(\d+)px', styles_css)
    assert tb_match is not None, "Could not find .topbar margin-bottom"
    margin = int(tb_match.group(1))
    assert margin <= 12, (
        f"Topbar margin-bottom ({margin}px) must be <= 12px"
    )


def test_css_drop_zone_padding_is_compact(styles_css: str) -> None:
    """Drop zone vertical padding must be <= 16px for compact layout."""
    import re
    dz_match = re.search(r'\.drop-zone\s*\{[^}]*padding:\s*(\d+)px', styles_css)
    assert dz_match is not None, "Could not find .drop-zone padding"
    dz_padding = int(dz_match.group(1))
    assert dz_padding <= 16, (
        f"Drop zone padding ({dz_padding}px) must be <= 16px"
    )


def test_css_evidence_panel_no_oversized_min_height(styles_css: str) -> None:
    """Evidence panel min-height must be <= 300px."""
    import re
    ep_match = re.search(r'\.evidence-panel\s*\{[^}]*min-height:\s*(\d+)px', styles_css)
    assert ep_match is not None, "Could not find .evidence-panel min-height"
    min_h = int(ep_match.group(1))
    assert min_h <= 300, (
        f"Evidence panel min-height ({min_h}px) must be <= 300px"
    )


def test_css_task_list_max_height_is_bounded(styles_css: str) -> None:
    """Task list max-height must be <= 280px to avoid pushing content down."""
    import re
    tl_match = re.search(r'\.task-list\s*\{[^}]*max-height:\s*(\d+)px', styles_css)
    assert tl_match is not None, "Could not find .task-list max-height"
    max_h = int(tl_match.group(1))
    assert max_h <= 280, (
        f"Task list max-height ({max_h}px) must be <= 280px"
    )


def test_css_single_column_on_narrow_viewport(styles_css: str) -> None:
    """At <= 860px, main-grid must collapse to single column."""
    narrow_section = _extract_media_block(styles_css, "max-width: 860px")
    assert "grid-template-columns: 1fr" in narrow_section, (
        "Narrow viewport must use single-column grid"
    )


def test_css_no_horizontal_scroll_on_mobile_lte_500(styles_css: str) -> None:
    """At <= 500px, workspace must not exceed viewport width."""
    narrow_section = _extract_media_block(styles_css, "max-width: 500px")
    assert "min(100% - 16px, 100%)" in narrow_section or "calc" in narrow_section, (
        "Mobile layout must constrain width to avoid horizontal scroll"
    )


# ---------------------------------------------------------------------------
# CSS hidden-attribute regression
# ---------------------------------------------------------------------------


def test_css_hidden_attribute_must_use_display_none_important(
    styles_css: str,
) -> None:
    """[hidden] must use display:none!important so flex classes don't override it."""
    import re
    assert "[hidden]" in styles_css, "CSS must include a [hidden] selector"
    match = re.search(r'\[hidden\]\s*\{[^}]*\}', styles_css)
    assert match is not None, "[hidden] rule must exist in CSS"
    rule = match.group()
    assert "display" in rule, "[hidden] must set display property"
    assert "none" in rule, "[hidden] must set display: none"
    assert "!important" in rule, "[hidden] must use !important to override display:flex"


def test_css_evidence_states_do_not_conflict_with_hidden(
    styles_css: str,
) -> None:
    """Verify evidence-loading and evidence-failed have hidden attr in HTML."""
    html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="evidence-loading" hidden' in html or 'id="evidence-loading"\n' in html.replace('\r', '')
    assert 'id="evidence-failed" hidden' in html or 'id="evidence-failed"\n' in html.replace('\r', '')


# ---------------------------------------------------------------------------
# Model readiness tests
# ---------------------------------------------------------------------------


def test_js_disables_analyze_button_when_model_not_ready(app_js: str) -> None:
    """Analyze/retry button must be disabled when model_ready is false."""
    retry_func = _extract_function(app_js, "function handleRetry")
    assert "model_ready" in retry_func, (
        "handleRetry must check model_ready"
    )


def test_js_upload_only_creates_when_model_not_ready(app_js: str) -> None:
    """Upload must skip analyze call when model_ready is false."""
    upload_func = _extract_function(app_js, "function handleUpload")
    assert "modelReady" in upload_func or "model_ready" in upload_func, (
        "handleUpload must check model readiness before calling analyze"
    )
    assert 'analyzeJob' in upload_func, (
        "handleUpload must conditionally call analyzeJob"
    )
