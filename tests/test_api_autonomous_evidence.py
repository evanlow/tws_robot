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


def test_recent_evidence_api_returns_records(monkeypatch):
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    monkeypatch.setattr(
        "web.routes.api_connection.is_accepted",
        lambda: True,
    )
    import web.routes.api_autonomous_evidence as evidence_route
    monkeypatch.setattr(evidence_route, "_evidence_store", lambda: _FakeEvidenceStore())

    app = create_app(
        {"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False}
    )
    client = app.test_client()

    resp = client.get("/api/autonomous/evidence?limit=5")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 1
    assert body["records"][0]["symbol"] == "AAA"
    assert body["records"][0]["limit_seen"] == 5
