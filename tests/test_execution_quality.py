from autonomous.execution_quality import ExecutionQualityGuard


def test_execution_quality_allows_missing_quote_by_default():
    guard = ExecutionQualityGuard(block_on_missing_quote=False)

    decision = guard.evaluate_buy_limit(
        symbol="AAA",
        limit_price=100.0,
        reference_price=100.0,
    )

    assert decision.allowed is True
    assert decision.warnings


def test_execution_quality_blocks_missing_quote_when_configured():
    guard = ExecutionQualityGuard(block_on_missing_quote=True)

    decision = guard.evaluate_buy_limit(
        symbol="AAA",
        limit_price=100.0,
        reference_price=100.0,
    )

    assert decision.allowed is False
    assert "unavailable" in decision.reason


def test_execution_quality_blocks_wide_spread():
    guard = ExecutionQualityGuard(max_spread_pct=0.003)

    decision = guard.evaluate_buy_limit(
        symbol="AAA",
        limit_price=100.0,
        reference_price=100.0,
        bid=99.0,
        ask=101.0,
    )

    assert decision.allowed is False
    assert "spread" in decision.reason


def test_execution_quality_blocks_price_runaway():
    guard = ExecutionQualityGuard(max_price_move_pct=0.01)

    decision = guard.evaluate_buy_limit(
        symbol="AAA",
        limit_price=100.0,
        reference_price=100.0,
        bid=99.9,
        ask=100.1,
        last=102.0,
    )

    assert decision.allowed is False
    assert "price moved" in decision.reason


def test_execution_quality_allows_good_quote():
    guard = ExecutionQualityGuard(max_spread_pct=0.003, max_slippage_pct=0.005)

    decision = guard.evaluate_buy_limit(
        symbol="AAA",
        limit_price=100.0,
        reference_price=100.0,
        bid=99.95,
        ask=100.05,
        last=100.01,
    )

    assert decision.allowed is True
    assert decision.spread_pct is not None
