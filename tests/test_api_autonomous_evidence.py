from datetime import datetime, timedelta, timezone

from web import create_app


class _FakeEvidenceStore:
    def recent(self, limit=100):
        return [
            {
                "schema_version": 1,
                "evidence_type": "autonomous_decision",
                "status": "recommended",
                "symbol": "AAA",
                "limit_seen": limit,
            }
        ]


BASE = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def _outcome(r_value, *, index=0, symbol="AAA"):
    return {
        "schema_version": 3,
        "evidence_type": "autonomous_outcome",
        "timestamp": (BASE + timedelta(minutes=index)).isoformat(),
        "mode": "paper",
        "symbol": symbol,
        "strategy_bucket": {
            "signal_label": "Confirmed Rebound",
            "quality_label": "Strong",
            "momentum_label": "Confirmed Rebound",
            "market_classification": "Bullish / Volatility Acceptable",
            "vix_level_regime": "normal",
            "vix_direction_regime": "falling",
            "sector": "Technology",
        },
        "selected": {
            "features": {
                "sector_regime": "sector_supportive",
                "time_of_day_regime": "regular_session",
                "support_distance_pct": 0.02,
                "resistance_room_pct": 0.12,
                "adr_pct": 0.035,
            },
        },
        "trade_plan": {"symbol": symbol, "trade_type": "BUY_SHARES"},
        "outcome": {
            "realized": True,
            "realized_r_multiple": r_value,
            "realized_pnl": r_value * 100,
        },
    }


class _FakeLearningEvidenceStore:
    def recent(self, limit=1000):
        records = (
            [_outcome(1.0, index=i) for i in range(6)]
            + [_outcome(-1.0, index=6 + i) for i in range(4)]
        )
        return records[:limit]


def _app(monkeypatch, store):
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    monkeypatch.setattr(
        "web.routes.api_connection.is_accepted",
        lambda: True,
    )
    import web.routes.api_autonomous_evidence as evidence_route
    monkeypatch.setattr(evidence_route, "_evidence_store", lambda: store)
    return create_app(
        {"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False}
    )


def test_recent_evidence_api_returns_records(monkeypatch):
    app = _app(monkeypatch, _FakeEvidenceStore())
    client = app.test_client()

    resp = client.get("/api/autonomous/evidence?limit=5")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 1
    assert body["records"][0]["symbol"] == "AAA"
    assert body["records"][0]["limit_seen"] == 5


def test_learning_status_api_returns_el8_sections(monkeypatch):
    app = _app(monkeypatch, _FakeLearningEvidenceStore())
    client = app.test_client()

    resp = client.get("/api/autonomous/evidence/learning-status?recent_trades=4&min_trades=3")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["safety_notes"]["read_only"] is True
    assert body["setup_performance"]["count"] == 1
    assert body["weak_setups"]["count"] == 1
    assert body["drift_report"]["count"] == 1
    assert body["promotion_report"]["operator_approval_required"] is True
    assert body["promotion_report"]["automatic_capital_scaling_allowed"] is False


def test_setup_performance_api_returns_setup_table(monkeypatch):
    app = _app(monkeypatch, _FakeLearningEvidenceStore())
    client = app.test_client()

    resp = client.get("/api/autonomous/evidence/setup-performance")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 1
    setup = body["setups"][0]
    assert setup["setup_id"].startswith("setup_v1__")
    assert setup["trade_count"] == 10
    assert "current_allowed_mode" in setup
    assert "recommended_capital_level" in setup


def test_promotion_weak_and_drift_apis_are_read_only(monkeypatch):
    app = _app(monkeypatch, _FakeLearningEvidenceStore())
    client = app.test_client()

    promotion = client.get("/api/autonomous/evidence/promotion-report").get_json()
    weak = client.get("/api/autonomous/evidence/weak-setups").get_json()
    drift = client.get(
        "/api/autonomous/evidence/drift-report?recent_trades=4&min_trades=3"
    ).get_json()

    assert promotion["operator_approval_required"] is True
    assert promotion["automatic_capital_scaling_allowed"] is False
    assert weak["count"] == 1
    assert weak["setups"][0]["recommended_size_state"] == "PAPER_ONLY"
    assert drift["count"] == 1
    assert drift["setups"][0]["direction"] == "weakening"
