"""Tests for FX Research Dashboard route and service."""

import re

import pytest

from web import create_app
from web.fx_signal_service import get_fx_dashboard_data


def _assert_no_order_ui(html: str) -> None:
    """Assert the rendered HTML contains no order submission UI elements."""
    buttons = re.findall(r"<button[^>]*>", html, flags=re.IGNORECASE)
    assert all(
        "emergencyBtn" in button
        or "btn-emergency" in button
        or "nav-dropdown-toggle" in button
        for button in buttons
    )
    assert 'type="submit"' not in html.lower()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as c:
        yield c


class TestFxSignalService:
    """Unit tests for get_fx_dashboard_data (not_configured mode)."""

    @pytest.fixture(autouse=True)
    def ensure_not_configured(self, monkeypatch):
        monkeypatch.delenv("FX_DATA_MODE", raising=False)

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


class TestFxSignalServiceDemoMode:
    """Unit tests for get_fx_dashboard_data in demo mode."""

    @pytest.fixture(autouse=True)
    def set_demo_mode(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "demo")

    def test_data_status_demo_mode(self):
        data = get_fx_dashboard_data()
        status = data["data_status"]
        assert status["data_mode"] == "Demo Research Data"
        assert status["execution_status"] == "Disabled"
        assert status["live_trading"] == "Disabled"
        assert status["order_placement"] == "Disabled"

    def test_market_watch_demo_pairs(self):
        data = get_fx_dashboard_data()
        mw = data["market_watch"]
        assert mw["available"] is True
        pairs = [item["pair"] for item in mw["items"]]
        for expected in ["USD/SGD", "EUR/SGD", "GBP/SGD", "JPY/SGD", "AUD/SGD", "USD/CNH", "USD/JPY", "EUR/USD"]:
            assert expected in pairs

    def test_market_watch_demo_item_fields(self):
        data = get_fx_dashboard_data()
        for item in data["market_watch"]["items"]:
            assert "pair" in item
            assert "last_price" in item
            assert "daily_change_pct" in item
            assert "weekly_change_pct" in item
            assert "signal_bias" in item
            assert "notes" in item

    def test_sneer_proxy_demo(self):
        data = get_fx_dashboard_data()
        sp = data["sneer_proxy"]
        assert sp["available"] is True
        assert "proxy_index" in sp
        assert "change_1d" in sp
        assert "change_20d" in sp
        assert "z_score" in sp
        assert "interpretation" in sp
        assert "proxy" in sp["note"].lower() or "estimate" in sp["note"].lower()

    def test_mas_policy_demo(self):
        data = get_fx_dashboard_data()
        mp = data["mas_policy"]
        assert mp["available"] is True
        assert "latest_stance" in mp
        assert "next_review_window" in mp
        assert "inflation_assessment" in mp
        assert "growth_assessment" in mp
        assert "sgd_policy_bias" in mp
        assert "notes" in mp

    def test_macro_pressure_demo_items(self):
        data = get_fx_dashboard_data()
        macro = data["macro_pressure"]
        assert macro["available"] is True
        assert len(macro["items"]) >= 3
        for item in macro["items"]:
            assert "name" in item
            assert "current_value" in item
            assert "direction" in item
            assert "sgd_impact" in item
            assert "notes" in item

    def test_signal_summary_demo_items(self):
        data = get_fx_dashboard_data()
        ss = data["signal_summary"]
        assert ss["available"] is True
        assert len(ss["items"]) >= 3
        for item in ss["items"]:
            assert "instrument" in item
            assert "bias" in item
            assert "confidence" in item
            assert "time_horizon" in item
            assert "supporting_factors" in item
            assert "invalidation_level" in item
            assert "risk_notes" in item

    def test_order_placement_disabled_in_demo(self):
        data = get_fx_dashboard_data()
        assert data["data_status"]["order_placement"] == "Disabled"
        assert data["data_status"]["live_trading"] == "Disabled"
        assert data["data_status"]["execution_status"] == "Disabled"


class TestFxResearchRoute:
    """Integration tests for the /fx route (not_configured mode)."""

    @pytest.fixture(autouse=True)
    def ensure_not_configured(self, monkeypatch):
        monkeypatch.delenv("FX_DATA_MODE", raising=False)

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
        _assert_no_order_ui(resp.data.decode())

    def test_fx_redirect_from_no_trailing_slash(self, client):
        resp = client.get("/fx")
        assert resp.status_code in {301, 302, 307, 308}
        assert resp.headers["Location"].endswith("/fx/")


