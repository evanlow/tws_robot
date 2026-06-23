"""Tests for the cash availability analysis feature.

Covers:
  1. No option positions: deployable cash = cash balance - buffer
  2. One cash-secured short put: reserve = strike * multiplier * contracts
  3. Multiple short puts across underlyings: reserves aggregate correctly
  4. Bull put spread: reserve = spread width * 100 * contracts, not full notional
  5. Iron condor: reserve = max loss of wider spread side
  6. Covered call: does not reduce cash reserve when enough shares exist
  7. Covered call: marks corresponding shares as committed
  8. Uncovered short call: high-risk warning and flag set
  9. Short stock: margin/risk warning issued
 10. Margin-financed long stock: margin safety buffer applied
 11. Pending stock buy order: reserves limit price * quantity
 12. Pending short-put order reserves gross assignment obligation
 13. Multi-currency account: deployable cash warns on mismatch
 14. Missing option parse data: conservative fallback warning
 15. Broker buying power shown separately from deployable cash
 16. Deployable cash floors at zero
 17. API endpoint: returns expected keys and format
 18. Bear call spread: short call protected by higher-strike long call
 19. Partial covered-call: covered + uncovered contracts split correctly
 20. Pending credit spread: paired short put + long put order uses spread reserve
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kw):
    from data.cash_availability import CashAvailabilityConfig, CashReserveMode

    defaults = {
        "reserve_mode": CashReserveMode.GROSS_ASSIGNMENT,
        "manual_cash_buffer_pct": 0.0,
        "manual_cash_buffer_amount": 0.0,
        "option_contract_multiplier": 100,
    }
    defaults.update(kw)
    return CashAvailabilityConfig(**defaults)


def _make_analyzer(**kw):
    from data.cash_availability import CashAvailabilityAnalyzer

    return CashAvailabilityAnalyzer(config=_make_config(**kw))


def _account(cash=100_000, buying_power=200_000, **kw):
    return {"cash_balance": cash, "buying_power": buying_power, **kw}


# Short put helper: OCC format AAPL260619P00150000 → strike 150
def _short_put(underlying, expiry, strike, contracts, premium_per_share=1.0,
               market_value=None):
    """Return a (symbol, pos_dict) pair for a short put."""
    strike_str = f"{int(strike * 1000):08d}"
    symbol = f"{underlying}{expiry}P{strike_str}"
    qty = -contracts  # negative = short
    mv = -(abs(market_value) if market_value is not None
           else contracts * 100 * premium_per_share * 0.5)
    return symbol, {
        "quantity": qty,
        "entry_price": premium_per_share,
        "market_value": mv,
        "side": "SHORT",
        "sec_type": "OPT",
    }


def _long_put(underlying, expiry, strike, contracts, premium_per_share=0.5):
    strike_str = f"{int(strike * 1000):08d}"
    symbol = f"{underlying}{expiry}P{strike_str}"
    mv = contracts * 100 * premium_per_share
    return symbol, {
        "quantity": contracts,
        "entry_price": premium_per_share,
        "market_value": mv,
        "side": "LONG",
        "sec_type": "OPT",
    }


def _short_call(underlying, expiry, strike, contracts, premium_per_share=1.5,
                market_value=None):
    strike_str = f"{int(strike * 1000):08d}"
    symbol = f"{underlying}{expiry}C{strike_str}"
    qty = -contracts
    mv = -(abs(market_value) if market_value is not None
           else contracts * 100 * premium_per_share * 0.5)
    return symbol, {
        "quantity": qty,
        "entry_price": premium_per_share,
        "market_value": mv,
        "side": "SHORT",
        "sec_type": "OPT",
    }


def _long_call(underlying, expiry, strike, contracts, premium_per_share=2.0):
    strike_str = f"{int(strike * 1000):08d}"
    symbol = f"{underlying}{expiry}C{strike_str}"
    mv = contracts * 100 * premium_per_share
    return symbol, {
        "quantity": contracts,
        "entry_price": premium_per_share,
        "market_value": mv,
        "side": "LONG",
        "sec_type": "OPT",
    }


def _stock(symbol, qty, entry_price=100.0):
    mv = qty * entry_price
    side = "LONG" if qty > 0 else "SHORT"
    return symbol, {
        "quantity": qty,
        "entry_price": entry_price,
        "market_value": mv,
        "side": side,
        "sec_type": "STK",
    }


# ===========================================================================
# 1. No option positions
# ===========================================================================

class TestNoPositions:
    def test_no_positions_deployable_equals_cash(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_account(cash=50_000), {})
        assert result.deployable_cash == 50_000.0

    def test_manual_buffer_pct_reduces_deployable(self):
        from data.cash_availability import CashAvailabilityConfig, CashReserveMode

        config = CashAvailabilityConfig(
            reserve_mode=CashReserveMode.GROSS_ASSIGNMENT,
            manual_cash_buffer_pct=0.10,
            manual_cash_buffer_amount=0.0,
        )
        from data.cash_availability import CashAvailabilityAnalyzer

        analyzer = CashAvailabilityAnalyzer(config=config)
        result = analyzer.analyze(_account(cash=50_000), {})
        assert result.manual_cash_buffer == 5_000.0
        assert result.deployable_cash == 45_000.0

    def test_manual_buffer_amount_reduces_deployable(self):
        from data.cash_availability import CashAvailabilityConfig, CashReserveMode

        config = CashAvailabilityConfig(
            reserve_mode=CashReserveMode.GROSS_ASSIGNMENT,
            manual_cash_buffer_pct=0.0,
            manual_cash_buffer_amount=3_000.0,
        )
        from data.cash_availability import CashAvailabilityAnalyzer

        analyzer = CashAvailabilityAnalyzer(config=config)
        result = analyzer.analyze(_account(cash=50_000), {})
        assert result.manual_cash_buffer == 3_000.0
        assert result.deployable_cash == 47_000.0

    def test_deployable_floors_at_zero(self):
        # Buffer larger than cash → deployable = 0
        from data.cash_availability import CashAvailabilityConfig, CashReserveMode

        config = CashAvailabilityConfig(
            reserve_mode=CashReserveMode.GROSS_ASSIGNMENT,
            manual_cash_buffer_pct=2.0,   # 200% — larger than cash
        )
        from data.cash_availability import CashAvailabilityAnalyzer

        analyzer = CashAvailabilityAnalyzer(config=config)
        result = analyzer.analyze(_account(cash=10_000), {})
        assert result.deployable_cash == 0.0

    def test_to_dict_has_required_keys(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_account(cash=10_000), {})
        d = result.to_dict()
        expected_keys = [
            "cash_balance", "cash_balance_usd", "cash_balance_currency",
            "broker_buying_power", "broker_available_funds",
            "broker_excess_liquidity", "reserved_cash_total",
            "reserved_cash_total_usd",
            "reserved_cash_short_puts", "reserved_cash_defined_risk_spreads",
            "reserved_cash_short_puts_usd", "reserved_cash_defined_risk_spreads_usd",
            "reserved_for_pending_orders", "manual_cash_buffer",
            "manual_cash_buffer_usd", "margin_safety_buffer",
            "margin_safety_buffer_usd", "deployable_cash", "deployable_cash_usd",
            "deployable_cash_currency", "reserve_coverage_ratio",
            "uncovered_short_call_risk", "cash_by_currency", "position_reserves",
            "warnings", "fx_rate_usd_sgd", "fx_rate_source",
        ]
        for k in expected_keys:
            assert k in d, f"Missing key: {k}"


# ===========================================================================
# 2. One cash-secured short put
# ===========================================================================

class TestOneShortPut:
    def test_reserve_equals_gross_obligation(self):
        analyzer = _make_analyzer()
        sym, pos = _short_put("AAPL", "260619", 150.0, 2, premium_per_share=3.0)
        result = analyzer.analyze(_account(cash=100_000), {sym: pos})

        # 2 contracts × 100 × $150 = $30,000
        assert result.reserved_cash_short_puts == 30_000.0
        assert result.deployable_cash == 70_000.0

    def test_reserve_position_detail(self):
        analyzer = _make_analyzer()
        sym, pos = _short_put("AAPL", "260619", 150.0, 2, premium_per_share=3.0)
        result = analyzer.analyze(_account(cash=100_000), {sym: pos})

        assert len(result.position_reserves) == 1
        pr = result.position_reserves[0]
        assert pr.position_type == "cash_secured_short_put"
        assert pr.underlying == "AAPL"
        assert pr.strike == 150.0
        assert pr.contracts == 2
        assert pr.gross_assignment_obligation == 30_000.0
        assert pr.reserve_amount == 30_000.0
        assert not pr.defined_risk_protected

    def test_net_premium_mode(self):
        from data.cash_availability import CashReserveMode

        analyzer = _make_analyzer(reserve_mode=CashReserveMode.NET_PREMIUM)
        sym, pos = _short_put("AAPL", "260619", 150.0, 2, premium_per_share=3.0)
        result = analyzer.analyze(_account(cash=100_000), {sym: pos})

        # gross = 30_000; premium = 2 * 100 * 3 = 600
        # net = 30_000 - 600 = 29_400
        assert result.reserved_cash_short_puts == pytest.approx(29_400.0)

    def test_premium_collected_stored(self):
        analyzer = _make_analyzer()
        sym, pos = _short_put("AAPL", "260619", 150.0, 1, premium_per_share=5.0)
        result = analyzer.analyze(_account(), {sym: pos})

        pr = result.position_reserves[0]
        assert pr.premium_collected == pytest.approx(500.0)  # 1 * 100 * 5


# ===========================================================================
# 3. Multiple short puts across underlyings
# ===========================================================================

class TestMultipleShortPuts:
    def test_aggregate_reserve(self):
        analyzer = _make_analyzer()
        sym1, pos1 = _short_put("AAPL", "260619", 150.0, 1, premium_per_share=2.0)
        sym2, pos2 = _short_put("TSLA", "260619", 200.0, 2, premium_per_share=4.0)
        positions = {sym1: pos1, sym2: pos2}
        result = analyzer.analyze(_account(cash=100_000), positions)

        # AAPL: 1 × 100 × 150 = 15_000
        # TSLA: 2 × 100 × 200 = 40_000
        assert result.reserved_cash_short_puts == 55_000.0
        assert result.deployable_cash == 45_000.0

    def test_two_short_puts_same_underlying(self):
        analyzer = _make_analyzer()
        sym1, pos1 = _short_put("AAPL", "260619", 150.0, 1)
        sym2, pos2 = _short_put("AAPL", "260718", 140.0, 1)
        positions = {sym1: pos1, sym2: pos2}
        result = analyzer.analyze(_account(cash=50_000), positions)

        # 15_000 + 14_000 = 29_000
        assert result.reserved_cash_short_puts == 29_000.0
        assert len(result.position_reserves) == 2


# ===========================================================================
# 4. Bull put spread: reserve = spread width × 100 × contracts
# ===========================================================================

class TestBullPutSpread:
    def test_spread_reserve_is_width_not_full_notional(self):
        analyzer = _make_analyzer()
        short_sym, short_pos = _short_put(
            "AAPL", "260619", 150.0, 2, premium_per_share=3.0
        )
        long_sym, long_pos = _long_put(
            "AAPL", "260619", 140.0, 2, premium_per_share=1.0
        )
        positions = {short_sym: short_pos, long_sym: long_pos}
        result = analyzer.analyze(_account(cash=100_000), positions)

        # Spread width = 150 - 140 = 10; reserve = 2 × 100 × 10 = 2_000
        assert result.reserved_cash_defined_risk_spreads == 2_000.0
        # No naked short-put reserve
        assert result.reserved_cash_short_puts == 0.0
        assert result.deployable_cash == 98_000.0

    def test_spread_position_is_marked_defined_risk(self):
        analyzer = _make_analyzer()
        short_sym, short_pos = _short_put("AAPL", "260619", 150.0, 1)
        long_sym, long_pos = _long_put("AAPL", "260619", 140.0, 1)
        positions = {short_sym: short_pos, long_sym: long_pos}
        result = analyzer.analyze(_account(), positions)

        spread_reserves = [
            pr for pr in result.position_reserves
            if pr.position_type == "defined_risk_put_spread"
        ]
        assert len(spread_reserves) == 1
        assert spread_reserves[0].defined_risk_protected
        assert spread_reserves[0].spread_width == 10.0

    def test_mismatched_expiry_not_treated_as_spread(self):
        """Different expiries → long put does not protect short put."""
        analyzer = _make_analyzer()
        short_sym, short_pos = _short_put("AAPL", "260619", 150.0, 1)
        long_sym, long_pos = _long_put("AAPL", "260718", 140.0, 1)  # diff expiry
        positions = {short_sym: short_pos, long_sym: long_pos}
        result = analyzer.analyze(_account(cash=100_000), positions)

        # Should treat as naked put
        assert result.reserved_cash_short_puts == 15_000.0
        assert result.reserved_cash_defined_risk_spreads == 0.0


# ===========================================================================
# 5. Iron condor: reserve = put spread max loss only
# ===========================================================================

class TestIronCondor:
    def test_iron_condor_reserve_is_max_spread_width(self):
        """Full iron condor (put spread + call spread) reserves max-loss of wider leg."""
        analyzer = _make_analyzer()
        # Put spread: short 500, long 490 → width 10
        short_put_sym, short_put_pos = _short_put("SPY", "260619", 500.0, 1)
        long_put_sym, long_put_pos = _long_put("SPY", "260619", 490.0, 1)
        # Call spread: short 520, long 530 → width 10
        short_call_sym, short_call_pos = _short_call("SPY", "260619", 520.0, 1)
        long_call_sym, long_call_pos = _long_call("SPY", "260619", 530.0, 1)
        positions = {
            short_put_sym: short_put_pos,
            long_put_sym: long_put_pos,
            short_call_sym: short_call_pos,
            long_call_sym: long_call_pos,
        }
        result = analyzer.analyze(_account(cash=100_000), positions)

        # Iron condor: max(10, 10) × 1 × 100 = 1_000 (not 2_000 for both sides)
        assert result.reserved_cash_defined_risk_spreads == 1_000.0
        # Short call is protected by the long call — NOT flagged as uncovered
        assert not result.uncovered_short_call_risk

    def test_iron_condor_wider_call_spread_sets_reserve(self):
        """When the call spread is wider, it sets the reserve."""
        analyzer = _make_analyzer()
        # Put spread width = 10
        short_put_sym, short_put_pos = _short_put("SPY", "260619", 500.0, 1)
        long_put_sym, long_put_pos = _long_put("SPY", "260619", 490.0, 1)
        # Call spread width = 15
        short_call_sym, short_call_pos = _short_call("SPY", "260619", 520.0, 1)
        long_call_sym, long_call_pos = _long_call("SPY", "260619", 535.0, 1)
        positions = {
            short_put_sym: short_put_pos,
            long_put_sym: long_put_pos,
            short_call_sym: short_call_pos,
            long_call_sym: long_call_pos,
        }
        result = analyzer.analyze(_account(cash=100_000), positions)

        # max(10, 15) × 1 × 100 = 1_500
        assert result.reserved_cash_defined_risk_spreads == 1_500.0
        assert not result.uncovered_short_call_risk

    def test_iron_condor_position_type_is_iron_condor(self):
        """Iron condor produces a single position_reserve entry with type 'iron_condor'."""
        analyzer = _make_analyzer()
        short_put_sym, short_put_pos = _short_put("SPY", "260619", 500.0, 1)
        long_put_sym, long_put_pos = _long_put("SPY", "260619", 490.0, 1)
        short_call_sym, short_call_pos = _short_call("SPY", "260619", 520.0, 1)
        long_call_sym, long_call_pos = _long_call("SPY", "260619", 530.0, 1)
        positions = {
            short_put_sym: short_put_pos,
            long_put_sym: long_put_pos,
            short_call_sym: short_call_pos,
            long_call_sym: long_call_pos,
        }
        result = analyzer.analyze(_account(cash=100_000), positions)

        ic_reserves = [
            pr for pr in result.position_reserves
            if pr.position_type == "iron_condor"
        ]
        assert len(ic_reserves) == 1
        assert ic_reserves[0].defined_risk_protected

    def test_overlapping_spreads_are_not_treated_as_iron_condor(self):
        """Overlapping put/call spreads must retain both spread reserves."""
        analyzer = _make_analyzer()
        short_put_sym, short_put_pos = _short_put("SPY", "260619", 150.0, 1)
        long_put_sym, long_put_pos = _long_put("SPY", "260619", 140.0, 1)
        short_call_sym, short_call_pos = _short_call("SPY", "260619", 130.0, 1)
        long_call_sym, long_call_pos = _long_call("SPY", "260619", 135.0, 1)
        positions = {
            short_put_sym: short_put_pos,
            long_put_sym: long_put_pos,
            short_call_sym: short_call_pos,
            long_call_sym: long_call_pos,
        }
        result = analyzer.analyze(_account(cash=100_000), positions)

        assert result.reserved_cash_defined_risk_spreads == 1_500.0
        assert sum(
            1 for pr in result.position_reserves if pr.position_type == "iron_condor"
        ) == 0
        assert sum(
            1
            for pr in result.position_reserves
            if pr.position_type == "defined_risk_put_spread"
        ) == 1
        assert sum(
            1
            for pr in result.position_reserves
            if pr.position_type == "defined_risk_call_spread"
        ) == 1

    def test_iron_condor_with_stock_cover_no_extra_reserve(self):
        """When the short call is covered by long stock, it adds no reserve."""
        analyzer = _make_analyzer()
        # Stock position covering the call
        stock_sym, stock_pos = _stock("SPY", 100)  # covers 1 contract
        # Put spread
        short_put_sym, short_put_pos = _short_put("SPY", "260619", 500.0, 1)
        long_put_sym, long_put_pos = _long_put("SPY", "260619", 490.0, 1)
        # Covered call
        short_call_sym, short_call_pos = _short_call("SPY", "260619", 520.0, 1)
        positions = {
            stock_sym: stock_pos,
            short_put_sym: short_put_pos,
            long_put_sym: long_put_pos,
            short_call_sym: short_call_pos,
        }
        result = analyzer.analyze(_account(cash=100_000), positions)

        # Put spread: 1 × 100 × 10 = 1_000
        assert result.reserved_cash_defined_risk_spreads == 1_000.0
        assert not result.uncovered_short_call_risk


# ===========================================================================
# 6 & 7. Covered calls
# ===========================================================================

class TestCoveredCalls:
    def test_covered_call_no_cash_reserve(self):
        """Short call with sufficient shares does NOT consume cash reserve."""
        analyzer = _make_analyzer()
        stock_sym, stock_pos = _stock("AAPL", 100)
        call_sym, call_pos = _short_call("AAPL", "260619", 160.0, 1)
        positions = {stock_sym: stock_pos, call_sym: call_pos}
        result = analyzer.analyze(_account(cash=50_000), positions)

        assert result.reserved_cash_short_puts == 0.0
        assert result.reserved_cash_defined_risk_spreads == 0.0
        # Total reserve = 0 + buffer
        assert result.deployable_cash == 50_000.0
        assert not result.uncovered_short_call_risk

    def test_covered_call_commits_shares(self):
        """Shares backing a covered call are recorded as committed."""
        analyzer = _make_analyzer()
        stock_sym, stock_pos = _stock("AAPL", 200)
        call_sym, call_pos = _short_call("AAPL", "260619", 160.0, 2)  # 200 shares
        positions = {stock_sym: stock_pos, call_sym: call_pos}
        result = analyzer.analyze(_account(), positions)

        assert result.committed_shares.get("AAPL") == 200

    def test_partial_cover_creates_covered_and_uncovered_entries(self):
        """Partial stock coverage splits into covered + uncovered position reserves."""
        analyzer = _make_analyzer()
        stock_sym, stock_pos = _stock("AAPL", 100)   # covers 1 contract
        call_sym, call_pos = _short_call("AAPL", "260619", 160.0, 2)  # needs 200
        positions = {stock_sym: stock_pos, call_sym: call_pos}
        result = analyzer.analyze(_account(), positions)

        # Only 1 contract is covered; the other is naked
        assert result.uncovered_short_call_risk

        covered = [
            pr for pr in result.position_reserves
            if pr.position_type == "covered_short_call"
        ]
        uncovered = [
            pr for pr in result.position_reserves
            if pr.position_type == "uncovered_short_call"
        ]
        assert len(covered) == 1
        assert covered[0].contracts == 1
        assert result.committed_shares.get("AAPL") == 100

        assert len(uncovered) == 1
        assert uncovered[0].contracts == 1

    def test_covered_call_position_type(self):
        analyzer = _make_analyzer()
        stock_sym, stock_pos = _stock("AAPL", 100)
        call_sym, call_pos = _short_call("AAPL", "260619", 160.0, 1)
        positions = {stock_sym: stock_pos, call_sym: call_pos}
        result = analyzer.analyze(_account(), positions)

        covered = [
            pr for pr in result.position_reserves
            if pr.position_type == "covered_short_call"
        ]
        assert len(covered) == 1


# ===========================================================================
# 8. Uncovered short call
# ===========================================================================

class TestUncoveredShortCall:
    def test_uncovered_short_call_flag(self):
        analyzer = _make_analyzer()
        call_sym, call_pos = _short_call("AAPL", "260619", 200.0, 1)
        result = analyzer.analyze(_account(), {call_sym: call_pos})

        assert result.uncovered_short_call_risk
        assert any("uncovered" in w.lower() or "naked" in w.lower()
                   for w in result.warnings)

    def test_uncovered_short_call_position_type(self):
        analyzer = _make_analyzer()
        call_sym, call_pos = _short_call("AAPL", "260619", 200.0, 2)
        result = analyzer.analyze(_account(), {call_sym: call_pos})

        uncovered = [
            pr for pr in result.position_reserves
            if pr.position_type == "uncovered_short_call"
        ]
        assert len(uncovered) == 1
        assert uncovered[0].contracts == 2


# ===========================================================================
# 9. Short stock
# ===========================================================================

class TestShortStock:
    def test_short_stock_emits_warning(self):
        analyzer = _make_analyzer()
        sym, pos = _stock("TSLA", -50, entry_price=200.0)
        result = analyzer.analyze(_account(), {sym: pos})

        assert any("short stock" in w.lower() for w in result.warnings)
        assert result.high_margin_usage

    def test_short_stock_no_direct_cash_reserve(self):
        """Short stock does not add to the numeric cash reserves."""
        analyzer = _make_analyzer()
        sym, pos = _stock("TSLA", -100, entry_price=200.0)
        result = analyzer.analyze(_account(cash=50_000), {sym: pos})

        # No numeric reserve is added (broker margin rules govern)
        assert result.reserved_cash_short_puts == 0.0
        assert result.reserved_cash_defined_risk_spreads == 0.0


# ===========================================================================
# 10. Margin-financed long stock
# ===========================================================================

class TestMarginUsage:
    def test_high_margin_usage_buffer_applied(self):
        """Tight excess liquidity triggers the margin safety buffer."""
        analyzer = _make_analyzer()
        account = _account(
            cash=100_000,
            excess_liquidity=5_000,   # < 10% of cash → tight
        )
        result = analyzer.analyze(account, {})

        # Margin safety buffer = 5% of cash = 5_000
        assert result.margin_safety_buffer == pytest.approx(5_000.0)
        assert result.deployable_cash < 100_000.0

    def test_comfortable_excess_liquidity_no_margin_buffer(self):
        analyzer = _make_analyzer()
        account = _account(cash=100_000, excess_liquidity=50_000)
        result = analyzer.analyze(account, {})

        assert result.margin_safety_buffer == 0.0

    def test_excess_liquidity_exactly_at_threshold_no_margin_buffer(self):
        """Excess liquidity exactly at 10% of cash should NOT trigger the buffer."""
        analyzer = _make_analyzer()
        account = _account(cash=100_000, excess_liquidity=10_000)  # == 10%
        result = analyzer.analyze(account, {})

        assert result.margin_safety_buffer == 0.0

    def test_excess_liquidity_just_below_threshold_triggers_buffer(self):
        """Excess liquidity just below 10% of cash should trigger the 5% buffer."""
        analyzer = _make_analyzer()
        account = _account(cash=100_000, excess_liquidity=9_999)  # < 10%
        result = analyzer.analyze(account, {})

        assert result.margin_safety_buffer == pytest.approx(5_000.0)

    def test_high_margin_req_sets_flag(self):
        analyzer = _make_analyzer()
        account = _account(cash=100_000, init_margin_req=85_000)
        result = analyzer.analyze(account, {})

        assert result.high_margin_usage


# ===========================================================================
# 11. Pending stock buy order
# ===========================================================================

class TestPendingOrders:
    def test_pending_stock_buy_reserves_capital(self):
        analyzer = _make_analyzer()
        orders = [{
            "id": "1",
            "status": "PENDING",
            "action": "BUY",
            "sec_type": "STK",
            "quantity": 100,
            "limit_price": 150.0,
        }]
        result = analyzer.analyze(_account(cash=50_000), {}, orders)

        # 100 shares × $150 = $15,000
        assert result.reserved_for_pending_orders == 15_000.0
        assert result.deployable_cash == 35_000.0

    def test_pending_option_buy_reserves_premium(self):
        analyzer = _make_analyzer()
        orders = [{
            "id": "2",
            "status": "RECORDED",
            "action": "BTO",
            "sec_type": "OPT",
            "quantity": 2,
            "limit_price": 3.0,
        }]
        result = analyzer.analyze(_account(cash=10_000), {}, orders)

        # 2 contracts × $3 × 100 = $600
        assert result.reserved_for_pending_orders == 600.0

    def test_filled_order_not_reserved(self):
        analyzer = _make_analyzer()
        orders = [{
            "id": "3",
            "status": "FILLED",
            "action": "BUY",
            "sec_type": "STK",
            "quantity": 100,
            "limit_price": 150.0,
        }]
        result = analyzer.analyze(_account(cash=50_000), {}, orders)
        assert result.reserved_for_pending_orders == 0.0

    def test_sell_stock_order_not_reserved(self):
        """Sell orders for stock do not consume cash reserve."""
        analyzer = _make_analyzer()
        orders = [{
            "id": "4",
            "status": "PENDING",
            "action": "SELL",
            "sec_type": "STK",
            "symbol": "AAPL",
            "quantity": 100,
            "limit_price": 150.0,
        }]
        result = analyzer.analyze(_account(cash=50_000), {}, orders)
        assert result.reserved_for_pending_orders == 0.0

    def test_pending_short_put_order_reserves_gross_obligation(self):
        """A pending SELL order for a put option reserves the gross assignment amount."""
        analyzer = _make_analyzer()
        # Short put at strike 150, 2 contracts
        sym, _ = _short_put("AAPL", "260619", 150.0, 2)
        orders = [{
            "id": "5",
            "status": "PENDING",
            "action": "SELL",
            "symbol": sym,
            "quantity": 2,
            "limit_price": 3.0,
        }]
        result = analyzer.analyze(_account(cash=100_000), {}, orders)

        # 2 contracts × 100 × $150 = $30,000
        assert result.reserved_for_pending_orders == 30_000.0

    def test_pending_short_put_order_net_premium_mode(self):
        """In net_premium mode, credit is subtracted from gross obligation."""
        from data.cash_availability import CashReserveMode

        analyzer = _make_analyzer(reserve_mode=CashReserveMode.NET_PREMIUM)
        sym, _ = _short_put("AAPL", "260619", 150.0, 1)
        orders = [{
            "id": "6",
            "status": "PENDING",
            "action": "SELL",
            "symbol": sym,
            "quantity": 1,
            "limit_price": 3.0,  # credit per share
        }]
        result = analyzer.analyze(_account(cash=100_000), {}, orders)

        # gross = 1 × 100 × 150 = 15_000; credit = 1 × 100 × 3 = 300
        # net = 15_000 - 300 = 14_700
        assert result.reserved_for_pending_orders == pytest.approx(14_700.0)

    def test_pending_credit_spread_uses_spread_width_reserve(self):
        """A paired pending short-put + long-put order reserves spread max loss."""
        analyzer = _make_analyzer()
        short_sym, _ = _short_put("AAPL", "260619", 150.0, 1)
        long_sym, _ = _long_put("AAPL", "260619", 140.0, 1)
        orders = [
            {
                "id": "7",
                "status": "PENDING",
                "action": "SELL",
                "symbol": short_sym,
                "quantity": 1,
                "limit_price": 3.0,
            },
            {
                "id": "8",
                "status": "PENDING",
                "action": "BUY",
                "symbol": long_sym,
                "quantity": 1,
                "limit_price": 1.0,
            },
        ]
        result = analyzer.analyze(_account(cash=100_000), {}, orders)

        # Spread width = 10; reserve = 1 × 100 × 10 = 1_000
        # Long put buy premium = 1 × 100 × 1 = 100
        # Total = 1_000 (spread reserve) + 100 (long put premium buy order)
        assert result.reserved_for_pending_orders == pytest.approx(1_100.0)

    def test_pending_short_put_sto_action_reserved(self):
        """STO (Sell To Open) action is treated as a short sell for reserve purposes."""
        analyzer = _make_analyzer()
        sym, _ = _short_put("AAPL", "260619", 100.0, 1)
        orders = [{
            "id": "9",
            "status": "PENDING",
            "action": "STO",
            "symbol": sym,
            "quantity": 1,
            "limit_price": 2.0,
        }]
        result = analyzer.analyze(_account(cash=100_000), {}, orders)

        # 1 × 100 × 100 = 10_000
        assert result.reserved_for_pending_orders == 10_000.0


# ===========================================================================
# 13. Multi-currency account
# ===========================================================================

class TestMultiCurrency:
    def test_non_usd_balance_emits_warning(self):
        analyzer = _make_analyzer()
        account = _account(
            cash=50_000,
            cash_by_currency={"USD": 50_000, "SGD": 30_000},
        )
        result = analyzer.analyze(account, {})

        assert result.multi_currency_mismatch
        assert any("sgd" in w.lower() or "non-usd" in w.lower()
                   for w in result.warnings)

    def test_usd_only_no_warning(self):
        analyzer = _make_analyzer()
        account = _account(
            cash=50_000,
            cash_by_currency={"USD": 50_000},
        )
        result = analyzer.analyze(account, {})

        assert not result.multi_currency_mismatch

    def test_cash_by_currency_in_output(self):
        analyzer = _make_analyzer()
        account = _account(
            cash=50_000,
            cash_by_currency={"USD": 50_000, "HKD": 100_000},
        )
        result = analyzer.analyze(account, {})
        d = result.to_dict()

        assert d["cash_by_currency"]["USD"] == 50_000.0
        assert d["cash_by_currency"]["HKD"] == 100_000.0


class TestUsdStandardization:
    def test_sgd_base_converts_deployable_cash_to_usd(self):
        analyzer = _make_analyzer(account_base_currency="SGD")
        account = _account(
            cash=50_000,
            cash_by_currency={"USD": 50_000, "SGD": 30_000},
        )
        result = analyzer.analyze(account, {}, usd_sgd_rate=1.25)

        assert result.cash_balance_currency == "SGD"
        assert result.cash_balance_usd == pytest.approx(40_000.0)
        assert result.deployable_cash_currency == "USD"
        assert result.deployable_cash == pytest.approx(40_000.0)
        assert result.deployable_cash_usd == pytest.approx(40_000.0)
        assert result.fx_rate_usd_sgd == pytest.approx(1.25)
        assert any("standardization applied" in w.lower() for w in result.warnings)

    def test_sgd_base_without_fx_rate_fails_closed(self):
        analyzer = _make_analyzer(account_base_currency="SGD")
        account = _account(
            cash=50_000,
            cash_by_currency={"USD": 50_000, "SGD": 30_000},
        )
        result = analyzer.analyze(account, {})

        assert result.deployable_cash == 0.0
        assert result.deployable_cash_usd == 0.0
        assert any("standardization unavailable" in w.lower() for w in result.warnings)


# ===========================================================================
# 14. Unparseable option symbol
# ===========================================================================

class TestUnparseableOption:
    def test_unparseable_option_emits_warning(self):
        analyzer = _make_analyzer()
        positions = {
            "NOTANOPTION": {
                "quantity": -1,
                "entry_price": 5.0,
                "market_value": -300.0,
                "side": "SHORT",
                "sec_type": "OPT",
            }
        }
        result = analyzer.analyze(_account(), positions)

        assert any("notanoption" in w.lower() or "parse" in w.lower()
                   for w in result.warnings)

    def test_unparseable_option_adds_conservative_reserve_entry(self):
        analyzer = _make_analyzer()
        positions = {
            "BADOPT": {
                "quantity": -1,
                "entry_price": 5.0,
                "market_value": -300.0,
                "side": "SHORT",
                "sec_type": "OPT",
            }
        }
        result = analyzer.analyze(_account(), positions)

        unparseable = [
            pr for pr in result.position_reserves
            if pr.position_type == "unparseable_option"
        ]
        assert len(unparseable) == 1


# ===========================================================================
# 15. Broker buying power vs deployable cash
# ===========================================================================

class TestBrokerFields:
    def test_broker_buying_power_shown_separately(self):
        analyzer = _make_analyzer()
        account = _account(
            cash=50_000,
            buying_power=200_000,
            available_funds=48_000,
            excess_liquidity=47_000,
        )
        sym, pos = _short_put("AAPL", "260619", 150.0, 2)
        result = analyzer.analyze(account, {sym: pos})

        # Deployable is different from broker buying power
        assert result.broker_buying_power == 200_000.0
        assert result.broker_available_funds == 48_000.0
        assert result.deployable_cash < 200_000.0
        assert result.deployable_cash < result.broker_buying_power

    def test_broker_margin_fields_captured(self):
        analyzer = _make_analyzer()
        account = _account(
            cash=100_000,
            init_margin_req=20_000,
            maint_margin_req=15_000,
        )
        result = analyzer.analyze(account, {})

        assert result.broker_initial_margin_req == 20_000.0
        assert result.broker_maintenance_margin_req == 15_000.0


# ===========================================================================
# 16. Deployable cash floors at zero
# ===========================================================================

class TestFloor:
    def test_large_reserve_floors_deployable_at_zero(self):
        analyzer = _make_analyzer()
        # Short put obligation exceeds cash
        sym, pos = _short_put("AAPL", "260619", 150.0, 10)  # 150_000 reserve
        result = analyzer.analyze(_account(cash=50_000), {sym: pos})

        assert result.deployable_cash == 0.0
        assert any("zero or negative" in w.lower() for w in result.warnings)

    def test_reserve_coverage_ratio_computed(self):
        analyzer = _make_analyzer()
        sym, pos = _short_put("AAPL", "260619", 100.0, 1)   # 10_000 reserve
        result = analyzer.analyze(_account(cash=30_000), {sym: pos})

        # 30_000 / 10_000 = 3.0
        assert result.reserve_coverage_ratio == pytest.approx(3.0)

    def test_zero_reserve_ratio_is_null(self):
        """No reserves + positive cash → coverage ratio is null (not infinity)."""
        analyzer = _make_analyzer()
        result = analyzer.analyze(_account(cash=50_000), {})
        assert result.reserve_coverage_ratio is None
        # to_dict() should serialize as JSON null, not Infinity
        d = result.to_dict()
        assert d["reserve_coverage_ratio"] is None

    def test_zero_cash_zero_ratio(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_account(cash=0), {})
        assert result.reserve_coverage_ratio == 0.0


# ===========================================================================
# 17. API endpoint
# ===========================================================================

class TestCashAvailabilityEndpoint:
    """Smoke tests for GET /api/account/cash-availability."""

    @pytest.fixture
    def app(self, monkeypatch):
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        from web import create_app

        return create_app({
            "TESTING": True,
            "LOGIN_DISABLED": True,
            "WTF_CSRF_ENABLED": False,
        })

    def _client_with_data(self, app, positions=None, orders=None, account=None):
        svc = app.config["services"]
        with svc._lock:
            svc._account_summary = account or {
                "cash_balance": 50_000,
                "buying_power": 100_000,
            }
            svc._positions = positions or {}
            svc._orders = orders or []
        return app.test_client()

    def test_endpoint_returns_200_and_expected_keys(self, app):
        client = self._client_with_data(app)
        resp = client.get("/api/account/cash-availability")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "cash_balance" in data
        assert "deployable_cash" in data
        assert "position_reserves" in data

    def test_endpoint_with_short_put_position(self, app):
        sym, pos = _short_put("AAPL", "260619", 150.0, 1)
        client = self._client_with_data(
            app,
            positions={sym: pos},
            account={"cash_balance": 30_000, "buying_power": 60_000},
        )
        resp = client.get("/api/account/cash-availability")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reserved_cash_short_puts"] == 15_000.0

    def test_endpoint_reserve_mode_param(self, app):
        sym, pos = _short_put("AAPL", "260619", 150.0, 1, premium_per_share=3.0)
        client = self._client_with_data(
            app,
            positions={sym: pos},
            account={"cash_balance": 30_000},
        )
        resp = client.get(
            "/api/account/cash-availability?reserve_mode=net_premium"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        # net = 15_000 - (1 * 100 * 3) = 14_700
        assert data["reserved_cash_short_puts"] == pytest.approx(14_700.0)

    def test_endpoint_invalid_reserve_mode(self, app):
        client = self._client_with_data(app)
        resp = client.get(
            "/api/account/cash-availability?reserve_mode=invalid"
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_endpoint_deployable_floors_at_zero(self, app):
        sym, pos = _short_put("AAPL", "260619", 500.0, 5)   # huge obligation
        client = self._client_with_data(
            app,
            positions={sym: pos},
            account={"cash_balance": 10_000},
        )
        resp = client.get("/api/account/cash-availability")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["deployable_cash"] == 0.0


# ===========================================================================
# TWSBridge: enhanced account value ingestion
# ===========================================================================

class TestTWSBridgeAccountIngestion:
    """Verify that the enhanced TWSBridge.updateAccountValue() stores new fields."""

    def _make_svc(self):
        """Return a minimal mock ServiceManager with a real _account_summary dict."""
        svc = MagicMock()
        svc._account_summary = {}
        svc._lock = __import__("threading").Lock()

        def _update(data):
            svc._account_summary.update(data)

        svc.update_account_summary.side_effect = _update
        return svc

    def _make_bridge_app(self, svc):
        from core.tws_bridge import _BridgeApp

        app = _BridgeApp.__new__(_BridgeApp)
        app._svc = svc
        app._account = "TEST"
        return app

    def _call_update(self, app, key, val, currency="BASE"):
        app.updateAccountValue(key, val, currency, "TEST")

    def test_available_funds_stored(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        self._call_update(app, "AvailableFunds", "48000.0")
        assert svc._account_summary.get("available_funds") == 48_000.0

    def test_excess_liquidity_stored(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        self._call_update(app, "ExcessLiquidity", "47000.0")
        assert svc._account_summary.get("excess_liquidity") == 47_000.0

    def test_init_margin_req_stored(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        self._call_update(app, "InitMarginReq", "20000.0")
        assert svc._account_summary.get("init_margin_req") == 20_000.0

    def test_maint_margin_req_stored(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        self._call_update(app, "MaintMarginReq", "15000.0")
        assert svc._account_summary.get("maint_margin_req") == 15_000.0

    def test_settled_cash_stored(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        self._call_update(app, "SettledCash", "49000.0")
        assert svc._account_summary.get("settled_cash") == 49_000.0

    def test_lookahead_available_funds_stored(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        self._call_update(app, "LookAheadAvailableFunds", "45000.0")
        assert svc._account_summary.get("lookahead_available_funds") == 45_000.0

    def test_per_currency_cash_stored(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        self._call_update(app, "CashBalance", "30000.0", currency="SGD")
        assert svc._account_summary.get("cash_by_currency", {}).get("SGD") == 30_000.0

    def test_non_base_non_cash_key_ignored_in_summary(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        # A non-BASE currency for a non-cash-balance key should not populate
        # the summary (only the event bus is called)
        self._call_update(app, "NetLiquidation", "99000.0", currency="SGD")
        assert "net_liquidation" not in svc._account_summary

    def test_buying_power_base_currency(self):
        svc = self._make_svc()
        app = self._make_bridge_app(svc)
        self._call_update(app, "BuyingPower", "200000.0")
        assert svc._account_summary.get("buying_power") == 200_000.0


# ===========================================================================
# 18. Bear call spread
# ===========================================================================

class TestBearCallSpread:
    def test_bear_call_spread_reserve_is_width_not_notional(self):
        """Short call + higher-strike long call = defined-risk bear call spread."""
        analyzer = _make_analyzer()
        short_call_sym, short_call_pos = _short_call(
            "AAPL", "260619", 160.0, 1, premium_per_share=3.0
        )
        long_call_sym, long_call_pos = _long_call(
            "AAPL", "260619", 170.0, 1, premium_per_share=1.0
        )
        positions = {short_call_sym: short_call_pos, long_call_sym: long_call_pos}
        result = analyzer.analyze(_account(cash=100_000), positions)

        # Spread width = 170 - 160 = 10; reserve = 1 × 100 × 10 = 1_000
        assert result.reserved_cash_defined_risk_spreads == 1_000.0
        # No naked short call risk
        assert not result.uncovered_short_call_risk

    def test_bear_call_spread_position_type(self):
        """Bear call spread produces a defined_risk_call_spread position entry."""
        analyzer = _make_analyzer()
        sc_sym, sc_pos = _short_call("AAPL", "260619", 160.0, 2)
        lc_sym, lc_pos = _long_call("AAPL", "260619", 175.0, 2)
        positions = {sc_sym: sc_pos, lc_sym: lc_pos}
        result = analyzer.analyze(_account(), positions)

        call_spreads = [
            pr for pr in result.position_reserves
            if pr.position_type == "defined_risk_call_spread"
        ]
        assert len(call_spreads) == 1
        assert call_spreads[0].defined_risk_protected
        assert call_spreads[0].spread_width == pytest.approx(15.0)
        # reserve = 2 × 100 × 15 = 3_000
        assert call_spreads[0].reserve_amount == pytest.approx(3_000.0)

    def test_bear_call_spread_mismatched_expiry_is_uncovered(self):
        """Long call with a different expiry does not protect the short call."""
        analyzer = _make_analyzer()
        sc_sym, sc_pos = _short_call("AAPL", "260619", 160.0, 1)
        lc_sym, lc_pos = _long_call("AAPL", "260718", 170.0, 1)  # diff expiry
        positions = {sc_sym: sc_pos, lc_sym: lc_pos}
        result = analyzer.analyze(_account(), positions)

        assert result.uncovered_short_call_risk

    def test_standalone_bear_call_spread_no_iron_condor(self):
        """Bear call spread without a matching put spread is standalone."""
        analyzer = _make_analyzer()
        sc_sym, sc_pos = _short_call("AAPL", "260619", 160.0, 1)
        lc_sym, lc_pos = _long_call("AAPL", "260619", 170.0, 1)
        positions = {sc_sym: sc_pos, lc_sym: lc_pos}
        result = analyzer.analyze(_account(cash=50_000), positions)

        assert result.reserved_cash_defined_risk_spreads == 1_000.0
        assert result.reserved_cash_short_puts == 0.0
        assert not result.uncovered_short_call_risk


# ===========================================================================
# 19. has_short_stock field
# ===========================================================================

class TestHasShortStock:
    def test_has_short_stock_set_when_short(self):
        analyzer = _make_analyzer()
        sym, pos = _stock("TSLA", -50, entry_price=200.0)
        result = analyzer.analyze(_account(), {sym: pos})

        assert result.has_short_stock
        d = result.to_dict()
        assert d["has_short_stock"] is True

    def test_has_short_stock_false_when_no_short_stock(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_account(), {})

        assert not result.has_short_stock
        d = result.to_dict()
        assert d["has_short_stock"] is False
