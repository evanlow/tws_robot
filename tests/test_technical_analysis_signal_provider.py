"""Tests for ``autonomous.technical_analysis_signal_provider``."""

from __future__ import annotations

import pytest

from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.technical_analysis_signal_provider import (
    STRONG_REBOUND_STRENGTH_SCORE,
    TechnicalAnalysisSignalProvider,
)


def _row(symbol="AAA", momentum="Confirmed Rebound", quality="Strong",
         current_price=100.0, bollinger_status="near_lower_band", **extra):
    row = {
        "symbol": symbol,
        "company": symbol + " Inc.",
        "sector": "Tech",
        "current_price": current_price,
        "bollinger_status": bollinger_status,
        "momentum_label": momentum,
        "momentum_confirmation": "confirmed_rebound" if momentum == "Confirmed Rebound" else None,
        "momentum_reasons": ["Price above 5-day MA"],
        "quality_label": quality,
        "quality_score": 80,
        "quality_reasons": ["Positive revenue growth"],
        "rsi_14": 45,
        "rsi_status": "rsi_neutral",
    }
    row.update(extra)
    return row


class _StubScreener:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def get_screener_data(self, refresh=False):
        self.calls += 1
        return {"rows": self.rows}


class TestQualifyingRows:
    def test_strong_confirmed_rebound_returns_qualifying_signal(self):
        screener = _StubScreener([_row("AAA")])
        provider = TechnicalAnalysisSignalProvider(
            screener_service=screener, refresh_on_first_call=False
        )
        sig = provider.analyze("AAA")
        assert sig is not None
        assert sig.symbol == "AAA"
        assert sig.strength_score == STRONG_REBOUND_STRENGTH_SCORE
        assert sig.strength_score >= 100
        assert sig.signal_label == "Confirmed Rebound"
        assert sig.last_price == 100.0
        # Mapped through to extras so the audit log keeps the original
        # screener context.
        assert sig.extras["quality_label"] == "Strong"
        assert sig.extras["momentum_label"] == "Confirmed Rebound"

    def test_case_insensitive_symbol_lookup(self):
        screener = _StubScreener([_row("aapl")])
        provider = TechnicalAnalysisSignalProvider(
            screener_service=screener, refresh_on_first_call=False
        )
        sig = provider.analyze("AAPL")
        assert sig is not None and sig.symbol == "AAPL"


class TestNonQualifyingRows:
    def test_non_strong_quality_returns_low_strength_signal(self):
        # Returns a CandidateSignal so the ranker records a clear
        # rejection reason rather than silently dropping the row.
        screener = _StubScreener([_row("AAA", quality="Moderate")])
        provider = TechnicalAnalysisSignalProvider(
            screener_service=screener, refresh_on_first_call=False
        )
        sig = provider.analyze("AAA")
        assert sig is not None
        assert sig.strength_score == 0
        # The momentum label is preserved so it's clear it was the
        # quality side that disqualified the candidate.
        assert sig.signal_label == "Confirmed Rebound"

    def test_no_momentum_label_returns_low_strength_signal(self):
        screener = _StubScreener([_row("AAA", momentum="Failed Bounce")])
        provider = TechnicalAnalysisSignalProvider(
            screener_service=screener, refresh_on_first_call=False
        )
        sig = provider.analyze("AAA")
        assert sig is not None
        assert sig.strength_score == 0
        assert sig.signal_label == "Failed Bounce"

    def test_insufficient_data_returns_none(self):
        screener = _StubScreener([_row("AAA", bollinger_status="insufficient_data")])
        provider = TechnicalAnalysisSignalProvider(
            screener_service=screener, refresh_on_first_call=False
        )
        assert provider.analyze("AAA") is None

    def test_unknown_symbol_returns_none(self):
        screener = _StubScreener([_row("AAA")])
        provider = TechnicalAnalysisSignalProvider(
            screener_service=screener, refresh_on_first_call=False
        )
        assert provider.analyze("MISSING") is None


class TestFailureSafety:
    def test_screener_exception_falls_back_to_no_rows(self):
        class _Raises:
            def get_screener_data(self, refresh=False):
                raise RuntimeError("yfinance exploded")

        provider = TechnicalAnalysisSignalProvider(
            screener_service=_Raises(), refresh_on_first_call=False
        )
        # Must not propagate; subsequent lookups return None.
        assert provider.analyze("AAA") is None
        assert provider.analyze("BBB") is None

    def test_try_build_swallows_construction_errors(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("nope")

        monkeypatch.setattr(
            TechnicalAnalysisSignalProvider, "__init__", _boom
        )
        assert TechnicalAnalysisSignalProvider.try_build() is None


class TestScannerIntegration:
    def test_scanner_iterates_provider_without_crashing(self):
        screener = _StubScreener([_row("AAA"), _row("BBB", quality="Weak")])
        provider = TechnicalAnalysisSignalProvider(
            screener_service=screener, refresh_on_first_call=False
        )
        scanner = CandidateScanner(
            signal_provider=provider,
            symbols=[
                {"symbol": "AAA", "security": "AAA Inc.", "sector": "X", "sub_industry": ""},
                {"symbol": "BBB", "security": "BBB Inc.", "sector": "X", "sub_industry": ""},
                {"symbol": "MISS", "security": "Missing", "sector": "X", "sub_industry": ""},
            ],
        )
        results = scanner.scan()
        # Two of three symbols return a CandidateSignal (one qualifies,
        # one is a low-strength rejection candidate); the unknown row
        # is silently skipped.
        symbols = {sig.symbol for sig in results}
        assert symbols == {"AAA", "BBB"}
        # Only AAA actually qualifies under the engine's hard filters.
        qualifying = [s for s in results if s.strength_score >= 100]
        assert [s.symbol for s in qualifying] == ["AAA"]
