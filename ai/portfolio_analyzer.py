"""Portfolio Strategy Analyzer — deduces strategies and generates insights.

Combines rule-based heuristics (holding period, position size, P&L trajectory)
with optional LLM narration to classify each position's likely strategy and
produce a portfolio-level narrative.

Multi-leg option strategies (covered calls, protective puts, collars, etc.)
are detected by scanning cross-position relationships so the analyser can
reason about the portfolio *as a whole* rather than treating each position
in isolation.

Usage::

    from ai.portfolio_analyzer import PortfolioAnalyzer

    analyzer = PortfolioAnalyzer()
    result = analyzer.analyze_portfolio(positions, account_summary)
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy classification constants
# ---------------------------------------------------------------------------

STRATEGY_MOMENTUM = "momentum"
STRATEGY_MEAN_REVERSION = "mean_reversion"
STRATEGY_BUY_AND_HOLD = "buy_and_hold"
STRATEGY_VALUE = "value"
STRATEGY_INCOME = "income"
STRATEGY_SPECULATIVE = "speculative"
STRATEGY_HEDGING = "hedging"
STRATEGY_COVERED_CALL = "covered_call"
STRATEGY_PROTECTIVE_PUT = "protective_put"
STRATEGY_COLLAR = "collar"
STRATEGY_UNKNOWN = "unknown"

# Holding period thresholds (in days)
_SHORT_TERM_DAYS = 5
_MEDIUM_TERM_DAYS = 30
_LONG_TERM_DAYS = 90


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float, returning *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _holding_days(entry_time: Any) -> Optional[float]:
    """Return the number of calendar days since *entry_time*.

    Accepts ISO-format strings and ``datetime`` objects.
    Returns ``None`` when the input cannot be parsed.
    """
    if entry_time is None:
        return None
    if isinstance(entry_time, str):
        try:
            entry_time = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if isinstance(entry_time, datetime):
        now = datetime.now(timezone.utc)
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        return (now - entry_time).total_seconds() / 86400
    return None


# ---------------------------------------------------------------------------
# Option symbol parsing & multi-leg strategy detection
# ---------------------------------------------------------------------------

# Matches TWS-style option local symbols, e.g.:
#   "GOOG  260515C00200000"  or  "GOOG 260515P00240000"
# Group 1: underlying ticker, Group 2: expiry (YYMMDD),
# Group 3: right (C or P), Group 4: raw strike digits.
_OPT_SYMBOL_RE = re.compile(
    r"^([A-Z]+)\s+(\d{6})([CP])(\d+)$"
)


def extract_option_underlying(symbol: str) -> Optional[Dict[str, Any]]:
    """Parse a TWS option local-symbol into its components.

    Parameters
    ----------
    symbol : str
        A TWS-style option symbol like ``"GOOG 260515C00200000"``.

    Returns
    -------
    dict or None
        ``{"underlying": "GOOG", "expiry": "260515",
           "right": "C", "strike": 200.0}``
        Returns ``None`` when the symbol doesn't match the expected format.
    """
    if not symbol:
        return None
    m = _OPT_SYMBOL_RE.match(symbol.strip())
    if not m:
        return None
    raw_strike = m.group(4)
    # TWS encodes strike as integer in units of 1/1000 of a dollar
    strike = int(raw_strike) / 1000.0
    return {
        "underlying": m.group(1),
        "expiry": m.group(2),
        "right": m.group(3),  # "C" (call) or "P" (put)
        "strike": strike,
    }


def detect_multi_leg_strategies(
    positions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Scan the portfolio for multi-leg option strategies.

    Identifies combinations such as:
    * **Covered call** — long stock + short call on same underlying
    * **Protective put** — long stock + long put on same underlying
    * **Collar** — long stock + short call + long put on same underlying

    Parameters
    ----------
    positions : list[dict]
        Position dicts containing at least ``symbol``, ``side``, ``sec_type``.

    Returns
    -------
    list[dict]
        Each entry describes a detected multi-leg strategy with keys
        ``strategy``, ``underlying``, ``legs`` (list of symbols), and
        ``description``.
    """
    # Index positions by underlying
    long_stocks: Dict[str, Dict[str, Any]] = {}   # underlying → position
    short_calls: Dict[str, List[Dict[str, Any]]] = {}  # underlying → [positions]
    long_puts: Dict[str, List[Dict[str, Any]]] = {}
    short_puts: Dict[str, List[Dict[str, Any]]] = {}

    for pos in positions:
        symbol = pos.get("symbol", "")
        side = pos.get("side", "LONG")
        sec_type = pos.get("sec_type", "STK")

        if sec_type in ("STK", "") and side == "LONG":
            long_stocks[symbol] = pos
            continue

        if sec_type == "OPT":
            parsed = extract_option_underlying(symbol)
            if parsed is None:
                continue
            underlying = parsed["underlying"]
            right = parsed["right"]
            pos_with_parsed = {**pos, "_parsed_option": parsed}

            if right == "C" and side == "SHORT":
                short_calls.setdefault(underlying, []).append(pos_with_parsed)
            elif right == "P" and side == "LONG":
                long_puts.setdefault(underlying, []).append(pos_with_parsed)
            elif right == "P" and side == "SHORT":
                short_puts.setdefault(underlying, []).append(pos_with_parsed)

    detected: List[Dict[str, Any]] = []

    for underlying, stock_pos in long_stocks.items():
        has_short_calls = underlying in short_calls
        has_long_puts = underlying in long_puts

        if has_short_calls and has_long_puts:
            # Collar: long stock + short call + long put
            call_legs = [p.get("symbol") for p in short_calls[underlying]]
            put_legs = [p.get("symbol") for p in long_puts[underlying]]
            detected.append({
                "strategy": STRATEGY_COLLAR,
                "underlying": underlying,
                "legs": [underlying] + call_legs + put_legs,
                "description": (
                    f"Collar on {underlying}: long stock hedged with "
                    f"short call(s) and protective put(s). "
                    f"Limits both upside and downside risk."
                ),
            })
        elif has_short_calls:
            # Covered call: long stock + short call
            call_legs = [p.get("symbol") for p in short_calls[underlying]]
            call_details = []
            for p in short_calls[underlying]:
                parsed = p.get("_parsed_option", {})
                strike = parsed.get("strike", "?")
                expiry = parsed.get("expiry", "?")
                call_details.append(f"strike={strike}, expiry={expiry}")
            detected.append({
                "strategy": STRATEGY_COVERED_CALL,
                "underlying": underlying,
                "legs": [underlying] + call_legs,
                "description": (
                    f"Covered call on {underlying}: the short call(s) "
                    f"({'; '.join(call_details)}) are backed by the long "
                    f"stock position. The short call risk is capped because "
                    f"the trader owns the underlying shares and can deliver "
                    f"them if assigned. This is an intentional income / exit "
                    f"strategy, not a naked risk."
                ),
            })
        elif has_long_puts:
            # Protective put: long stock + long put
            put_legs = [p.get("symbol") for p in long_puts[underlying]]
            detected.append({
                "strategy": STRATEGY_PROTECTIVE_PUT,
                "underlying": underlying,
                "legs": [underlying] + put_legs,
                "description": (
                    f"Protective put on {underlying}: long stock position "
                    f"is hedged with put option(s) providing downside "
                    f"protection."
                ),
            })

    return detected


