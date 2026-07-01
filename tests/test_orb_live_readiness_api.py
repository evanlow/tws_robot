"""Tests for the ORB Phase 4 live-readiness API endpoint (#213).

Verifies the ``/api/orb/strategies/<name>/live-readiness`` endpoint (built
on ``autonomous.orb_live_readiness``) stays locked by default and only
reports a candidate status when every gate is explicitly satisfied. Never
places an order; never flips a live switch.
"""

import json

import pytest

import web.routes.api_opening_range as api
from autonomous.audit import AuditLogger
from autonomous.runner_config import AutonomousLiveRunnerConfig
from web import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    api._manager = None
    api._proposal_store = None
    api._executor = None
    api._exit_manager = None
    api._review_store = None
    api._live_readiness_confirmations = None
    app = create_app({
        "TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False,
        "orb_config_dir": str(tmp_path / "config"),
        "orb_evidence_dir": str(tmp_path / "logs"),
    })
    yield app.test_client()
    api._manager = None
    api._proposal_store = None
    api._executor = None
    api._exit_manager = None
    api._review_store = None
    api._live_readiness_confirmations = None


def _seed_trade(log_dir, *, strategy="ORB1", symbol="QQQ", trade_id="t1",
                 session_date="2024-01-02", entry_price=100.0, actual_entry_price=None,
                 entry_slippage=None, realized_r=None, exit_reason="TARGET",
                 status="exit_filled", failure_note=None):
    """Write minimal paper-execution + intraday-exit evidence records."""
    audit = AuditLogger(str(log_dir))
    audit.log_decision({
        "kind": "orb_paper_execution",
        "action": "orb_paper_executed",
        "trade_id": trade_id,
        "strategy": strategy,
        "symbol": symbol,
        "session_date": session_date,
        "entry_price": entry_price,
        "stop_price": entry_price - 1.0,
        "target_price": entry_price + 2.0,
        "quantity": 10,
        "protection_status": "BRACKET_CONFIRMED",
    })
    if status == "entry_filled":
        audit.log_decision({
            "kind": "orb_intraday_exit", "action": "entry_filled", "trade_id": trade_id,
            "fill_price": actual_entry_price or entry_price, "entry_slippage": entry_slippage,
        })
    elif status == "exit_filled":
        audit.log_decision({
            "kind": "orb_intraday_exit", "action": "entry_filled", "trade_id": trade_id,
            "fill_price": actual_entry_price or entry_price, "entry_slippage": entry_slippage,
        })
        audit.log_decision({
            "kind": "orb_intraday_exit", "action": "exit_filled", "trade_id": trade_id,
            "fill_price": entry_price + 1.0, "reason": exit_reason, "realized_r": realized_r,
        })
    elif status == "exit_failed_no_price":
        audit.log_decision({
            "kind": "orb_intraday_exit", "action": "entry_filled", "trade_id": trade_id,
            "fill_price": actual_entry_price or entry_price, "entry_slippage": entry_slippage,
        })
        audit.log_decision({
            "kind": "orb_intraday_exit", "action": "exit_failed_no_price", "trade_id": trade_id,
            "would_exit_reason": exit_reason,
        })


def _seed_rejection(log_dir, *, strategy="ORB1", reason="missing_protection"):
    AuditLogger(str(log_dir)).log_decision({
        "kind": "orb_paper_execution",
        "action": "orb_paper_rejected",
        "proposal_id": "p1",
        "strategy": strategy,
        "session_date": "2024-01-02",
        "symbol": "QQQ",
        "mode": "paper_autonomous",
        "reason": reason,
    })


def _make(client, name="ORB1", symbols=None, mode="recommend_only"):
    return client.post("/api/orb/strategies", json={
        "name": name, "symbols": symbols or ["QQQ"], "mode": mode})


def test_unknown_strategy_404(client):
    res = client.get("/api/orb/strategies/NOPE/live-readiness")
    assert res.status_code == 404


def test_default_locked_no_paper_evidence(client):
    _make(client)
    res = client.get("/api/orb/strategies/ORB1/live-readiness")
    assert res.status_code == 200
    body = res.get_json()
    assert body["overall_status"] == "LOCKED"
    assert body["live_trading_locked"] is True
    # No connection, no live master switch, no operator confirmation, no
    # emergency-stop testing -> multiple gates fail by default.
    assert "live_master_switch_enabled" in body["failing_gates"]
    assert "operator_confirmation" in body["failing_gates"]
    assert "broker_connection_confirmed" in body["failing_gates"]