class TestFxResearchRouteDemoMode:
    """Integration tests for the /fx route in demo mode."""

    @pytest.fixture
    def demo_client(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "demo")
        monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
        app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
        with app.test_client() as c:
            yield c

    def test_demo_mode_shows_data_mode_label(self, demo_client):
        resp = demo_client.get("/fx/")
        html = resp.data.decode()
        assert "Demo Research Data" in html

    def test_demo_mode_shows_market_watch_pairs(self, demo_client):
        resp = demo_client.get("/fx/")
        html = resp.data.decode()
        for pair in ["USD/SGD", "EUR/SGD", "GBP/SGD", "JPY/SGD", "AUD/SGD"]:
            assert pair in html

    def test_demo_mode_shows_sneer_proxy_content(self, demo_client):
        resp = demo_client.get("/fx/")
        html = resp.data.decode()
        assert "proxy" in html.lower()
        assert "estimate" in html.lower()

    def test_demo_mode_shows_mas_policy_content(self, demo_client):
        resp = demo_client.get("/fx/")
        html = resp.data.decode()
        assert "MAS Policy Console" in html
        assert "Upcoming semi-annual MAS policy statement" in html

    def test_demo_mode_shows_macro_factors(self, demo_client):
        resp = demo_client.get("/fx/")
        html = resp.data.decode()
        assert "US 2Y Yield" in html
        assert "DXY" in html

    def test_demo_mode_shows_research_signals(self, demo_client):
        resp = demo_client.get("/fx/")
        html = resp.data.decode()
        assert "Bearish USD/SGD" in html

    def test_demo_mode_order_placement_disabled(self, demo_client):
        resp = demo_client.get("/fx/")
        html = resp.data.decode()
        assert "Disabled" in html
        assert 'type="submit"' not in html.lower()

    def test_demo_mode_no_order_buttons(self, demo_client):
        resp = demo_client.get("/fx/")
        _assert_no_order_ui(resp.data.decode())

    def test_demo_mode_research_disclaimer(self, demo_client):
        resp = demo_client.get("/fx/")
        html = resp.data.decode()
        assert "research output only" in html.lower()
        assert "not trading advice" in html.lower()


class TestFxResearchRouteLiveResearchMode:
    """Integration tests for the /fx route in live_research mode."""

    @pytest.fixture
    def live_research_client(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "live_research")
        monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
        app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
        with app.test_client() as c:
            yield c

    def test_live_research_route_returns_200(self, live_research_client):
        resp = live_research_client.get("/fx/")
        assert resp.status_code == 200

    def test_live_research_shows_data_mode_label(self, live_research_client):
        resp = live_research_client.get("/fx/")
        html = resp.data.decode()
        assert "Live Research (Unavailable)" in html

    def test_live_research_execution_statuses_disabled(self, live_research_client):
        resp = live_research_client.get("/fx/")
        html = resp.data.decode()
        assert "Disabled" in html

    def test_live_research_no_order_buttons(self, live_research_client):
        resp = live_research_client.get("/fx/")
        _assert_no_order_ui(resp.data.decode())


class TestFxResearchRouteInvalidMode:
    """Integration tests for the /fx route with an invalid FX_DATA_MODE."""

    @pytest.fixture
    def invalid_mode_client(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "totally_invalid")
        monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
        app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
        with app.test_client() as c:
            yield c

    def test_invalid_mode_route_returns_200(self, invalid_mode_client):
        resp = invalid_mode_client.get("/fx/")
        assert resp.status_code == 200

    def test_invalid_mode_shows_not_configured(self, invalid_mode_client):
        resp = invalid_mode_client.get("/fx/")
        html = resp.data.decode()
        assert "Not Configured" in html

    def test_invalid_mode_execution_statuses_disabled(self, invalid_mode_client):
        resp = invalid_mode_client.get("/fx/")
        html = resp.data.decode()
        assert "Disabled" in html

    def test_invalid_mode_no_order_buttons(self, invalid_mode_client):
        resp = invalid_mode_client.get("/fx/")
        _assert_no_order_ui(resp.data.decode())
