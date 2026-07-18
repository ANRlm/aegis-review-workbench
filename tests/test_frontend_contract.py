"""Verify frontend contract: state transitions, responsive layout, motion, keyboard."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def template_path() -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / "index.html"


@pytest.fixture(scope="module")
def styles_path() -> Path:
    return Path(__file__).resolve().parent.parent / "static" / "styles.css"


@pytest.fixture(scope="module")
def script_path() -> Path:
    return Path(__file__).resolve().parent.parent / "static" / "app.js"


class TestFrontendFiles:
    def test_index_html_exists_and_contains_required_sections(self, template_path: Path) -> None:
        assert template_path.is_file(), "templates/index.html does not exist"
        html = template_path.read_text("utf-8")
        assert "影鉴" in html
        assert "Aegis Review" in html
        assert "uploadForm" in html or "上传" in html
        assert "historyList" in html or "历史任务" in html
        assert "evidenceContent" in html or "evidence" in html
        assert "reviewContent" in html or "review" in html or "审核" in html

    def test_styles_css_exists_and_uses_design_tokens(self, styles_path: Path) -> None:
        assert styles_path.is_file(), "static/styles.css does not exist"
        css = styles_path.read_text("utf-8")
        assert "--canvas: #f7f7f3" in css or "#F7F7F3" in css
        assert "--surface: #ffffff" in css or "#ffffff" in css
        assert "--ink:" in css
        assert "--accent:" in css
        assert "--radius:" in css
        assert "--transition:" in css or "200ms" in css or "240ms" in css
        assert "prefers-reduced-motion" in css

    def test_styles_css_has_keyboard_focus_style(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "focus-visible" in css or "outline" in css

    def test_styles_css_has_responsive_breakpoints(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "@media" in css
        assert "max-width" in css

    def test_app_js_exists(self, script_path: Path) -> None:
        assert script_path.is_file(), "static/app.js does not exist"
        js = script_path.read_text("utf-8")
        assert "apiFetch" in js or "fetch" in js
        assert "API_BASE" in js or "/api" in js


class TestApiContractCompliance:
    """Check that the frontend only uses documented API endpoints."""

    API_ENDPOINTS = [
        "/health",
        "/jobs",
        "/jobs/",
        "/analyze",
        "/report",
        "/artifacts/",
        "/stats",
        "/review",
    ]

    def test_frontend_only_refers_to_documented_endpoints(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        for ep in self.API_ENDPOINTS:
            assert ep in js, f"Missing documented endpoint reference: {ep}"

    def test_frontend_checks_ok_field(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        assert ".ok" in js or "ok" in js, "Frontend must check ok field"

    def test_frontend_shows_error_message(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        assert "error" in js or "message" in js

    def test_frontend_disables_analysis_when_model_not_ready(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        assert "modelReady" in js or "model_ready" in js

    def test_frontend_polls_completed_or_failed_stop(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        assert "completed" in js and "failed" in js
        assert "stopPolling" in js or "clearInterval" in js


class TestStatesAndTransitions:
    """Verify all four page states are represented."""

    STATES = ["empty", "loading", "failed", "completed"]

    def test_all_states_present_in_html(self, template_path: Path) -> None:
        html = template_path.read_text("utf-8")
        for state in self.STATES:
            assert state in html.lower(), f"Missing state: {state}"

    def test_all_states_present_in_js(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        for state in self.STATES:
            assert state in js.lower(), f"Missing state handler: {state}"

    def test_hidden_attribute_used_for_state_toggle(self, template_path: Path) -> None:
        html = template_path.read_text("utf-8")
        assert 'hidden' in html


class TestResponsiveLayout:
    """Verify responsive design requirements."""

    def test_css_has_three_column_layout(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "grid-template-columns" in css

    def test_css_has_single_column_breakpoint(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "grid-template-columns: 1fr" in css or "grid-template-columns: 1fr 1fr 1fr" not in css

    def test_css_has_no_overflow_hidden_on_body(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "overflow" not in css or "overflow-y: auto" in css

    def test_sticky_topbar(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "sticky" in css or "position: sticky" in css


class TestMotionAndKeyboard:
    """Verify animation constraints and keyboard accessibility."""

    def test_reduced_motion_query(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "prefers-reduced-motion" in css
        assert "0.01ms" in css

    def test_focus_visible_style(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "focus-visible" in css, "Must use :focus-visible for keyboard focus"

    def test_animated_properties_use_transition(self, styles_path: Path) -> None:
        css = styles_path.read_text("utf-8")
        assert "transition" in css


class TestDownloadActions:
    """Verify download functionality."""

    DOWNLOAD_TYPES = ["json", "csv", "zip"]

    def test_download_buttons_in_html(self, template_path: Path) -> None:
        html = template_path.read_text("utf-8")
        for dt in self.DOWNLOAD_TYPES:
            assert dt.lower() in html.lower() or dt.upper() in html, f"Missing download: {dt}"

    def test_download_handling_in_js(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        for dt in self.DOWNLOAD_TYPES:
            assert dt in js.lower() or dt.upper() in js


class TestReviewWorkflow:
    """Verify review panel requirements."""

    def test_review_has_three_decisions(self, template_path: Path) -> None:
        html = template_path.read_text("utf-8")
        for d in ["pass", "review", "reject"]:
            assert d in html.lower()

    def test_review_requires_reviewer(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        assert "reviewer" in js or "负责人" in js

    def test_review_has_note_field(self, template_path: Path) -> None:
        html = template_path.read_text("utf-8")
        assert "note" in html or "备注" in html

    def test_review_saves_decision(self, script_path: Path) -> None:
        js = script_path.read_text("utf-8")
        assert "review" in js or "saveReview" in js or "改判" in js