def test_readiness_audit_logged(client, tmp_path):
    _make(client)
    client.get("/api/orb/strategies/ORB1/live-readiness")
    log_files = list((tmp_path / "logs").glob("autonomous_trading_*.jsonl"))
    assert log_files
    records = [json.loads(l) for l in log_files[0].read_text().splitlines()]
    assert any(r.get("kind") == "orb_live_readiness" and r.get("action") == "evaluate" for r in records)


def test_query_params_do_not_bypass_broker_or_switch(client):
    _make(client)
    res = client.get(
        "/api/orb/strategies/ORB1/live-readiness",
        query_string={
            "confirm_account": "true",
            "confirm_mode": "true",
            "emergency_stop_tested": "true",
        },
    )
    body = res.get_json()
    # Operator confirmations alone never unlock live trading: master switch
    # and broker connection are still unmet in a bare test app.
    assert body["overall_status"] == "LOCKED"
    assert "live_master_switch_enabled" in body["failing_gates"]
    assert "broker_connection_confirmed" in body["failing_gates"]


# ---------------------------------------------------------------------------
# Regression: evidence-derived risk/slippage gates (review feedback #1)
# ---------------------------------------------------------------------------

def test_bad_realized_r_history_locks_without_query_params(client, tmp_path):
    _make(client)
    log_dir = tmp_path / "logs"
    # Six consecutive losing trades -> max_consecutive_losses(6) exceeds the
    # default criteria (5), purely from evidence; no query params supplied.
    for i in range(6):
        _seed_trade(
            log_dir, trade_id=f"loss-{i}", session_date=f"2024-01-{i + 1:02d}",
            realized_r=-1.0,
        )
    res = client.get("/api/orb/strategies/ORB1/live-readiness")
    body = res.get_json()
    assert body["overall_status"] == "LOCKED"
    assert "paper_evidence_meets_thresholds" in body["failing_gates"]


def test_high_entry_slippage_locks_without_query_params(client, tmp_path):
    _make(client)
    log_dir = tmp_path / "logs"
    # A low-priced fill ($1.00) with $0.05 absolute slippage is 500 bps,
    # far above the 15 bps default threshold, without any query override.
    _seed_trade(
        log_dir, trade_id="slip-1", entry_price=1.0, actual_entry_price=1.0,
        entry_slippage=0.05, realized_r=0.5,
    )
    res = client.get("/api/orb/strategies/ORB1/live-readiness")
    body = res.get_json()
    assert body["overall_status"] == "LOCKED"
    assert "paper_evidence_meets_thresholds" in body["failing_gates"]


def test_query_params_cannot_lower_evidence_derived_failures(client, tmp_path):
    _make(client)
    log_dir = tmp_path / "logs"
    _seed_rejection(log_dir, reason="missing_protection")
    res = client.get(
        "/api/orb/strategies/ORB1/live-readiness",
        query_string={"unresolved_protection_failures": "0"},
    )
    body = res.get_json()
    # A query param of 0 must never hide a real evidence-derived failure.
    assert "no_unresolved_protection_failures" in body["failing_gates"]


# ---------------------------------------------------------------------------
# Regression: tiny-live caps must reflect the actual live runner config
# (review feedback #2)
# ---------------------------------------------------------------------------

def test_tiny_live_caps_use_actual_live_runner_config_by_default(client):
    _make(client)
    client.application.config["autonomous_live_runner_config"] = AutonomousLiveRunnerConfig(
        max_deployable_cash_pct=0.05,  # far above MAX_TINY_LIVE_CASH_PCT (0.01)
    )
    res = client.get("/api/orb/strategies/ORB1/live-readiness")
    body = res.get_json()
    assert body["overall_status"] == "LOCKED"
    assert "tiny_live_caps_valid" in body["failing_gates"]
    assert body["tiny_live_caps"]["max_deployable_cash_pct"] == 0.05


def test_tiny_live_caps_query_override_cannot_loosen_above_config(client):
    _make(client)
    client.application.config["autonomous_live_runner_config"] = AutonomousLiveRunnerConfig(
        max_deployable_cash_pct=0.05,
    )
    res = client.get(
        "/api/orb/strategies/ORB1/live-readiness",
        query_string={"max_deployable_cash_pct": "0.5"},
    )
    body = res.get_json()
    # The query string tries to claim an even larger (looser) cap; the
    # effective cap must never exceed the real configured value.
    assert body["tiny_live_caps"]["max_deployable_cash_pct"] == 0.05


