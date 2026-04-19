"""Market Outlook Generator — AI-powered daily market briefing.

Combines market overview data, last session snapshots, portfolio positions,
strategy mix, and sentiment scores to produce a structured market outlook
that is displayed prominently on the dashboard.

Results are cached with a configurable TTL (default 15 minutes) to avoid
redundant LLM calls on every page load.

Usage::

    from ai.market_outlook import MarketOutlookGenerator

    generator = MarketOutlookGenerator()
    outlook = generator.get_outlook(
        market_overview=overview_dict,
        positions=positions_dict,
        strategy_mix=strategy_mix_dict,
        account_summary=account_dict,
    )
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache TTL — 15 minutes
_OUTLOOK_CACHE_TTL = 15 * 60


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float, returning *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_market_pulse(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive a compact market pulse from index snapshots.

    Returns a dict with aggregate sentiment, regional summaries,
    and VIX data — suitable for rendering without AI.

    Parameters
    ----------
    snapshots : list[dict]
        Index snapshot dicts from ``MarketOverviewService.get_overview()``.

    Returns
    -------
    dict
        Keys: ``overall_sentiment``, ``sentiment_label``, ``regions``,
        ``vix``, ``summary_text``.
    """
    if not snapshots:
        return {
            "overall_sentiment": 0.0,
            "sentiment_label": "neutral",
            "regions": {},
            "vix": None,
            "summary_text": "No market data available.",
        }

    # Group by region and compute aggregate change percentages
    region_data: Dict[str, List[float]] = {}
    vix_snapshot: Optional[Dict[str, Any]] = None

    for s in snapshots:
        symbol = s.get("symbol", "")
        region = s.get("region", "US")
        change_pct = s.get("change_pct")

        # Track VIX separately
        if symbol == "^VIX":
            vix_snapshot = s
            continue

        if change_pct is not None:
            region_data.setdefault(region, []).append(change_pct)

    # Compute regional averages
    regions: Dict[str, Dict[str, Any]] = {}
    all_changes: List[float] = []

    for region, changes in region_data.items():
        if changes:
            avg = sum(changes) / len(changes)
            regions[region] = {
                "avg_change_pct": round(avg, 2),
                "index_count": len(changes),
                "direction": "up" if avg > 0.1 else ("down" if avg < -0.1 else "flat"),
            }
            all_changes.extend(changes)

    # Overall sentiment: simple average of all index changes, normalised to [-1, 1]
    if all_changes:
        raw_avg = sum(all_changes) / len(all_changes)
        # Normalise: ±2% maps to ±1.0
        overall = max(-1.0, min(1.0, raw_avg / 2.0))
    else:
        overall = 0.0

    if overall > 0.25:
        label = "bullish"
    elif overall > 0.05:
        label = "slightly bullish"
    elif overall < -0.25:
        label = "bearish"
    elif overall < -0.05:
        label = "slightly bearish"
    else:
        label = "neutral"

    # Build human-readable summary
    parts: List[str] = []
    for region_name in ["US", "Europe", "Asia"]:
        r = regions.get(region_name)
        if r:
            direction = "▲" if r["direction"] == "up" else ("▼" if r["direction"] == "down" else "▬")
            parts.append(f"{region_name} {direction} {r['avg_change_pct']:+.2f}%")

    vix_info = None
    if vix_snapshot:
        vix_price = _safe_float(vix_snapshot.get("price"))
        vix_change = vix_snapshot.get("change_pct")
        vix_info = {
            "price": round(vix_price, 2) if vix_price else None,
            "change_pct": round(vix_change, 2) if vix_change is not None else None,
            "level": (
                "elevated" if vix_price > 25
                else ("moderate" if vix_price > 18 else "low")
            ) if vix_price else "unknown",
        }
        if vix_price:
            parts.append(f"VIX {vix_price:.1f}")

    summary = " | ".join(parts) if parts else "No market data available."

    return {
        "overall_sentiment": round(overall, 3),
        "sentiment_label": label,
        "regions": regions,
        "vix": vix_info,
        "summary_text": summary,
    }


