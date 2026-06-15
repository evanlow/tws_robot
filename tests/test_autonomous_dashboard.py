"""Tests for the Autonomous Trading dashboard page and the
``GET /api/autonomous/audit`` endpoint that backs its timeline view.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from web import create_app


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    monkeypatch.setattr(
        "web.routes.api_connection.is_accepted", lambda: True
    )
    app = create_app(
        {"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False}
    )
    app.config["autonomous_audit_log_dir"] = str(tmp_path)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _write_audit_log(tmp_path: Path, records):
    when = datetime.now(timezone.utc)
    log = tmp_path / f"autonomous_trading_{when:%Y%m%d}.jsonl"
    with log.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return log


class TestPage:
    def test_dashboard_page_is_registered(self, client):
        resp = client.get("/autonomous-trading/")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Autonomous Trading" in body
        # Key sections must be present in the rendered HTML.
        for needle in (
            "Autonomous Mode",
            "Deployable Cash",
            "Candidate Shortlist",
            "Trade Proposal",
            "Decision Timeline",
            "Activate Autonomous Mode",
            "Single Trade",
            "Continuous Trading",
            "Emergency Stop",
            "autonomous_trading.js",
        ):
            assert needle in body, f"missing section: {needle!r}"

    def test_dashboard_uses_unified_live_aware_controls(self, client):
        body = client.get("/autonomous-trading/").get_data(as_text=True)
        assert "detected Paper or Live TWS account context" in body
        assert 'id="liveConfirmFields"' in body
        assert 'id="liveExpectedAccountId"' in body
        # Legacy unrestricted live execution endpoint must not be exposed.
        assert "execute-live" not in body.lower()
        assert "execute live" not in body.lower()

    def test_nav_includes_autonomous_trading_link(self, client):
        body = client.get("/autonomous-trading/").get_data(as_text=True)
        assert 'href="/autonomous-trading/"' in body


class TestAuditEndpoint:
    def test_audit_returns_empty_when_no_log(self, client):
        resp = client.get("/api/autonomous/audit")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body == {"entries": [], "count": 0}

    def test_audit_returns_recent_entries_newest_first(
        self, app, client, tmp_path
    ):
        records = [
            {
                "timestamp": "2024-01-01T10:00:00+00:00",
                "decision": {
                    "status": "no_candidate",
                    "mode": "recommend_only",
                    "rejection_reason": "no signals available",
                },
            },
            {
                "timestamp": "2024-01-01T11:00:00+00:00",
                "decision": {
                    "status": "paper_executed",
                    "mode": "paper_execute",
                    "selected": {"symbol": "AAA"},
                    "trade_plan": {"symbol": "AAA", "trade_type": "BUY_SHARES"},
                    "order_id": 42,
                },
            },
        ]
        _write_audit_log(tmp_path, records)

        body = client.get("/api/autonomous/audit?limit=10").get_json()
        assert body["count"] == 2
        # Newest-first: paper_executed entry must come before the rejection.
        assert body["entries"][0]["status"] == "paper_executed"
        assert body["entries"][0]["selected_symbol"] == "AAA"
        assert body["entries"][0]["trade_type"] == "BUY_SHARES"
        assert body["entries"][0]["order_id"] == 42
        assert body["entries"][1]["status"] == "no_candidate"
        assert body["entries"][1]["rejection_reason"] == "no signals available"

    def test_audit_limit_is_clamped(self, app, client, tmp_path):
        records = [
            {
                "timestamp": f"2024-01-01T10:00:0{i}+00:00",
                "decision": {"status": "no_candidate", "mode": "recommend_only"},
            }
            for i in range(5)
        ]
        _write_audit_log(tmp_path, records)
        body = client.get("/api/autonomous/audit?limit=2").get_json()
        assert body["count"] == 2

    def test_audit_limit_zero_clamps_to_one(self, app, client, tmp_path):
        records = [
            {
                "timestamp": f"2024-01-01T10:00:0{i}+00:00",
                "decision": {"status": f"s{i}", "mode": "recommend_only"},
            }
            for i in range(3)
        ]
        _write_audit_log(tmp_path, records)
        body = client.get("/api/autonomous/audit?limit=0").get_json()
        assert body["count"] == 1
        assert body["entries"][0]["status"] == "s2"

    def test_audit_ignores_malformed_lines(self, app, client, tmp_path):
        when = datetime.now(timezone.utc)
        log = tmp_path / f"autonomous_trading_{when:%Y%m%d}.jsonl"
        with log.open("w", encoding="utf-8") as fh:
            fh.write("not json at all\n")
            fh.write(json.dumps({
                "timestamp": "2024-01-01T12:00:00+00:00",
                "decision": {"status": "recommended", "mode": "recommend_only"},
            }) + "\n")
            fh.write("\n")  # blank line
        body = client.get("/api/autonomous/audit").get_json()
        assert body["count"] == 1
        assert body["entries"][0]["status"] == "recommended"


class TestShortlistRendering:
    """Guard against regressing the Candidate Shortlist payload shape.

    The backend returns ranked candidates shaped like
    ``RankedCandidate.to_dict()`` — a wrapper ``{"candidate": {...},
    "score": ..., "reasons": [...]}``.  The dashboard's JS must read the
    candidate fields from the nested ``candidate`` object (with a flat
    fallback for older fixtures) or the table silently renders blanks.
    """

    def _js_source(self) -> str:
        from autonomous.candidate_ranker import RankedCandidate
        from autonomous.candidate_scanner import CandidateSignal

        # Build a realistic /api/autonomous/scan row to make sure the
        # contract we're asserting against is the one the backend actually
        # produces.
        sample = RankedCandidate(
            candidate=CandidateSignal(
                symbol="AAPL",
                company_name="Apple Inc.",
                sector="Information Technology",
                strength_score=100,
                signal_label="Confirmed Rebound",
                last_price=190.25,
                support_price=185.0,
                resistance_price=205.0,
            ),
            score=100.25,
            reasons=["strength_score=100", "signal_label=Confirmed Rebound"],
        ).to_dict()
        assert "candidate" in sample and sample["candidate"]["symbol"] == "AAPL"
        assert sample["candidate"]["company_name"] == "Apple Inc."

        js_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "static" / "js" / "autonomous_trading.js"
        )
        return js_path.read_text(encoding="utf-8")

    def test_shortlist_normalises_ranked_candidate_wrapper(self):
        src = self._js_source()
        # The JS must look at the nested `candidate` wrapper produced by
        # RankedCandidate.to_dict(); otherwise every candidate cell will
        # render as an em-dash placeholder.
        assert "row.candidate" in src, (
            "renderShortlist() must dereference the nested `candidate` "
            "object from RankedCandidate.to_dict()."
        )
        for field in (
            "candidate.symbol",
            "candidate.company_name",
            "candidate.sector",
            "candidate.strength_score",
            "candidate.signal_label",
            "candidate.last_price",
            "candidate.support_price",
            "candidate.resistance_price",
        ):
            assert field in src, (
                f"renderShortlist() must read `{field}` from the nested "
                "CandidateSignal payload."
            )
        # Ranking metadata stays at the wrapper level.
        assert "row.score" in src
        assert "row.reasons" in src


class TestFrontendSecurity:
    def test_proposal_and_audit_errors_use_text_content(self):
        js_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "static" / "js" / "autonomous_trading.js"
        )
        src = js_path.read_text(encoding="utf-8")
        assert "header.textContent" in src
        assert "rej.textContent" in src
        assert "Failed to load audit log: ' + ((err && err.message)" in src


class TestStatusBadges:
    """The dashboard's status panel must surface the wired provider /
    paper-adapter readiness so operators can see whether the system is
    really executable, not just whether the page rendered."""

    def _js_source(self) -> str:
        js_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "static" / "js" / "autonomous_trading.js"
        )
        return js_path.read_text(encoding="utf-8")

    def test_signal_provider_ready_badge_is_rendered(self):
        src = self._js_source()
        assert "SIGNAL PROVIDER READY" in src
        # The badge must be driven by the explicit boolean from /status.
        assert "signal_provider_ready" in src

    def test_autonomous_mode_badges_are_rendered(self):
        src = self._js_source()
        assert "AUTONOMOUS " in src
        assert "MATCH " in src

    def test_disabled_button_uses_paper_adapter_reason(self):
        src = self._js_source()
        # When the adapter is unavailable the tooltip should show the
        # backend-supplied reason (e.g. "Connect to IBKR paper mode…")
        # rather than a hard-coded string.
        assert "paper_adapter_reason" in src

    def test_autonomous_mode_panel_fields_are_rendered(self):
        src = self._js_source()
        for label in (
            "Autonomous Mode status",
            "TWS connection status",
            "Selected connection type",
            "Verified running TWS session/account type",
            "Detected account ID",
            "Paper/Live match status",
            "Dashboard account context",
            "Latest autonomous readiness status",
            "Last status refresh timestamp",
        ):
            assert label in src


class TestStatusDisplayRefinement:
    """Verify that the Autonomous Mode panel uses non-button status indicators.

    The mode state chip must be a passive display element (not styled like a
    button), readiness checks must be grouped under a clear label, and the
    trading cycle selector must be labelled as a selectable choice — so
    operators can immediately distinguish status from actions.
    """

    def _js_source(self) -> str:
        js_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "static" / "js" / "autonomous_trading.js"
        )
        return js_path.read_text(encoding="utf-8")

    def _html_source(self, client) -> str:
        return client.get("/autonomous-trading/").get_data(as_text=True)

    def _css_source(self) -> str:
        css_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "static" / "css" / "autonomous_trading.css"
        )
        return css_path.read_text(encoding="utf-8")

    # ---- HTML structure ----

    def test_mode_state_chip_element_exists(self, client):
        """The #modeStateChip element must be present for mode state display."""
        html = self._html_source(client)
        assert 'id="modeStateChip"' in html

    def test_readiness_list_element_exists(self, client):
        """The #readinessList element must be present for readiness check items."""
        html = self._html_source(client)
        assert 'id="readinessList"' in html

    def test_readiness_section_label_exists(self, client):
        """A 'Readiness checks' label must group the passive readiness indicators."""
        html = self._html_source(client)
        assert "Readiness checks" in html

    def test_cycle_selector_label_exists(self, client):
        """A label must make the trading cycle options clearly selectable choices."""
        html = self._html_source(client)
        assert "Choose trading cycle before activation" in html

    # ---- JS logic ----

    def test_mode_chip_shows_all_state_texts(self):
        """JS must set modeStateChip text for OFF, ON, and BLOCKED states."""
        src = self._js_source()
        assert "AUTONOMOUS OFF" in src
        assert "AUTONOMOUS ON" in src
        assert "AUTONOMOUS BLOCKED" in src

    def test_mode_chip_uses_neutral_class_for_off_state(self):
        """OFF state must use a neutral chip class, not the green badge-safe."""
        src = self._js_source()
        assert "mode-chip-off" in src
        assert "mode-chip-on" in src
        assert "mode-chip-blocked" in src

    def test_readiness_list_renders_match_and_provider(self):
        """JS must populate #readinessList with MATCH and provider check items."""
        src = self._js_source()
        assert "readinessList" in src
        assert "'MATCH ' + matchStatus.toUpperCase()" in src
        assert "SIGNAL PROVIDER READY" in src

    def test_mode_chip_updates_description_text(self):
        """JS must update the #modeStateDesc element alongside the chip class."""
        src = self._js_source()
        assert "modeStateDesc" in src
        assert "modeDescEl" in src

    # ---- CSS non-button styling ----

    def test_css_has_mode_state_chip_classes(self):
        """CSS must define mode-chip-off/on/blocked with distinct colours."""
        css = self._css_source()
        assert ".mode-chip-off" in css
        assert ".mode-chip-on" in css
        assert ".mode-chip-blocked" in css

    def test_mode_chip_off_not_green(self):
        """OFF chip must NOT use the green badge-safe background (#22543d)."""
        css = self._css_source()
        off_block = css.split(".mode-chip-off")[1].split("}")[0]
        assert "#22543d" not in off_block, (
            "mode-chip-off must use a neutral colour, not the green badge-safe colour"
        )

    def test_readiness_item_has_non_button_cursor(self):
        """Readiness items must use cursor:default (they are not clickable)."""
        css = self._css_source()
        assert ".readiness-item" in css
        # cursor:default conveys non-interactivity without blocking tooltip events
        readiness_item_block = css.split(".readiness-item")[1].split("}")[0]
        assert "cursor: default" in readiness_item_block


