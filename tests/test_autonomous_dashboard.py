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
            "Status &amp; Safety",
            "Deployable Cash",
            "Candidate Shortlist",
            "Trade Proposal",
            "Decision Timeline",
            "Execute Paper Trade",
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
