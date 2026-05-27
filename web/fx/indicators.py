"""FX indicator helper functions for the FX Research Dashboard.

Small, testable utility functions for common FX research calculations.
All functions handle edge cases (zero denominator, empty lists, etc.) safely.
"""

from __future__ import annotations


def pct_change(current: float, previous: float) -> float | None:
    """Calculate percentage change from previous to current value.

    Args:
        current: Current value.
        previous: Previous value.

    Returns:
        Percentage change as a float, or None if previous is zero.
    """
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100


def simple_moving_average(values: list[float], window: int) -> float | None:
    """Calculate a simple moving average over the given window.

    Args:
        values: List of numeric values (most recent last).
        window: Number of periods to average.

    Returns:
        Average of the last ``window`` values, or None if there are
        fewer values than the window size or the window is not positive.
    """
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def z_score(value: float, mean: float, std_dev: float) -> float | None:
    """Calculate the z-score of a value given a mean and standard deviation.

    Args:
        value: The observation to score.
        mean: Population or sample mean.
        std_dev: Population or sample standard deviation.

    Returns:
        Z-score as a float, or None if std_dev is zero.
    """
    if std_dev == 0:
        return None
    return (value - mean) / std_dev
