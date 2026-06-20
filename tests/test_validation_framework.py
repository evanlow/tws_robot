from autonomous.validation_framework import ValidationFramework, ValidationThresholds


def _record(r_value):
    return {
        "outcome": {
            "realized": True,
            "realized_r_multiple": r_value,
        }
    }


def test_validation_framework_passes_good_realized_sample():
    records = [_record(1.0), _record(0.5), _record(-0.5), _record(1.0), _record(0.5)]
    framework = ValidationFramework(
        ValidationThresholds(
            min_trades=5,
            min_avg_r=0.1,
            min_win_rate=0.5,
            max_drawdown_r=2.0,
        )
    )

    report = framework.evaluate(records)

    assert report.passed is True
    assert report.trades == 5
    assert report.wins == 4
    assert report.avg_r > 0.0


def test_validation_framework_fails_small_sample():
    framework = ValidationFramework(ValidationThresholds(min_trades=3))

    report = framework.evaluate([_record(1.0)])

    assert report.passed is False
    assert any("trades" in reason for reason in report.reasons)


def test_validation_framework_detects_drawdown_failure():
    records = [_record(2.0), _record(-1.0), _record(-1.0), _record(-1.0), _record(2.0)]
    framework = ValidationFramework(
        ValidationThresholds(
            min_trades=5,
            min_avg_r=-1.0,
            min_win_rate=0.0,
            max_drawdown_r=2.0,
        )
    )

    report = framework.evaluate(records)

    assert report.passed is False
    assert report.max_drawdown_r == 3.0
    assert any("max_drawdown" in reason for reason in report.reasons)


def test_validation_framework_ignores_nonfinite_r():
    records = [
        _record(1.0),
        _record(float("nan")),
        _record(float("inf")),
        _record(float("-inf")),
    ]

    report = ValidationFramework(ValidationThresholds(min_trades=1)).evaluate(records)

    assert report.trades == 1
    assert report.total_r == 1.0


def test_validation_framework_ignores_unrealized_records():
    records = [_record(1.0), {"outcome": {"realized": False, "realized_r_multiple": 5.0}}]

    report = ValidationFramework(ValidationThresholds(min_trades=1)).evaluate(records)

    assert report.trades == 1
    assert report.total_r == 1.0
