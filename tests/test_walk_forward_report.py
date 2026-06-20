from datetime import datetime, timedelta, timezone

from autonomous.validation_framework import ValidationThresholds
from autonomous.walk_forward_report import ChronoValidator


def _record(index, r_value=0.5):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return {
        "timestamp": ts.isoformat(),
        "outcome": {
            "realized": True,
            "realized_r_multiple": r_value,
        },
    }


def test_chrono_validator_requires_enough_records():
    report = ChronoValidator(earlier_size=3, later_size=2).evaluate([_record(1)])

    assert report.passed is False
    assert "insufficient" in report.reasons[0]


def test_chrono_validator_builds_sequential_windows():
    records = [_record(i, 0.5) for i in range(6)]
    validator = ChronoValidator(
        earlier_size=3,
        later_size=2,
        step_size=1,
        thresholds=ValidationThresholds(
            min_trades=2,
            min_avg_r=0.1,
            min_win_rate=0.5,
            max_drawdown_r=2.0,
        ),
    )

    report = validator.evaluate(records)

    assert report.windows
    assert report.passed is True
    assert report.windows[0].earlier_count == 3
    assert report.windows[0].later_count == 2