def build_outlook_context(
    *,
    market_pulse: Dict[str, Any],
    snapshots: List[Dict[str, Any]],
    positions: Optional[Dict[str, Dict[str, Any]]] = None,
    strategy_mix: Optional[Dict[str, float]] = None,
    account_summary: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a JSON context string for the LLM market outlook prompt.

    Parameters
    ----------
    market_pulse : dict
        Output of :func:`compute_market_pulse`.
    snapshots : list[dict]
        Raw index snapshots.
    positions : dict, optional
        Current portfolio positions (symbol → position dict).
    strategy_mix : dict, optional
        Strategy name → weight from :mod:`ai.portfolio_analyzer`.
    account_summary : dict, optional
        Account-level data (equity, cash, buying power).

    Returns
    -------
    str
        JSON string for embedding in the LLM prompt.
    """
    # Compact snapshot summaries (name, region, change %)
    index_summaries = []
    for s in snapshots:
        index_summaries.append({
            "name": s.get("name", s.get("symbol")),
            "region": s.get("region"),
            "price": s.get("price"),
            "change_pct": s.get("change_pct"),
            "prev_close": s.get("prev_close"),
        })

    # Portfolio summary — always include account-level data when available,
    # even if individual position details have not yet been received from TWS.
    portfolio_summary: Optional[Dict[str, Any]] = None
    if positions:
        total_value = sum(
            abs(_safe_float(p.get("market_value"))) for p in positions.values()
        )
        symbols = list(positions.keys())
        portfolio_summary = {
            "position_count": len(positions),
            "symbols": symbols[:20],  # Cap for prompt size
            "total_value": round(total_value, 2),
            "strategy_mix": strategy_mix or {},
        }
        if account_summary:
            portfolio_summary["equity"] = account_summary.get("equity", 0)
    elif account_summary:
        # Detailed positions not yet loaded, but account-level data exists.
        # Provide what we can so the LLM avoids the "portfolio data
        # unavailable" phrasing.
        portfolio_summary = {
            "position_count": account_summary.get("position_count", 0),
            "symbols": [],
            "total_value": 0,
            "strategy_mix": strategy_mix or {},
            "equity": account_summary.get("equity", 0),
            "unrealized_pnl": account_summary.get("unrealized_pnl", 0),
            "daily_pnl": account_summary.get("daily_pnl", 0),
            "note": "Individual position details are still loading; "
                    "account-level figures are shown.",
        }

    ctx = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_pulse": market_pulse,
        "index_data": index_summaries,
        "portfolio": portfolio_summary,
    }
    return json.dumps(ctx, indent=2, default=str)


def _parse_outlook_json(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse of LLM JSON response for market outlook."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse market outlook JSON: %s...", text[:200])
        return None


class MarketOutlookGenerator:
    """Generates and caches AI-powered market outlook for the dashboard.

    Thread-safe: all public methods acquire ``_lock``.  When the cache is
    stale, only one thread performs the (potentially slow) LLM generation;
    other concurrent callers wait and receive the freshly cached result.
    """

    # Short TTL used when no snapshots are available so the dashboard
    # picks up real data as soon as the background refresh completes.
    _EMPTY_DATA_TTL = 30  # seconds

    def __init__(self, cache_ttl: int = _OUTLOOK_CACHE_TTL) -> None:
        self._lock = threading.Lock()
        # Event starts set so the very first concurrent waiter (if any)
        # proceeds immediately rather than blocking forever.
        self._generation_done = threading.Event()
        self._generation_done.set()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[float] = None
        self._cache_ttl = cache_ttl
        self._cache_ttl_active = cache_ttl
        self._generating = False
        # Track whether the cached outlook was generated with full position
        # data.  When it was not, the cache is auto-invalidated as soon as
        # positions become available so the user doesn't see a stale
        # "portfolio data unavailable" message for the entire TTL.
        self._cache_had_positions = False

    def try_get_cached(
        self,
        *,
        positions: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return a fresh cached outlook, or ``None``.

        This is a **cache-only** check — it never triggers generation.
        It performs the same auto-invalidation as :meth:`get_outlook`:
        if the cached outlook was generated without positions but
        *positions* are now available the cache is cleared and ``None``
        is returned so the caller can gather full context and regenerate.
        """
        with self._lock:
            self._maybe_invalidate_for_positions(positions)

            if self._cache and self._cache_time:
                age = time.time() - self._cache_time
                if age < self._cache_ttl_active:
                    cached = dict(self._cache)
                    cached["from_cache"] = True
                    return cached
        return None

    def get_outlook(
        self,
        *,
        market_overview: Optional[Dict[str, Any]] = None,
        positions: Optional[Dict[str, Dict[str, Any]]] = None,
        strategy_mix: Optional[Dict[str, float]] = None,
        account_summary: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Return the current market outlook, generating if needed.

        Parameters
        ----------
        market_overview : dict, optional
            Output of ``MarketOverviewService.get_overview()``.
        positions : dict, optional
            Current portfolio positions.
        strategy_mix : dict, optional
            Portfolio strategy mix from ``PortfolioAnalyzer``.
        account_summary : dict, optional
            Account-level data.
        force_refresh : bool
            When True, bypass cache and regenerate.

        Returns
        -------
        dict
            Market outlook with keys: ``market_pulse``, ``ai_session_recap``,
            ``ai_portfolio_outlook``, ``ai_recommendations``,
            ``generated_at``, ``from_cache``.
        """
        should_generate = False

        with self._lock:
            # Auto-invalidate the cache when it was generated without
            # portfolio data but positions are now available.  This ensures
            # the user quickly gets a portfolio-aware outlook once TWS
            # callbacks populate positions.
            self._maybe_invalidate_for_positions(positions)

            # Serve from cache if fresh
            if not force_refresh and self._cache and self._cache_time:
                age = time.time() - self._cache_time
                if age < self._cache_ttl_active:
                    cached = dict(self._cache)
                    cached["from_cache"] = True
                    return cached

            # Cache is stale — decide whether *we* generate or wait
            if self._generating:
                # Another thread is already generating — wait for it
                pass
            else:
                self._generating = True
                self._generation_done.clear()
                should_generate = True

        if not should_generate:
            # Wait for the in-flight generation to finish, then return cache
            self._generation_done.wait(timeout=60)
            with self._lock:
                if self._cache:
                    # Re-check: the generation that just finished may not
                    # have had positions while this caller does.  Invalidate
                    # so the *next* request regenerates with positions.
                    if bool(positions) and not self._cache_had_positions:
                        logger.info(
                            "Post-wait: cached outlook lacks positions "
                            "— invalidating for next request"
                        )
                        self._cache = None
                        self._cache_time = None
                    else:
                        cached = dict(self._cache)
                        cached["from_cache"] = True
                        return cached
            # Fallback: generation failed or timed out — compute pulse only
            snapshots = []
            if market_overview:
                snapshots = market_overview.get("snapshots", [])
            return {
                "market_pulse": compute_market_pulse(snapshots),
                "ai_session_recap": None,
                "ai_portfolio_outlook": None,
                "ai_recommendations": [],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "from_cache": False,
            }

        # --- This thread is the generator ---
        try:
            result = self._generate(
                market_overview=market_overview,
                positions=positions,
                strategy_mix=strategy_mix,
                account_summary=account_summary,
            )
            return result
        finally:
            with self._lock:
                self._generating = False
            self._generation_done.set()

    # -- internal helpers --------------------------------------------------

    def _maybe_invalidate_for_positions(
        self,
        positions: Optional[Dict[str, Dict[str, Any]]],
    ) -> None:
        """Clear cache when it was generated without positions but positions
        are now available.  **Must be called while holding ``_lock``.**
        """
        if (bool(positions) and not self._cache_had_positions
                and self._cache and self._cache_time):
            logger.info(
                "Positions now available — invalidating portfolio-less "
                "outlook cache"
            )
            self._cache = None
            self._cache_time = None

    def _generate(
        self,
        *,
        market_overview: Optional[Dict[str, Any]],
        positions: Optional[Dict[str, Dict[str, Any]]],
        strategy_mix: Optional[Dict[str, float]],
        account_summary: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Perform the actual generation (pulse + optional AI enrichment)."""
        # Compute data-only market pulse (always available, no AI needed)
        snapshots = []
        if market_overview:
            snapshots = market_overview.get("snapshots", [])
        market_pulse = compute_market_pulse(snapshots)

        # Build result with data-only defaults
        result: Dict[str, Any] = {
            "market_pulse": market_pulse,
            "ai_session_recap": None,
            "ai_portfolio_outlook": None,
            "ai_recommendations": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "from_cache": False,
        }

        # Attempt AI enrichment
        try:
            from ai.client import get_client
            from ai.prompts import Prompts

            client = get_client()
            if client is not None and snapshots:
                context_json = build_outlook_context(
                    market_pulse=market_pulse,
                    snapshots=snapshots,
                    positions=positions,
                    strategy_mix=strategy_mix,
                    account_summary=account_summary,
                )
                system_prompt = Prompts.MARKET_OUTLOOK.format(
                    context_json=context_json,
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Generate today's market outlook."},
                ]
                raw = client.chat(messages)
                ai_result = _parse_outlook_json(raw)
                if ai_result:
                    result["ai_session_recap"] = ai_result.get("session_recap")
                    result["ai_portfolio_outlook"] = ai_result.get("portfolio_outlook")
                    result["ai_recommendations"] = ai_result.get(
                        "recommendations", []
                    )
        except Exception:
            logger.exception("AI market outlook generation failed")

        # Cache the result — use a short TTL when no snapshots were available
        # so the dashboard picks up real data once the background refresh fills it.
        effective_ttl = self._cache_ttl if snapshots else self._EMPTY_DATA_TTL
        with self._lock:
            self._cache = result
            self._cache_time = time.time()
            self._cache_ttl_active = effective_ttl
            self._cache_had_positions = bool(positions)

        return result

    def invalidate(self) -> None:
        """Clear the cached outlook so the next call regenerates it."""
        with self._lock:
            self._cache = None
            self._cache_time = None

    def is_stale(self) -> bool:
        """Return True if cache is empty or older than the TTL."""
        with self._lock:
            if not self._cache or not self._cache_time:
                return True
            return (time.time() - self._cache_time) >= self._cache_ttl_active


# ──────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────

_instance: Optional[MarketOutlookGenerator] = None
_instance_lock = threading.Lock()


def get_market_outlook_generator() -> MarketOutlookGenerator:
    """Return (or create) the module-level singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MarketOutlookGenerator()
    return _instance
