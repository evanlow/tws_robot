"""
Tests for the PositionAnalyzer service.

Covers strategy deduction from TWS positions including:
- Long/short equity positions
- Covered calls
- Protective puts
- Bull/bear call/put spreads
- Iron condors
- Straddles and strangles
- Edge cases (empty positions, unparseable symbols)
"""

import pytest

from web.services.position_analyzer import (
    InferredStrategy,
    PositionAnalyzer,
    _parse_option_symbol,
    _equity_targets,
    _underlying_for,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stock_pos(qty=100, entry=150.0, current=155.0, side="LONG"):
    """Build a minimal stock position dict."""
    return {
        "quantity": qty if side == "LONG" else -qty,
        "entry_price": entry,
        "current_price": current,
        "market_value": qty * current * (1 if side == "LONG" else -1),
        "unrealized_pnl": (current - entry) * qty * (1 if side == "LONG" else -1),
        "side": side,
        "sec_type": "STK",
    }


def _option_pos(qty=1, entry=5.0, current=3.0, side="SHORT", sec_type="OPT"):
    """Build a minimal option position dict."""
    return {
        "quantity": qty if side == "LONG" else -qty,
        "entry_price": entry,
        "current_price": current,
        "market_value": qty * current * 100 * (1 if side == "LONG" else -1),
        "unrealized_pnl": (current - entry) * qty * 100 * (1 if side == "LONG" else -1),
        "side": side,
        "sec_type": sec_type,
    }


# ---------------------------------------------------------------------------
# Option symbol parsing
# ---------------------------------------------------------------------------

class TestOptionSymbolParsing:

    def test_compact_call(self):
        parsed = _parse_option_symbol("AAPL250620C200")
        assert parsed is not None
        assert parsed["underlying"] == "AAPL"
        assert parsed["expiry"] == "250620"
        assert parsed["right"] == "C"
        assert parsed["strike"] == 200.0

    def test_compact_put(self):
        parsed = _parse_option_symbol("MSFT250718P300.5")
        assert parsed is not None
        assert parsed["underlying"] == "MSFT"
        assert parsed["right"] == "P"
        assert parsed["strike"] == 300.5

    def test_occ_format(self):
        """OCC-style: AAPL  250620C00200000  (8-digit strike / 1000)"""
        parsed = _parse_option_symbol("AAPL  250620C00200000")
        assert parsed is not None
        assert parsed["underlying"] == "AAPL"
        assert parsed["strike"] == 200.0

    def test_non_option_returns_none(self):
        assert _parse_option_symbol("AAPL") is None
        assert _parse_option_symbol("") is None

    def test_underlying_for_stock(self):
        assert _underlying_for("AAPL", {}) == "AAPL"

    def test_underlying_for_option(self):
        assert _underlying_for("AAPL250620C200", {}) == "AAPL"


# ---------------------------------------------------------------------------
# Equity target calculation
# ---------------------------------------------------------------------------

class TestEquityTargets:

    def test_long_targets(self):
        targets = _equity_targets({"entry_price": 100.0, "side": "LONG"})
        assert targets["stop_loss_price"] == 95.0
        assert targets["profit_target_price"] == 110.0
        assert targets["trailing_stop_pct"] == 0.05

    def test_short_targets(self):
        targets = _equity_targets({"entry_price": 100.0, "side": "SHORT"})
        assert targets["stop_loss_price"] == 105.0
        assert targets["profit_target_price"] == 90.0

    def test_zero_entry(self):
        targets = _equity_targets({"entry_price": 0, "side": "LONG"})
        assert targets == {}


# ---------------------------------------------------------------------------
# PositionAnalyzer
# ---------------------------------------------------------------------------

class TestPositionAnalyzer:

    def setup_method(self):
        self.analyzer = PositionAnalyzer()

    # ---- empty / trivial --------------------------------------------------

    def test_empty_positions(self):
        assert self.analyzer.analyze({}) == []

    # ---- single stock -----------------------------------------------------

    def test_long_equity(self):
        positions = {
            "AAPL": _stock_pos(100, 150.0, 155.0, "LONG"),
        }
        results = self.analyzer.analyze(positions)
        assert len(results) == 1
        r = results[0]
        assert r.strategy_type == "LongEquity"
        assert r.symbols == ["AAPL"]
        assert r.confidence >= 0.9
        assert "stop_loss_price" in r.targets
        assert "profit_target_price" in r.targets

    def test_short_equity(self):
        positions = {
            "TSLA": _stock_pos(50, 300.0, 280.0, "SHORT"),
        }
        results = self.analyzer.analyze(positions)
        assert len(results) == 1
        assert results[0].strategy_type == "ShortEquity"

    # ---- covered call -----------------------------------------------------

    def test_covered_call(self):
        positions = {
            "AAPL": _stock_pos(100, 150.0, 155.0, "LONG"),
            "AAPL250620C200": _option_pos(1, 5.0, 3.0, "SHORT"),
        }
        results = self.analyzer.analyze(positions)
        # Should detect CoveredCall, not separate LongEquity + ShortCall
        types = [r.strategy_type for r in results]
        assert "CoveredCall" in types
        cc = [r for r in results if r.strategy_type == "CoveredCall"][0]
        assert "AAPL" in cc.symbols
        assert len(cc.positions) == 2
        # Targets should include profit_target_price (the call strike)
        assert cc.targets.get("profit_target_price") == 200.0

    # ---- protective put ---------------------------------------------------

    def test_protective_put(self):
        positions = {
            "MSFT": _stock_pos(100, 300.0, 310.0, "LONG"),
            "MSFT250620P280": _option_pos(1, 4.0, 5.0, "LONG"),
        }
        results = self.analyzer.analyze(positions)
        types = [r.strategy_type for r in results]
        assert "ProtectivePut" in types
        pp = [r for r in results if r.strategy_type == "ProtectivePut"][0]
        assert pp.targets.get("stop_loss_price") == 280.0

    # ---- bull call spread -------------------------------------------------

    def test_bull_call_spread(self):
        positions = {
            "AAPL250620C150": _option_pos(1, 10.0, 12.0, "LONG"),
            "AAPL250620C170": _option_pos(1, 3.0, 2.0, "SHORT"),
        }
        results = self.analyzer.analyze(positions)
        types = [r.strategy_type for r in results]
        assert "BullCallSpread" in types
        bcs = [r for r in results if r.strategy_type == "BullCallSpread"][0]
        assert bcs.targets.get("spread_width") == 20.0
        assert "max_profit" in bcs.targets
        assert "max_loss" in bcs.targets

    # ---- bear put spread --------------------------------------------------

    def test_bear_put_spread(self):
        positions = {
            "SPY250620P420": _option_pos(1, 8.0, 10.0, "LONG"),
            "SPY250620P400": _option_pos(1, 3.0, 2.0, "SHORT"),
        }
        results = self.analyzer.analyze(positions)
        types = [r.strategy_type for r in results]
        assert "BearPutSpread" in types

    # ---- bull put spread (credit) -----------------------------------------

    def test_bull_put_spread(self):
        positions = {
            "QQQ250620P350": _option_pos(1, 6.0, 4.0, "SHORT"),
            "QQQ250620P330": _option_pos(1, 2.0, 1.5, "LONG"),
        }
        results = self.analyzer.analyze(positions)
        types = [r.strategy_type for r in results]
        assert "BullPutSpread" in types

    # ---- iron condor ------------------------------------------------------

    def test_iron_condor(self):
        positions = {
            "SPY250620C450": _option_pos(1, 3.0, 2.0, "SHORT"),   # short call
            "SPY250620C460": _option_pos(1, 1.0, 0.5, "LONG"),    # long call (higher)
            "SPY250620P400": _option_pos(1, 3.0, 2.0, "SHORT"),   # short put
            "SPY250620P390": _option_pos(1, 1.0, 0.5, "LONG"),    # long put (lower)
        }
        results = self.analyzer.analyze(positions)
        types = [r.strategy_type for r in results]
        assert "IronCondor" in types
        ic = [r for r in results if r.strategy_type == "IronCondor"][0]
        assert len(ic.positions) == 4

    # ---- straddle ---------------------------------------------------------

    def test_straddle(self):
        positions = {
            "AAPL250620C200": _option_pos(1, 8.0, 10.0, "LONG"),
            "AAPL250620P200": _option_pos(1, 7.0, 6.0, "LONG"),
        }
        results = self.analyzer.analyze(positions)
        types = [r.strategy_type for r in results]
        assert "Straddle" in types

    # ---- strangle ---------------------------------------------------------

    def test_strangle(self):
        positions = {
            "AAPL250620C210": _option_pos(1, 5.0, 6.0, "LONG"),
            "AAPL250620P190": _option_pos(1, 4.0, 3.0, "LONG"),
        }
        results = self.analyzer.analyze(positions)
        types = [r.strategy_type for r in results]
        assert "Strangle" in types

    # ---- naked option (no matching pattern) -------------------------------

    def test_naked_short_call(self):
        positions = {
            "TSLA250620C500": _option_pos(1, 10.0, 8.0, "SHORT"),
        }
        results = self.analyzer.analyze(positions)
        assert len(results) == 1
        assert results[0].strategy_type == "ShortCall"

    def test_naked_long_put(self):
        positions = {
            "TSLA250620P250": _option_pos(1, 5.0, 7.0, "LONG"),
        }
        results = self.analyzer.analyze(positions)
        assert len(results) == 1
        assert results[0].strategy_type == "LongPut"

    # ---- multiple underlyings ---------------------------------------------

    def test_multiple_underlyings(self):
        positions = {
            "AAPL": _stock_pos(100, 150.0, 155.0, "LONG"),
            "MSFT": _stock_pos(200, 300.0, 310.0, "LONG"),
        }
        results = self.analyzer.analyze(positions)
        assert len(results) == 2
        symbols = [r.symbols[0] for r in results]
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    # ---- mixed stock + options for different underlyings -------------------

    def test_mixed_portfolio(self):
        positions = {
            "AAPL": _stock_pos(100, 150.0, 155.0, "LONG"),
            "AAPL250620C200": _option_pos(1, 5.0, 3.0, "SHORT"),
            "MSFT": _stock_pos(200, 300.0, 310.0, "LONG"),
        }
        results = self.analyzer.analyze(positions)
        types = [r.strategy_type for r in results]
        assert "CoveredCall" in types
        assert "LongEquity" in types
        # AAPL should be CoveredCall, MSFT should be LongEquity
        msft_strats = [r for r in results if "MSFT" in r.symbols]
        assert msft_strats[0].strategy_type == "LongEquity"


# ---------------------------------------------------------------------------
# InferredStrategy dataclass
# ---------------------------------------------------------------------------

class TestInferredStrategy:

    def test_to_dict(self):
        inf = InferredStrategy(
            id="test_1",
            strategy_type="LongEquity",
            description="Long AAPL",
            confidence=0.95,
            symbols=["AAPL"],
            positions=[{"symbol": "AAPL", "quantity": 100}],
            targets={"stop_loss_price": 142.5},
        )
        d = inf.to_dict()
        assert d["id"] == "test_1"
        assert d["strategy_type"] == "LongEquity"
        assert d["confidence"] == 0.95
        assert d["targets"]["stop_loss_price"] == 142.5


# ---------------------------------------------------------------------------
# StrategyTarget model
# ---------------------------------------------------------------------------

class TestStrategyTargetModel:

    def test_import(self):
        """Verify the StrategyTarget model can be imported."""
        # Import directly from the module file to avoid heavy __init__.py deps
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location(
            "data.models_direct", "data/models.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        StrategyTarget = mod.StrategyTarget
        assert hasattr(StrategyTarget, "profit_target_price")
        assert hasattr(StrategyTarget, "stop_loss_price")
        assert hasattr(StrategyTarget, "trailing_stop_pct")
        assert hasattr(StrategyTarget, "max_profit")
        assert hasattr(StrategyTarget, "max_loss")
        assert hasattr(StrategyTarget, "time_target")
        assert hasattr(StrategyTarget, "max_holding_days")

    def test_to_dict(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "data.models_direct2", "data/models.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        StrategyTarget = mod.StrategyTarget
        t = StrategyTarget(
            id=1,
            strategy_id=1,
            profit_target_price=160.0,
            stop_loss_price=140.0,
            trailing_stop_pct=0.05,
        )
        d = t.to_dict()
        assert d["profit_target_price"] == 160.0
        assert d["stop_loss_price"] == 140.0
        assert d["trailing_stop_pct"] == 0.05

    def test_strategy_relationship_backref(self):
        """Verify the Strategy model has a 'targets' relationship."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "data.models_direct3", "data/models.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        Strategy = mod.Strategy
        assert hasattr(Strategy, "targets")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