# ---------------------------------------------------------------------------
# Rule-based strategy deduction
# ---------------------------------------------------------------------------

def deduce_position_strategy(
    position: Dict[str, Any],
    multi_leg_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Classify a single position using rule-based heuristics.

    Parameters
    ----------
    position : dict
        Must contain at least ``symbol``.  Optional keys used for
        classification: ``entry_price``, ``current_price``, ``quantity``,
        ``market_value``, ``unrealized_pnl``, ``side``, ``sec_type``,
        ``entry_time``, ``portfolio_weight``.
    multi_leg_map : dict, optional
        Mapping of ``symbol → multi_leg_strategy_dict`` produced by
        :func:`detect_multi_leg_strategies`.  When provided, positions
        that belong to a detected multi-leg strategy are classified
        accordingly instead of being evaluated in isolation.

    Returns
    -------
    dict
        ``{"strategy": <str>, "confidence": <float 0-1>, "reasoning": <str>}``
    """
    symbol = position.get("symbol", "?")
    side = position.get("side", "LONG")
    sec_type = position.get("sec_type", "STK")
    entry_price = _safe_float(position.get("entry_price"))
    current_price = _safe_float(position.get("current_price"))
    unrealized_pnl = _safe_float(position.get("unrealized_pnl"))
    weight = _safe_float(position.get("portfolio_weight"))
    days_held = _holding_days(position.get("entry_time"))

    reasons: List[str] = []

    # --- Check if this position is part of a detected multi-leg strategy --
    if multi_leg_map and symbol in multi_leg_map:
        ml = multi_leg_map[symbol]
        return {
            "strategy": ml["strategy"],
            "confidence": 0.90,
            "reasoning": f"{symbol}: Part of {ml['strategy']} — {ml['description']}",
        }

    # --- Short option positions → hedging / income -----------------------
    if side == "SHORT" and sec_type == "OPT":
        return {
            "strategy": STRATEGY_INCOME,
            "confidence": 0.85,
            "reasoning": f"{symbol}: Short option position — likely premium income / hedging strategy.",
        }

    # --- Hedging via inverse/commodity ETFs ------------------------------
    hedging_keywords = {"SH", "SDS", "SPXS", "SQQQ", "VIX", "UVXY", "VIXY"}
    if symbol.upper() in hedging_keywords:
        return {
            "strategy": STRATEGY_HEDGING,
            "confidence": 0.80,
            "reasoning": f"{symbol}: Inverse/volatility product — likely a portfolio hedge.",
        }

    # --- Classify based on holding period & P&L --------------------------
    strategy = STRATEGY_UNKNOWN
    confidence = 0.40

    if days_held is not None:
        if days_held > _LONG_TERM_DAYS:
            strategy = STRATEGY_BUY_AND_HOLD
            confidence = 0.75
            reasons.append(f"held for {days_held:.0f} days (long-term)")
        elif days_held > _MEDIUM_TERM_DAYS:
            strategy = STRATEGY_VALUE
            confidence = 0.55
            reasons.append(f"held for {days_held:.0f} days (medium-term)")
        elif days_held <= _SHORT_TERM_DAYS:
            strategy = STRATEGY_MOMENTUM
            confidence = 0.60
            reasons.append(f"held for {days_held:.1f} days (short-term)")
        else:
            strategy = STRATEGY_MOMENTUM
            confidence = 0.50
            reasons.append(f"held for {days_held:.0f} days")

    # Adjust based on P&L trajectory
    if entry_price > 0 and current_price > 0:
        pnl_pct = (current_price - entry_price) / entry_price
        if abs(pnl_pct) > 0.20:
            if pnl_pct > 0:
                reasons.append(f"+{pnl_pct:.0%} gain — strong momentum")
                if strategy != STRATEGY_BUY_AND_HOLD:
                    strategy = STRATEGY_MOMENTUM
                    confidence = max(confidence, 0.65)
            else:
                reasons.append(f"{pnl_pct:.0%} loss — potentially caught in drawdown")
                confidence = max(0.30, confidence - 0.10)
        elif abs(pnl_pct) < 0.03 and days_held and days_held > _MEDIUM_TERM_DAYS:
            reasons.append("flat P&L on medium-term hold — possibly mean reversion or range trade")
            strategy = STRATEGY_MEAN_REVERSION
            confidence = 0.45

    # Weight-based adjustment
    if weight > 0.25:
        reasons.append(f"large position ({weight:.0%} of portfolio) — high conviction")
        confidence = min(1.0, confidence + 0.05)
    elif weight > 0 and weight < 0.03:
        reasons.append(f"small position ({weight:.1%}) — possibly speculative")
        if strategy == STRATEGY_UNKNOWN:
            strategy = STRATEGY_SPECULATIVE
            confidence = 0.45

    reasoning = f"{symbol}: " + "; ".join(reasons) if reasons else f"{symbol}: insufficient data for classification"
    return {"strategy": strategy, "confidence": confidence, "reasoning": reasoning}


def compute_strategy_mix(
    deductions: List[Dict[str, Any]],
    positions: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Compute portfolio-level strategy mix as weight-averaged percentages.

    Parameters
    ----------
    deductions : list[dict]
        Output of :func:`deduce_position_strategy` for each position.
    positions : list[dict]
        Corresponding position dicts (must include ``market_value``).

    Returns
    -------
    dict
        Strategy name → fraction of portfolio (sums to ~1.0).
    """
    mix: Dict[str, float] = {}
    total_value = sum(abs(_safe_float(p.get("market_value"))) for p in positions)
    if total_value <= 0:
        return mix

    for ded, pos in zip(deductions, positions):
        strat = ded.get("strategy", STRATEGY_UNKNOWN)
        mv = abs(_safe_float(pos.get("market_value")))
        mix[strat] = mix.get(strat, 0.0) + mv / total_value

    return mix


# ---------------------------------------------------------------------------
# LLM-powered portfolio analysis (optional enrichment)
# ---------------------------------------------------------------------------

def _build_portfolio_context(
    positions: List[Dict[str, Any]],
    deductions: List[Dict[str, Any]],
    strategy_mix: Dict[str, float],
    account_summary: Dict[str, Any],
    multi_leg_strategies: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Serialise portfolio data into a JSON string for LLM injection."""
    ctx = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account": {
            "equity": account_summary.get("equity", 0),
            "cash": account_summary.get("cash_balance", 0),
            "buying_power": account_summary.get("buying_power", 0),
        },
        "positions": [],
        "heuristic_strategy_mix": strategy_mix,
        "multi_leg_strategies": multi_leg_strategies or [],
    }
    for pos, ded in zip(positions, deductions):
        ctx["positions"].append({
            "symbol": pos.get("symbol"),
            "side": pos.get("side", "LONG"),
            "quantity": pos.get("quantity", 0),
            "entry_price": pos.get("entry_price", 0),
            "current_price": pos.get("current_price", 0),
            "market_value": pos.get("market_value", 0),
            "unrealized_pnl": pos.get("unrealized_pnl", 0),
            "weight": pos.get("portfolio_weight", 0),
            "entry_time": str(pos.get("entry_time", "")),
            "heuristic_strategy": ded.get("strategy"),
            "heuristic_confidence": ded.get("confidence"),
            "heuristic_reasoning": ded.get("reasoning"),
        })
    return json.dumps(ctx, indent=2, default=str)


class PortfolioAnalyzer:
    """High-level portfolio analysis combining heuristics + optional LLM."""

    def analyze_portfolio(
        self,
        positions: Dict[str, Dict[str, Any]],
        account_summary: Optional[Dict[str, Any]] = None,
        use_ai: bool = True,
    ) -> Dict[str, Any]:
        """Analyse the full portfolio and return structured insights.

        Parameters
        ----------
        positions : dict
            Mapping of ``symbol → position_dict`` (from ServiceManager).
        account_summary : dict, optional
            Account-level data (equity, cash, buying power).
        use_ai : bool
            When True and the AI client is available, enrich the analysis
            with an LLM-generated narrative.

        Returns
        -------
        dict
            Keys: ``deductions``, ``strategy_mix``, ``ai_narrative``,
            ``ai_recommendations``, ``positions_enriched``,
            ``multi_leg_strategies``.
        """
        account_summary = account_summary or {}

        # Flatten positions to a list and annotate with weights
        total_value = sum(
            abs(_safe_float(p.get("market_value"))) for p in positions.values()
        )
        pos_list: List[Dict[str, Any]] = []
        for symbol, pos in positions.items():
            enriched = dict(pos)
            enriched["symbol"] = symbol
            mv = abs(_safe_float(pos.get("market_value")))
            enriched["portfolio_weight"] = mv / total_value if total_value > 0 else 0
            pos_list.append(enriched)

        # Detect multi-leg option strategies across the portfolio
        multi_leg_strategies = detect_multi_leg_strategies(pos_list)

        # Build a map from symbol → multi-leg strategy for quick lookup
        multi_leg_map: Dict[str, Dict[str, Any]] = {}
        for ml in multi_leg_strategies:
            for leg_symbol in ml.get("legs", []):
                multi_leg_map[leg_symbol] = ml

        # Rule-based strategy deductions (now portfolio-aware)
        deductions = [
            deduce_position_strategy(p, multi_leg_map=multi_leg_map)
            for p in pos_list
        ]
        strategy_mix = compute_strategy_mix(deductions, pos_list)

        # Build enriched positions list
        positions_enriched = []
        for pos, ded in zip(pos_list, deductions):
            entry = {
                **pos,
                "deduced_strategy": ded["strategy"],
                "strategy_confidence": ded["confidence"],
                "strategy_reasoning": ded["reasoning"],
            }
            # Tag positions that belong to a multi-leg strategy
            sym = pos.get("symbol", "")
            if sym in multi_leg_map:
                entry["multi_leg_strategy"] = multi_leg_map[sym]["strategy"]
                entry["multi_leg_description"] = multi_leg_map[sym]["description"]
            positions_enriched.append(entry)

        result: Dict[str, Any] = {
            "deductions": deductions,
            "strategy_mix": strategy_mix,
            "positions_enriched": positions_enriched,
            "multi_leg_strategies": multi_leg_strategies,
            "ai_narrative": None,
            "ai_recommendations": [],
            "ai_risk_assessment": None,
            "ai_strategy_mix": None,
        }

        # LLM enrichment (optional)
        if use_ai:
            try:
                from ai.client import get_client
                from ai.prompts import Prompts

                client = get_client()
                if client is not None:
                    ctx_json = _build_portfolio_context(
                        pos_list, deductions, strategy_mix, account_summary,
                        multi_leg_strategies=multi_leg_strategies,
                    )
                    system_prompt = Prompts.PORTFOLIO_STRATEGY_ANALYSIS.format(
                        portfolio_json=ctx_json,
                    )
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "Analyse this portfolio."},
                    ]
                    raw = client.chat(messages)
                    ai_result = _parse_ai_json(raw)
                    if ai_result:
                        result["ai_narrative"] = ai_result.get("narrative")
                        result["ai_recommendations"] = ai_result.get("recommendations", [])
                        result["ai_risk_assessment"] = ai_result.get("risk_assessment")
                        result["ai_strategy_mix"] = ai_result.get("strategy_mix")
                        # Merge AI position-level classifications if available
                        ai_positions = {
                            p["symbol"]: p
                            for p in ai_result.get("positions", [])
                            if isinstance(p, dict) and "symbol" in p
                        }
                        for pe in result["positions_enriched"]:
                            ai_pos = ai_positions.get(pe["symbol"])
                            if ai_pos:
                                pe["ai_strategy"] = ai_pos.get("strategy")
                                pe["ai_confidence"] = ai_pos.get("confidence")
                                pe["ai_reasoning"] = ai_pos.get("reasoning")
            except Exception:
                logger.exception("AI portfolio analysis failed — returning heuristics only")

        return result


def _parse_ai_json(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse of an LLM JSON response.

    Handles common issues like markdown code fences around JSON.
    """
    if not raw:
        return None
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse AI JSON response: %s...", text[:200])
        return None
