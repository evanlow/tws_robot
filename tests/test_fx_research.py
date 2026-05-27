"""Tests for FX Research Dashboard route and service."""

import re

import pytest

from web import create_app
from web.fx_signal_service import get_fx_dashboard_data


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as c:
        yield c


class TestFxSignalService:
    """Unit tests for get_fx_dashboard_data."""

    def test_returns_all_sections(self):
        data = get_fx_dashboard_data()
        assert "data_status" in data
        assert "market_watch" in data
        assert "sneer_proxy" in data
        assert "mas_policy" in data
        assert "macro_pressure" in data
        assert "signal_summary" in data

    def test_data_status_not_configured(self):
        data = get_fx_dashboard_data()
        status = data["data_status"]
        assert status["data_mode"] == "Not Configured"
        assert status["execution_status"] == "Disabled"
        assert status["live_trading"] == "Disabled"
        assert status["order_placement"] == "Disabled"

    def test_market_watch_unavailable(self):
        data = get_fx_dashboard_data()
        assert data["market_watch"]["available"] is False
        assert "No live FX data source configured" in data["market_watch"]["message"]
        assert data["market_watch"]["items"] == []

    def test_sneer_proxy_unavailable(self):
        data = get_fx_dashboard_data()
        assert data["sneer_proxy"]["available"] is False
        assert "No S$NEER data source configured" in data["sneer_proxy"]["message"]

    def test_mas_policy_unavailable(self):
        data = get_fx_dashboard_data()
        assert data["mas_policy"]["available"] is False
        assert "No MAS policy data source configured" in data["mas_policy"]["message"]

    def test_macro_pressure_unavailable(self):
        data = get_fx_dashboard_data()
        assert data["macro_pressure"]["available"] is False
        assert "No macro data source configured" in data["macro_pressure"]["message"]

    def test_signal_summary_unavailable(self):
        data = get_fx_dashboard_data()
        assert data["signal_summary"]["available"] is False
        assert "Signal unavailable" in data["signal_summary"]["message"]


class TestFxResearchRoute:
    """Integration tests for the /fx route."""

    def test_fx_route_returns_200(self, client):
        resp = client.get("/fx/")
        assert resp.status_code == 200

    def test_fx_route_renders_all_sections(self, client):
        resp = client.get("/fx/")
        html = resp.data.decode()
        assert "FX Market Watch" in html
        assert "NEER Proxy Monitor" in html
        assert "MAS Policy Console" in html
        assert "Macro Pressure Monitor" in html
        assert "Research Signal Summary" in html

    def test_fx_route_shows_research_disclaimer(self, client):
        resp = client.get("/fx/")
        html = resp.data.decode()
        assert "Research Only" in html
        assert "does not place orders" in html

    def test_fx_route_shows_data_status_banner(self, client):
        resp = client.get("/fx/")
        html = resp.data.decode()
        assert "Data Mode:" in html
        assert "Not Configured" in html
        assert "Execution Status:" in html
        assert "Disabled" in html

    def test_fx_route_shows_empty_states(self, client):
        resp = client.get("/fx/")
        html = resp.data.decode()
        assert "No live FX data source configured" in html
        assert "No S$NEER data source configured" in html
        assert "No MAS policy data source configured" in html
        assert "No macro data source configured" in html
        assert "Signal unavailable" in html

    def test_fx_route_renders_market_watch_items_when_available(self, client, monkeypatch):
        monkeypatch.setattr(
            "web.routes.fx_research.get_fx_dashboard_data",
            lambda: {
                "data_status": {
                    "data_mode": "Configured",
                    "execution_status": "Disabled",
                    "live_trading": "Disabled",
                    "order_placement": "Disabled",
                },
                "market_watch": {
                    "available": True,
                    "items": [
                        {
                            "pair": "USD/SGD",
                            "last_price": 1.3512,
                            "daily_change_pct": 0.12,
                            "signal_bias": "Neutral",
                            "notes": "Test note",
                        }
                    ],
                },
                "sneer_proxy": {"available": False, "message": "No S$NEER data source configured."},
                "mas_policy": {"available": False, "message": "No MAS policy data source configured."},
                "macro_pressure": {"available": False, "message": "No macro data source configured."},
                "signal_summary": {
                    "available": False,
                    "message": "Signal unavailable until required data sources are configured.",
                },
            },
        )

        resp = client.get("/fx/")

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "USD/SGD" in html
        assert "1.3512" in html
        assert "Test note" in html

    def test_fx_route_no_hardcoded_mock_values(self, client):
        resp = client.get("/fx/")
        html = resp.data.decode()
        # Must not contain previous hardcoded mock values
        assert "1.3245" not in html
        assert "1.4532" not in html
        assert "101.45" not in html
        assert "101.20" not in html
        assert "62%" not in html
        assert "USD weakening on dovish Fed expectations" not in html

    def test_fx_route_no_order_buttons(self, client):
        resp = client.get("/fx/")
        html = resp.data.decode()
        # Ensure no order execution elements exist
        buttons = re.findall(r"<button[^>]*>", html, flags=re.IGNORECASE)
        assert all(
            "emergencyBtn" in button
            or "btn-emergency" in button
            or "nav-dropdown-toggle" in button
            for button in buttons
        )
        assert 'type="submit"' not in html.lower()

    def test_fx_redirect_from_no_trailing_slash(self, client):
        resp = client.get("/fx")
        assert resp.status_code in {301, 302, 307, 308}
        assert resp.headers["Location"].endswith("/fx/")
