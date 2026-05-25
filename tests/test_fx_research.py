"""Tests for FX Research Dashboard route and service."""

import pytest

from web import create_app
from web.fx_signal_service import get_fx_dashboard_data


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as c:
        yield c


class TestFxSignalService:
    """Unit tests for get_fx_dashboard_data."""

    def test_returns_all_sections(self):
        data = get_fx_dashboard_data()
        assert "market_watch" in data
        assert "sneer_proxy" in data
        assert "mas_policy" in data
        assert "macro_pressure" in data
        assert "signal_summary" in data

    def test_market_watch_has_seven_pairs(self):
        data = get_fx_dashboard_data()
        assert len(data["market_watch"]) == 7
        pairs = [item["pair"] for item in data["market_watch"]]
        assert "USD/SGD" in pairs
        assert "EUR/SGD" in pairs
        assert "JPY/SGD" in pairs
        assert "CNH/SGD" in pairs
        assert "MYR/SGD" in pairs
        assert "AUD/SGD" in pairs
        assert "GBP/SGD" in pairs

    def test_market_watch_item_fields(self):
        data = get_fx_dashboard_data()
        item = data["market_watch"][0]
        assert "pair" in item
        assert "last_price" in item
        assert "daily_change_pct" in item
        assert "signal_bias" in item
        assert "notes" in item

    def test_sneer_proxy_fields(self):
        data = get_fx_dashboard_data()
        proxy = data["sneer_proxy"]
        assert "estimated_sneer_proxy" in proxy
        assert "latest_official_sneer" in proxy
        assert "estimated_band_zone" in proxy
        assert "proxy_deviation_pct" in proxy
        assert "confidence" in proxy
        assert "disclaimer" in proxy
        assert "research estimates only" in proxy["disclaimer"]

    def test_signal_summary_fields(self):
        data = get_fx_dashboard_data()
        summary = data["signal_summary"]
        assert "overall_fx_bias" in summary
        assert "confidence_score" in summary
        assert "suggested_action" in summary
        assert "explanation" in summary


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

    def test_fx_route_shows_fx_pairs(self, client):
        resp = client.get("/fx/")
        html = resp.data.decode()
        assert "USD/SGD" in html
        assert "EUR/SGD" in html
        assert "GBP/SGD" in html

    def test_fx_route_no_order_buttons(self, client):
        resp = client.get("/fx/")
        html = resp.data.decode()
        # Ensure no order execution elements exist
        assert '<button' not in html.lower() or 'emergency' in html.lower()
        assert 'type="submit"' not in html.lower()

    def test_fx_redirect_from_no_trailing_slash(self, client):
        resp = client.get("/fx")
        assert resp.status_code == 308  # Redirect to /fx/