def test_tiny_live_caps_query_override_cannot_mask_unsafe_config(client):
    """A smaller query-string cap must not rescue an unsafe actual config.

    Regression for review feedback: the gate must always evaluate the real
    live-runner config cap, never a query-string value -- even one that
    looks "safer" -- so an operator cannot hide an unsafe actual
    max_deployable_cash_pct behind a small GET parameter.
    """
    _make(client)
    client.application.config["autonomous_live_runner_config"] = AutonomousLiveRunnerConfig(
        max_deployable_cash_pct=0.05,
    )
    res = client.get(
        "/api/orb/strategies/ORB1/live-readiness",
        query_string={"max_deployable_cash_pct": "0.005"},
    )
    body = res.get_json()
    assert body["overall_status"] == "LOCKED"
    assert "tiny_live_caps_valid" in body["failing_gates"]
    # The blocking gate cap must reflect the actual (unsafe) config value.
    assert body["tiny_live_caps"]["max_deployable_cash_pct"] == 0.05
    # The query override is surfaced only as a separate diagnostic.
    assert body["simulated_tiny_live_caps"]["max_deployable_cash_pct"] == 0.005


# ---------------------------------------------------------------------------
# Regression: market-data source must reflect the actual live runner config
# (review feedback #227-1)
# ---------------------------------------------------------------------------

def test_market_data_source_query_override_cannot_mask_unsafe_config(client):
    """A ``market_data_source`` query-string value must not rescue an unsafe
    actual live-runner ``live_market_data_provider``.

    Regression for review feedback: the gate must always evaluate the real
    live-runner config value, never a query-string value, so an operator
    cannot mask an unsafe actual market-data source (e.g. "yahoo") behind
    an acceptable-looking GET parameter (e.g. "ibkr").
    """
    _make(client)
    live_config = AutonomousLiveRunnerConfig()
    live_config.live_market_data_provider = "yahoo"  # unsafe actual config
    client.application.config["autonomous_live_runner_config"] = live_config
    res = client.get(
        "/api/orb/strategies/ORB1/live-readiness",
        query_string={"market_data_source": "ibkr"},
    )
    body = res.get_json()
    assert body["overall_status"] == "LOCKED"
    assert "market_data_source_acceptable" in body["failing_gates"]
    # The query override is surfaced only as a separate diagnostic.
    assert body["simulated_market_data_source"] == "ibkr"


# ---------------------------------------------------------------------------
# Regression: operator confirmation must be an explicit POST action
# (review feedback #3)
# ---------------------------------------------------------------------------

def test_get_query_string_confirmation_never_satisfies_gate(client):
    _make(client)
    res = client.get(
        "/api/orb/strategies/ORB1/live-readiness",
        query_string={"confirm_account": "true", "confirm_mode": "true"},
    )
    body = res.get_json()
    assert "operator_confirmation" in body["failing_gates"]


def test_post_confirm_endpoint_satisfies_gate_and_is_audit_logged(client, tmp_path, monkeypatch):
    _make(client)
    from web.services import get_services
    with client.application.app_context():
        svc = get_services()
    monkeypatch.setattr(type(svc), "connected", property(lambda self: True))
    monkeypatch.setattr(type(svc), "connection_info", property(lambda self: {"account": "DU12345"}))

    confirm_res = client.post(
        "/api/orb/strategies/ORB1/live-readiness/confirm",
        json={
            "mode": "tiny_live_candidate", "expected_account_id": "DU12345",
            "operator": "trader1", "notes": "reviewed evidence",
        },
    )
    assert confirm_res.status_code == 201
    assert confirm_res.get_json()["confirmed"] is True

    res = client.get("/api/orb/strategies/ORB1/live-readiness")
    body = res.get_json()
    assert "operator_confirmation" not in body["failing_gates"]

    log_files = list((tmp_path / "logs").glob("autonomous_trading_*.jsonl"))
    records = [json.loads(l) for l in log_files[0].read_text().splitlines()]
    decisions = [r for r in records if r.get("action") == "operator_decision"]
    assert decisions
    assert decisions[0]["operator"] == "trader1"
    assert decisions[0]["connected_account_id"] == "DU12345"


def test_post_confirm_mismatched_account_fails_closed(client, monkeypatch):
    _make(client)
    from web.services import get_services
    with client.application.app_context():
        svc = get_services()
    monkeypatch.setattr(type(svc), "connected", property(lambda self: True))
    monkeypatch.setattr(type(svc), "connection_info", property(lambda self: {"account": "DU99999"}))

    confirm_res = client.post(
        "/api/orb/strategies/ORB1/live-readiness/confirm",
        json={"mode": "tiny_live_candidate", "expected_account_id": "DU12345"},
    )
    assert confirm_res.get_json()["confirmed"] is False

    res = client.get("/api/orb/strategies/ORB1/live-readiness")
    body = res.get_json()
    assert "operator_confirmation" in body["failing_gates"]


def test_post_confirm_invalid_mode_rejected(client):
    _make(client)
    res = client.post(
        "/api/orb/strategies/ORB1/live-readiness/confirm",
        json={"mode": "full_live"},
    )
    assert res.status_code == 400
