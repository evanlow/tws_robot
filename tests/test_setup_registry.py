from autonomous.setup_registry import SetupRegistry, setup_id_for_record


def _record(**overrides):
    record = {
        "schema_version": 3,
        "evidence_type": "autonomous_outcome",
        "timestamp": "2026-06-22T12:00:00+00:00",
        "symbol": "AAA",
        "strategy_bucket": {
            "signal_label": "Confirmed Rebound",
            "quality_label": "Strong",
            "momentum_label": "Confirmed Rebound",
            "market_classification": "Bullish / Volatility Acceptable",
            "vix_level_regime": "normal",
            "vix_direction_regime": "falling",
            "sector": "Technology",
        },
        "features": {
            "sector_regime": "sector_supportive",
            "time_of_day_regime": "regular_session",
            "support_distance_pct": 0.025,
            "resistance_room_pct": 0.12,
            "adr_pct": 0.035,
        },
        "trade_plan": {
            "symbol": "AAA",
            "trade_type": "BUY_SHARES",
        },
        "outcome": {
            "realized": True,
            "realized_r_multiple": 1.0,
        },
    }
    record.update(overrides)
    return record


def test_setup_registry_builds_deterministic_readable_setup_id():
    registry = SetupRegistry()
    record = _record()

    metadata = registry.metadata_for_record(record)

    assert metadata.setup_id == setup_id_for_record(record)
    assert metadata.setup_id.startswith("setup_v1__")
    assert "signal-confirmed_rebound" in metadata.setup_id
    assert "quality-strong" in metadata.setup_id
    assert "support-near_support" in metadata.setup_id
    assert "resistance-open_resistance_room" in metadata.setup_id
    assert "vol-normal_adr_volatility" in metadata.setup_id
    assert metadata.dimensions.basket_context == "single_leg"
    assert metadata.observation_count == 1
    assert metadata.symbols == ["AAA"]


def test_setup_registry_uses_explicit_unknown_buckets_for_sparse_records():
    metadata = SetupRegistry().metadata_for_record({
        "symbol": "BBB",
        "outcome": {"realized": True, "realized_r_multiple": -0.5},
    })

    dimensions = metadata.dimensions

    assert dimensions.signal_label == "unknown_signal"
    assert dimensions.quality_label == "unknown_quality"
    assert dimensions.vix_level_regime == "unknown_vix_level"
    assert dimensions.sector_regime == "unknown_sector_regime"
    assert dimensions.support_distance_bucket == "unknown_support_distance"
    assert dimensions.resistance_room_bucket == "unknown_resistance_room"
    assert dimensions.adr_volatility_bucket == "unknown_adr_volatility"
    assert dimensions.basket_context == "unknown_basket_context"


def test_setup_registry_derives_buckets_from_selected_candidate_when_features_missing():
    record = {
        "symbol": "CCC",
        "selected": {
            "candidate": {
                "signal_label": "Pullback",
                "last_price": 100.0,
                "support_price": 94.0,
                "resistance_price": 102.0,
                "extras": {
                    "quality_label": "Acceptable",
                    "momentum_label": "VWAP Reclaim",
                    "adr_pct": 0.07,
                    "sector_regime": "sector_mixed",
                },
            }
        },
        "trade_plan": {"symbol": "CCC", "trade_type": "BUY_SHARES", "basket_id": "B1"},
        "outcome": {"realized": True, "realized_r_multiple": 0.2},
    }

    dimensions = SetupRegistry().metadata_for_record(record).dimensions

    assert dimensions.signal_label == "Pullback"
    assert dimensions.quality_label == "Acceptable"
    assert dimensions.momentum_label == "VWAP Reclaim"
    assert dimensions.support_distance_bucket == "moderate_support_distance"
    assert dimensions.resistance_room_bucket == "tight_resistance_room"
    assert dimensions.adr_volatility_bucket == "elevated_adr_volatility"
    assert dimensions.sector_regime == "sector_mixed"
    assert dimensions.basket_context == "basket_leg"


def test_setup_registry_builds_metadata_registry_without_performance_aggregation():
    records = [
        _record(symbol="AAA"),
        _record(symbol="BBB"),
        _record(
            symbol="CCC",
            features={
                "sector_regime": "sector_supportive",
                "time_of_day_regime": "regular_session",
                "support_distance_pct": 0.12,
                "resistance_room_pct": 0.12,
                "adr_pct": 0.035,
            },
        ),
    ]

    registry = SetupRegistry().build_registry(records)

    assert len(registry) == 2
    first = [item for item in registry.values() if item.observation_count == 2][0]
    assert first.symbols == ["AAA", "BBB"]
    assert "avg_r" not in first.to_dict()
