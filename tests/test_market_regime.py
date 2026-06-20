from autonomous.market_regime import evaluate_market_regime


def test_market_regime_allows_bullish_spy_with_normal_vix():
    gate = evaluate_market_regime(
        {
            "open": 500.0,
            "current": 505.0,
            "vix_open": 16.0,
            "vix_current": 15.5,
        }
    )

    assert gate["trade_allowed"] is True
    assert gate["bullish"] is True
    assert gate["size_multiplier"] == 1.0
    assert gate["vix"]["level_regime"] == "normal"


def test_market_regime_blocks_when_vix_above_block_level():
    gate = evaluate_market_regime(
        {
            "open": 500.0,
            "current": 505.0,
            "vix_open": 28.0,
            "vix_current": 31.0,
        }
    )

    assert gate["trade_allowed"] is False
    assert gate["size_multiplier"] == 0.0
    assert gate["vix"]["level_regime"] == "block"
    assert any("block level" in reason for reason in gate["reasons"])


def test_market_regime_reduces_size_when_vix_rises_intraday():
    gate = evaluate_market_regime(
        {
            "open": 500.0,
            "current": 505.0,
            "vix_open": 17.0,
            "vix_current": 17.6,
        }
    )

    assert gate["trade_allowed"] is True
    assert gate["size_multiplier"] == 0.5
    assert gate["vix"]["direction_regime"] == "rising_caution"
    assert gate["warnings"]


def test_market_regime_can_fail_closed_when_vix_missing():
    gate = evaluate_market_regime(
        {"open": 500.0, "current": 505.0},
        vix_missing_blocks_trade=True,
    )

    assert gate["trade_allowed"] is False
    assert gate["vix"]["level_regime"] == "unavailable"
    assert "VIX data unavailable" in gate["reasons"]


def test_market_regime_applies_vix_block_with_current_only_no_open():
    """VIX absolute-level block fires even when vix_open is absent."""
    gate = evaluate_market_regime(
        {
            "open": 500.0,
            "current": 505.0,
            "vix_current": 35.0,
            # vix_open intentionally omitted
        }
    )

    assert gate["trade_allowed"] is False
    assert gate["vix"]["available"] is True
    assert gate["vix"]["level_regime"] == "block"
    assert gate["vix"]["direction_regime"] == "unknown"
    assert any("block level" in reason for reason in gate["reasons"])


def test_market_regime_applies_vix_caution_with_current_only_no_open():
    """VIX caution-level size reduction fires even when vix_open is absent."""
    gate = evaluate_market_regime(
        {
            "open": 500.0,
            "current": 505.0,
            "vix_current": 22.0,
            # vix_open intentionally omitted
        }
    )

    assert gate["trade_allowed"] is True
    assert gate["vix"]["available"] is True
    assert gate["vix"]["level_regime"] == "caution"
    assert gate["vix"]["direction_regime"] == "unknown"
    assert gate["size_multiplier"] < 1.0
