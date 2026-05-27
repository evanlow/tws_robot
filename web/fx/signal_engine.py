"""Signal engine helpers for the FX Research Dashboard.

Transparent, rule-based scoring utilities that power research signal
classification. No AI-generated or external signals are used here.
"""


def confidence_from_score(score: int, max_score: int = 6) -> int:
    """Convert a raw score into a confidence percentage (0–100).

    Args:
        score: Raw signal score (non-negative integer).
        max_score: Maximum possible score. Must be greater than zero.

    Returns:
        Confidence percentage clamped to [0, 100].
    """
    if max_score <= 0:
        return 0
    raw = int(round((max(0, score) / max_score) * 100))
    return min(100, raw)


def classify_bias(score: int) -> str:
    """Classify a directional bias label from a signal score.

    Positive scores indicate a bullish bias; negative scores indicate
    a bearish bias; zero is neutral.

    Args:
        score: Signed integer signal score.

    Returns:
        One of 'Bullish', 'Bearish', or 'Neutral'.
    """
    if score > 0:
        return "Bullish"
    if score < 0:
        return "Bearish"
    return "Neutral"
