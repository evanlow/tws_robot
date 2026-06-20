from autonomous.technical_levels import compute_support_resistance_levels


def test_compute_support_resistance_nearest_levels():
    bars = [
        {"low": 90, "high": 98, "close": 95},
        {"low": 94, "high": 101, "close": 99},
        {"low": 96, "high": 104, "close": 100},
        {"low": 97, "high": 107, "close": 102},
        {"low": 98, "high": 110, "close": 103},
        {"low": 99, "high": 108, "close": 104},
    ]

    levels = compute_support_resistance_levels(bars, current_price=105.0, lookback_days=6)

    assert levels["valid"] is True
    assert levels["support_price"] == 99.0
    assert levels["resistance_price"] == 107.0
    assert levels["support_source"] == "nearest_recent_low_below_price"
    assert levels["resistance_source"] == "nearest_recent_high_above_price"


def test_compute_support_resistance_handles_insufficient_data():
    levels = compute_support_resistance_levels([], current_price=100.0)

    assert levels["valid"] is False
    assert levels["support_price"] is None
    assert levels["resistance_price"] is None