class TestModeActivationButton:
    """The dashboard must correctly enable/disable the activation button based on
    the mode status payload and display visible gate reasons to the operator."""

    def _js_source(self) -> str:
        js_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "static" / "js" / "autonomous_trading.js"
        )
        return js_path.read_text(encoding="utf-8")

    def _html_source(self, client) -> str:
        return client.get("/autonomous-trading/").get_data(as_text=True)

    # ---- JS source checks ----

    def test_refresh_status_fetches_mode_status_directly(self):
        """refreshStatus() must fetch /api/autonomous/mode/status directly so the
        dashboard can read Paper/Live verification before choosing a runner."""
        src = self._js_source()
        assert "/api/autonomous/mode/status" in src, (
            "refreshStatus() must call /api/autonomous/mode/status directly"
        )
        assert "/api/autonomous/live/status" in src, (
            "refreshStatus() must call /api/autonomous/live/status for live accounts"
        )

    def test_render_status_uses_mode_payload_parameter(self):
        """renderStatus must accept a modePayload argument and use it for mode data."""
        src = self._js_source()
        assert "modePayload" in src, (
            "renderStatus must accept modePayload to avoid divergence from autonomous_mode nesting"
        )

    def test_button_enable_condition_checks_readiness_status(self):
        """The button enable logic must check readiness.status === 'Ready'."""
        src = self._js_source()
        assert "readiness.status === 'Ready'" in src, (
            "modeBtn.disabled must be driven by readiness.status"
        )

    def test_gate_reasons_element_is_populated(self):
        """When button is disabled, gate reasons must be written to the DOM element."""
        src = self._js_source()
        assert "modeGateReasons" in src, (
            "JS must write gate reasons to the #modeGateReasons DOM element"
        )
        # The reasons text must come from gates.reasons array.
        assert "gates.reasons" in src, (
            "gate reasons text must be derived from the gates.reasons array"
        )

    def test_live_account_context_routes_to_live_endpoints(self):
        """The dashboard must map detected live accounts to /api/autonomous/live/*."""
        src = self._js_source()
        for endpoint in (
            "/api/autonomous/live/activate",
            "/api/autonomous/live/halt",
            "/api/autonomous/live/run-once",
            "/api/autonomous/live/evaluate-exits",
            "/api/autonomous/live/trades",
        ):
            assert endpoint in src
        assert "accountContextFromConnection" in src
        assert "running_account_type" in src

    def test_live_activation_requires_account_id_and_dry_run(self):
        """Live dashboard activation must confirm the detected account and use dry-run."""
        src = self._js_source()
        assert "liveExpectedAccountId" in src
        assert "expected_account_id: expectedAccountId" in src
        assert "confirmed_by: 'dashboard'" in src
        assert "dry_run: true" in src
        assert "Live activation blocked: type the detected account ID exactly." in src

    def test_live_continuous_selection_requires_live_continuous_gate(self):
        """Continuous Trading must require the live continuous feature gate."""
        src = self._js_source()
        assert "live_continuous_enabled" in src
        assert "continuousSelected" in src
        assert "AUTONOMOUS_LIVE_CONTINUOUS_ENABLED=true" in src

    def test_live_mode_state_is_cached_when_live_status_fails(self):
        """Live status fetch failures must retain last known live mode state."""
        src = self._js_source()
        assert "const cachedMode = (state.modePayload && state.modePayload.mode) || {};" in src
        assert "const liveMode = (liveData && liveData.autonomous_live_mode) || cachedMode;" in src

    def test_halt_attempts_both_endpoints_when_context_is_ambiguous(self):
        """When mode appears ON but context is blocked, halt must try live then paper."""
        src = self._js_source()
        assert "Ambiguous account context while mode is ON; attempting both live and paper halt endpoints." in src
        assert "for (const endpoint of [ENDPOINTS.live.halt, ENDPOINTS.paper.halt])" in src
        assert "No halt endpoint accepted the request" in src

    def test_blocked_context_off_path_contract_in_rendered_dashboard(self, client):
        """Integration-style guard: rendered dashboard + JS must express dual-halt OFF fallback."""
        html = self._html_source(client)
        src = self._js_source()
        assert 'id="btnAutonomousModeToggle"' in html
        assert "Turn Autonomous Mode OFF" in src
        assert "ENDPOINTS.live.halt" in src
        assert "ENDPOINTS.paper.halt" in src
        assert "attempting both live and paper halt endpoints" in src

    def test_mismatch_diagnostic_shown_when_gates_ready_but_blocked(self):
        """When gates.ready is true but the button is still disabled, the JS must
        show a 'UI readiness mismatch' diagnostic rather than an empty reason."""
        src = self._js_source()
        assert "readiness mismatch" in src, (
            "JS must show a mismatch diagnostic when gates.ready is true but activation is blocked"
        )

    # ---- HTML structure checks ----

    def test_mode_gate_reasons_element_exists(self, client):
        """The #modeGateReasons element must be present for JS to populate."""
        html = self._html_source(client)
        assert 'id="modeGateReasons"' in html, (
            "#modeGateReasons element must be present in the template"
        )

    def test_trading_cycle_rendered_as_option_cards(self, client):
        """Trading Cycle controls must use the option-card layout, not a cramped fieldset."""
        html = self._html_source(client)
        assert "cycle-option" in html, (
            "Trading Cycle must use the .cycle-option card layout"
        )
        assert "cycle-selector" in html, (
            "Trading Cycle container must use .cycle-selector"
        )

    def test_trading_cycle_options_present(self, client):
        """Both Single Trade and Continuous Trading options must be present."""
        html = self._html_source(client)
        assert 'value="single_trade"' in html
        assert 'value="continuous"' in html

    def test_activate_button_present_and_initially_disabled(self, client):
        """The #btnAutonomousModeToggle must be present and start disabled."""
        html = self._html_source(client)
        assert 'id="btnAutonomousModeToggle"' in html
        assert "disabled" in html


