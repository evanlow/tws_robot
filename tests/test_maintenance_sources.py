from __future__ import annotations

import pandas as pd
import requests

from web.maintenance.sources import sp500, sti


class _FakeResponse:
    def __init__(self, *, url: str, status_code: int, text: str) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            err = requests.HTTPError(f"HTTP Error {self.status_code}: Forbidden")
            err.response = self
            raise err


def test_sp500_retries_after_403_and_succeeds(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, headers, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(url=url, status_code=403, text="blocked")
        return _FakeResponse(url=url, status_code=200, text="<html>ok</html>")

    def fake_read_html(buf):
        assert "ok" in buf.getvalue()
        return [
            pd.DataFrame(
                {
                    "Symbol": ["abc"],
                    "Security": ["ABC Corp"],
                    "GICS Sector": ["Technology"],
                    "GICS Sub-Industry": ["Software"],
                }
            )
        ]

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("pandas.read_html", fake_read_html)

    rows = sp500.fetch_constituents()

    assert calls["count"] >= 2
    assert rows[0]["symbol"] == "ABC"


def test_sti_uses_fallback_url_when_primary_is_forbidden(monkeypatch):
    requested_urls = []

    def fake_get(url, headers, timeout):
        requested_urls.append(url)
        if "en.m.wikipedia.org" in url:
            return _FakeResponse(url=url, status_code=200, text="<html>ok</html>")
        return _FakeResponse(url=url, status_code=403, text="blocked")

    def fake_read_html(buf):
        codes = [
            "D05", "O39", "U11", "C6L", "Z74", "S68", "C38U", "A17U", "BN4", "G13",
            "C09", "C31", "H78", "J36", "U96", "S58", "Y92", "F34", "M44U", "N2IU",
            "T39", "U14", "V03", "BS6", "C07", "C52", "K71U", "ME8U", "S63", "BUOU",
        ]
        return [
            pd.DataFrame(
                {
                    "Ticker": codes,
                    "Company": [f"Company {code}" for code in codes],
                    "Sector": ["Financials"] * len(codes),
                }
            )
        ]

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("pandas.read_html", fake_read_html)

    rows = sti.fetch_constituents()

    assert rows[0]["symbol"] == "A17U.SI"
    assert len(rows) == 30
    assert any("en.m.wikipedia.org" in url for url in requested_urls)


def test_sti_ignores_stray_table_and_picks_constituents_table(monkeypatch):
    def fake_get(url, headers, timeout):
        return _FakeResponse(url=url, status_code=200, text="<html>ok</html>")

    codes = [
        "D05", "O39", "U11", "C6L", "Z74", "S68", "C38U", "A17U", "BN4", "G13",
        "C09", "C31", "H78", "J36", "U96", "S58", "Y92", "F34", "M44U", "N2IU",
        "T39", "U14", "V03", "BS6", "C07", "C52", "K71U", "ME8U", "S63", "BUOU",
    ]
    stray_table = pd.DataFrame({"Symbol": ["SGX"], "Name": ["Singapore Exchange"]})
    constituents_table = pd.DataFrame(
        {
            "Ticker": codes,
            "Company": [f"Company {code}" for code in codes],
            "Sector": ["Financials"] * len(codes),
        }
    )

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("pandas.read_html", lambda buf: [stray_table, constituents_table])

    rows = sti.fetch_constituents()

    assert len(rows) == 30
    assert "SGX.SI" not in {row["symbol"] for row in rows}


def test_sti_parses_real_wikipedia_sgx_prefixed_symbols(monkeypatch):
    """Live Wikipedia format uses a 'Stock symbol' column with 'SGX: CODE' cells."""

    def fake_get(url, headers, timeout):
        return _FakeResponse(url=url, status_code=200, text="<html>ok</html>")

    codes = [
        "A17U", "C38U", "9CI", "C09", "D05", "D01", "J69U", "BUOU", "5E2", "AJBU",
        "BN4", "BS6", "C6L", "F34", "G13", "H78", "J36", "M44U", "ME8U", "N2IU",
        "O39", "S58", "S63", "S68", "U11", "U14", "U96", "V03", "Y92", "Z74",
    ]
    constituents_table = pd.DataFrame(
        {
            "Stock symbol": [f"SGX: {code}" for code in codes],
            "Company": [f"Company {code}" for code in codes],
        }
    )

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("pandas.read_html", lambda buf: [constituents_table])

    rows = sti.fetch_constituents()

    symbols = {row["symbol"] for row in rows}
    assert len(rows) == 30
    # Every distinct code must survive; no collapse to the 'SGX' exchange token.
    assert "SGX.SI" not in symbols
    assert "9CI.SI" in symbols  # digit-leading code
    assert "5E2.SI" in symbols
    assert "A17U.SI" in symbols
