"""Market Sentiment Feed — Enhancement 5.

Provides per-symbol sentiment scores derived from OpenAI's knowledge of
recent market news and conditions.  Results are cached with a configurable
TTL to avoid per-bar API calls.

Usage::

    from data.sentiment_feed import fetch_sentiment, SentimentCache

    score = fetch_sentiment("AAPL")  # float in [-1.0, 1.0]

    # Or use the cache directly for custom TTLs
    cache = SentimentCache(ttl_seconds=600)
    result = cache.get("MSFT")
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from ai.client import get_client
from ai.prompts import Prompts

logger = logging.getLogger(__name__)

# Default cache TTL: 15 minutes
_DEFAULT_TTL = 15 * 60

# Module-level default cache instance
_default_cache: Optional["SentimentCache"] = None


@dataclass
class SentimentResult:
    """Cached sentiment result for a symbol."""
    symbol: str
    score: float         # [-1.0, 1.0]
    rationale: str
    fetched_at: float = field(default_factory=time.time)

    def is_expired(self, ttl_seconds: int) -> bool:
        """Return True if the result is older than ``ttl_seconds``."""
        return (time.time() - self.fetched_at) > ttl_seconds


class SentimentCache:
    """Thread-safe in-memory cache for sentiment scores.

    Args:
        ttl_seconds: How long a cached score remains valid.
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL) -> None:
        self._ttl = ttl_seconds
        self._cache: Dict[str, SentimentResult] = {}

    def get(self, symbol: str) -> Optional[SentimentResult]:
        """Return a valid cached result, or None if missing/expired."""
        result = self._cache.get(symbol)
        if result is None or result.is_expired(self._ttl):
            return None
        return result

    def set(self, result: SentimentResult) -> None:
        """Store a sentiment result in the cache."""
        self._cache[result.symbol] = result

    def invalidate(self, symbol: str) -> None:
        """Remove a cached result for the given symbol."""
        self._cache.pop(symbol, None)

    def clear(self) -> None:
        """Clear all cached results."""
        self._cache.clear()


def fetch_sentiment(
    symbol: str,
    cache: Optional[SentimentCache] = None,
    ttl_seconds: int = _DEFAULT_TTL,
) -> float:
    """Return a sentiment score for ``symbol`` in the range [-1.0, 1.0].

    Uses the module-level cache by default; pass a custom ``SentimentCache``
    instance to use a different cache or TTL.

    Returns 0.0 (neutral) when AI is disabled or the request fails.
    """
    global _default_cache

    if cache is None:
        if _default_cache is None:
            _default_cache = SentimentCache(ttl_seconds=ttl_seconds)
        cache = _default_cache

    # Return cached value if still valid
    cached = cache.get(symbol)
    if cached is not None:
        logger.debug("Sentiment cache hit for %s: %.2f", symbol, cached.score)
        return cached.score

    client = get_client()
    if client is None:
        logger.debug("AI disabled — returning neutral sentiment for %s.", symbol)
        return 0.0

    system_prompt = Prompts.MARKET_SENTIMENT.format(symbol=symbol)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"What is the current market sentiment for {symbol}?"},
    ]

    try:
        raw = client.chat(messages, temperature=0.2)
        parsed = json.loads(raw)
        score = float(parsed.get("score", 0.0))
        # Clamp to [-1, 1]
        score = max(-1.0, min(1.0, score))
        rationale = str(parsed.get("rationale", ""))
    except (RuntimeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.error("Sentiment fetch failed for %s: %s", symbol, exc)
        return 0.0

    result = SentimentResult(symbol=symbol, score=score, rationale=rationale)
    cache.set(result)
    logger.info("Sentiment for %s: %.2f (%s)", symbol, score, rationale)
    return score
