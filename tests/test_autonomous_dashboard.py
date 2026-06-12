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

    def test_dashboard_does_not_expose_live_button(self, client):
        body = client.get("/autonomous-trading/").get_data(as_text=True)
        # No live-execution control must be rendered.
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
            "Paper/Live match status",
            "Latest autonomous readiness status",
            "Last status refresh timestamp",
        ):
            assert label in src


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
        mode panel always reads from the correct source of truth."""
        src = self._js_source()
        assert "/api/autonomous/mode/status" in src, (
            "refreshStatus() must call /api/autonomous/mode/status directly"
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
        """confirmPaperExecute must not log 'Activation modal cancelled by operator'."""
        src = self._js_source()
        # confirmPaperExecute calls hidePaperConfirm (no log), not cancelPaperConfirm
        assert "function confirmPaperExecute" in src
        # Extract the confirmPaperExecute function body
        start = src.index("async function confirmPaperExecute()")
        # Find the cancellation log — it must NOT appear in confirmPaperExecute
        assert "hidePaperConfirm()" in src[start:start + 200]
        assert "cancelPaperConfirm()" not in src[start:start + 200]

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
        # runStatus === 'no_trade' should set kind to 'info', not 'error'
        assert "runStatus === 'no_trade'" in src
        # Verify that no_trade maps to 'info' kind
        start = src.index("runStatus === 'no_trade'")
        # The line should assign kind = 'info'
        region = src[start - 50:start + 80]
        assert "kind = 'info'" in region