class TestActivityLogPanel:
    """The Autonomous Activity Log panel must exist and JS must drive it."""

    def _js_source(self) -> str:
        js_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "static" / "js" / "autonomous_trading.js"
        )
        return js_path.read_text(encoding="utf-8")

    def _html_source(self, client) -> str:
        return client.get("/autonomous-trading/").get_data(as_text=True)

    # ---- DOM existence ----

    def test_activity_log_panel_exists(self, client):
        """The #activityLogPanel section must be present in the rendered page."""
        html = self._html_source(client)
        assert 'id="activityLogPanel"' in html
        assert 'id="activityLogList"' in html
        assert "Autonomous Activity Log" in html
        assert '<ul id="activityLogList"' in html

    def test_activity_log_placed_before_cash_panel(self, client):
        """The activity log must appear between Autonomous Mode and Deployable Cash."""
        html = self._html_source(client)
        log_pos = html.index('id="activityLogPanel"')
        cash_pos = html.index('id="cashPanel"')
        assert log_pos < cash_pos, (
            "Activity Log panel must appear before the Cash panel"
        )

    # ---- JS source checks ----

    def test_log_activity_function_exists(self):
        """logActivity helper must be defined in the JS source."""
        src = self._js_source()
        assert "function logActivity(" in src

    def test_activation_click_logs_event(self):
        """Clicking Activate must produce an activity log entry."""
        src = self._js_source()
        assert "Operator clicked Activate Autonomous Mode" in src

    def test_cancel_logs_event(self):
        """Cancelling the modal must produce an activity log entry."""
        src = self._js_source()
        assert "Activation modal cancelled" in src

    def test_no_trade_response_logs_valid_outcome(self):
        """A no_trade response must be logged as a valid outcome, not an error."""
        src = self._js_source()
        assert "No Trade:" in src
        # Must NOT be labelled as error — it's info level
        assert "'info', 'No Trade:" in src

    def test_no_trade_logs_mode_off(self):
        """A no_trade outcome must log that Autonomous Mode was turned OFF."""
        src = self._js_source()
        assert "ended with NO TRADE; Autonomous Mode turned OFF" in src

    def test_api_error_logs_error_entry(self):
        """API errors during activation must be logged at error level."""
        src = self._js_source()
        assert "'error', 'Autonomous Mode activation failed:" in src

    def test_halt_logs_filled_positions_note(self):
        """Halt action must log that filled positions were not liquidated."""
        src = self._js_source()
        assert "Filled positions were not liquidated" in src

    def test_emergency_stop_logs_event(self):
        """Emergency stop must produce an activity log entry."""
        src = self._js_source()
        assert "Emergency stop clicked by operator" in src

    def test_dashboard_loaded_logs_event(self):
        """Page load must log a dashboard loaded event."""
        src = self._js_source()
        assert "Dashboard loaded" in src

    def test_confirm_path_does_not_log_cancellation(self):
        """confirmAutonomousActivation must not log cancellation."""
        src = self._js_source()
        assert "function confirmAutonomousActivation" in src
        start = src.index("async function confirmAutonomousActivation()")
        region = src[start:start + 1200]
        assert "hidePaperConfirm()" in region
        assert "cancelPaperConfirm()" not in region

    def test_spy_gate_uses_market_gate_bullish(self):
        """SPY gate logging must derive from decision.market_gate.bullish, not body.run.spy_gate_passed."""
        src = self._js_source()
        # Must reference market_gate.bullish for pass/fail logic
        assert "market_gate" in src
        assert "marketGate.bullish === true" in src
        assert "marketGate.bullish === false" in src
        # Must NOT reference the old spy_gate_passed field
        assert "spy_gate_passed" not in src

    def test_no_trade_feedback_not_error(self):
        """A no_trade run status must not produce error-level feedback."""
        src = self._js_source()
        # no_trade should set kind to 'info' for either status source
        assert "status === 'no_trade' || runStatus === 'no_trade'" in src
        # Verify no_trade maps to 'info' kind
        start = src.index("status === 'no_trade' || runStatus === 'no_trade'")
        region = src[start - 60:start + 120]
        assert "kind = 'info'" in region

    # ---- Severity visual cues ----

    def test_severity_meta_mapping_exists(self):
        """SEVERITY_META must map info/success/warning/error to label+icon."""
        src = self._js_source()
        assert "SEVERITY_META" in src
        assert "info:" in src
        assert "success:" in src
        assert "warning:" in src
        assert "error:" in src

    def test_render_creates_severity_badge(self):
        """renderActivityLog must create an element with class activity-severity."""
        src = self._js_source()
        assert "'activity-severity'" in src

    def test_severity_badge_has_aria_hidden(self):
        """The severity badge icon must have aria-hidden for screen readers."""
        src = self._js_source()
        assert "aria-hidden" in src

    def test_entry_has_aria_label(self):
        """Each log entry must set an aria-label for accessibility."""
        src = self._js_source()
        assert "aria-label" in src
        assert "meta.label + ': ' + entry.timestamp + ' — ' + entry.message" in src

    def _css_source(self) -> str:
        css_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "static" / "css" / "autonomous_trading.css"
        )
        return css_path.read_text(encoding="utf-8")

    def test_css_has_severity_class(self):
        """CSS must define .activity-severity styling."""
        css = self._css_source()
        assert ".activity-severity" in css

    def test_css_severity_colors_per_level(self):
        """CSS must define per-level colours for severity badges."""
        css = self._css_source()
        assert ".activity-info .activity-severity { color: #4299e1; }" in css
        assert ".activity-success .activity-severity { color: #48bb78; }" in css
        assert ".activity-warning .activity-severity { color: #ecc94b; }" in css
        assert ".activity-error .activity-severity { color: #fc8181; }" in css
