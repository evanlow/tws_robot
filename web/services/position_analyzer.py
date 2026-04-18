"""Position Analyzer — deduce trading strategies from current TWS positions.

Examines the live positions held in the ServiceManager cache and groups
them into recognised strategy patterns (covered calls, spreads, iron
condors, etc.).  Each detected pattern is returned as an
``InferredStrategy`` dict that the UI can display and the user can
optionally promote to a managed strategy.

Usage::

    from web.services.position_analyzer import PositionAnalyzer

    analyzer = PositionAnalyzer()
    detected = analyzer.analyze(positions_dict)
    # detected → list of InferredStrategy dicts
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class InferredStrategy:
    """A strategy pattern deduced from live positions."""

    strategy_type: str          # e.g. "CoveredCall", "IronCondor", "LongEquity"
    description: str            # human-readable explanation
    confidence: float           # 0.0 – 1.0
    symbols: List[str]          # underlying symbol(s)
    positions: List[Dict[str, Any]]   # position dicts involved
    targets: Dict[str, Any]     # suggested targets
    id: str = ""                # auto-generated unique id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "strategy_type": self.strategy_type,
            "description": self.description,
            "confidence": self.confidence,
            "symbols": self.symbols,
            "positions": self.positions,
            "targets": self.targets,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPTION_RE = re.compile(
    r"^(?P<underlying>[A-Z]+)\s*"     # underlying symbol
    r"(?P<date>\d{6})"                # YYMMDD expiry
    r"(?P<right>[CP])"                # Call or Put
    r"(?P<strike>[\d.]+)$"           # strike price
)


def _parse_option_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Try to extract underlying, expiry, right, strike from an OCC-style symbol.

    TWS ``localSymbol`` for US equity options looks like ``AAPL  250620C00200000``
    but by the time positions reach the ServiceManager cache the symbol
    may have been normalised.  We also accept the compact ``AAPL250620C200``
    format commonly seen in TWS ``localSymbol`` with spaces stripped.

    Returns ``None`` if the symbol doesn't match option patterns.
    """
    # Strip all whitespace
    clean = symbol.replace(" ", "")

    # Try OCC format first: AAPL250620C00200000  (8-digit strike ×1000)
    occ_re = re.compile(
        r"^(?P<underlying>[A-Z]+)"
        r"(?P<date>\d{6})"
        r"(?P<right>[CP])"
        r"(?P<strike>\d{8})$"
    )
    m2 = occ_re.match(clean)
    if m2:
        return {
            "underlying": m2.group("underlying"),
            "expiry": m2.group("date"),
            "right": m2.group("right"),
            "strike": float(m2.group("strike")) / 1000.0,
        }

    # Compact format: AAPL250620C200 or AAPL250620C200.5
    m = _OPTION_RE.match(clean)
    if m:
        return {
            "underlying": m.group("underlying"),
            "expiry": m.group("date"),
            "right": m.group("right"),
            "strike": float(m.group("strike")),
        }

    return None


def _underlying_for(symbol: str, pos: Dict[str, Any]) -> str:
    """Return the underlying symbol for a position."""
    parsed = _parse_option_symbol(symbol)
    if parsed:
        return parsed["underlying"]
    return symbol


# ---------------------------------------------------------------------------
# Default target calculations
# ---------------------------------------------------------------------------

def _equity_targets(pos: Dict[str, Any]) -> Dict[str, Any]:
    """Return sensible default targets for a long/short equity position."""
    entry = pos.get("entry_price", 0)
    side = pos.get("side", "LONG")
    if entry <= 0:
        return {}

    if side == "LONG":
        return {
            "stop_loss_price": round(entry * 0.95, 2),
            "stop_loss_pct": 0.05,
            "profit_target_price": round(entry * 1.10, 2),
            "profit_target_pct": 0.10,
            "trailing_stop_pct": 0.05,
        }
    else:
        return {
            "stop_loss_price": round(entry * 1.05, 2),
            "stop_loss_pct": 0.05,
            "profit_target_price": round(entry * 0.90, 2),
            "profit_target_pct": 0.10,
            "trailing_stop_pct": 0.05,
        }


def _covered_call_targets(
    stock_pos: Dict[str, Any], call_pos: Dict[str, Any],
    call_strike: float,
) -> Dict[str, Any]:
    """Targets for a covered call (long stock + short call)."""
    entry = stock_pos.get("entry_price", 0)
    premium = abs(call_pos.get("entry_price", 0))
    if entry <= 0:
        return {}
    return {
        "profit_target_price": round(call_strike, 2),
        "profit_target_pct": round((call_strike - entry + premium) / entry, 4),
        "stop_loss_price": round(entry * 0.90, 2),
        "stop_loss_pct": 0.10,
        "max_profit": round((call_strike - entry + premium) * abs(stock_pos.get("quantity", 0)), 2),
    }


def _spread_targets(
    long_pos: Dict[str, Any], short_pos: Dict[str, Any],
    long_strike: float, short_strike: float,
    spread_type: str,
) -> Dict[str, Any]:
    """Targets for a vertical spread."""
    width = abs(long_strike - short_strike)
    long_entry = abs(long_pos.get("entry_price", 0))
    short_entry = abs(short_pos.get("entry_price", 0))

    if spread_type in ("BullCallSpread", "BearPutSpread"):
        # Debit spread
        net_debit = max(long_entry - short_entry, 0.01)
        max_profit = round(width - net_debit, 2)
        max_loss = round(net_debit, 2)
    else:
        # Credit spread
        net_credit = max(short_entry - long_entry, 0.01)
        max_profit = round(net_credit, 2)
        max_loss = round(width - net_credit, 2)

    qty = abs(long_pos.get("quantity", 1))
    return {
        "max_profit": round(max_profit * qty * 100, 2),
        "max_loss": round(max_loss * qty * 100, 2),
        "spread_width": round(width, 2),
        "profit_target_pct": 0.50,  # close at 50% of max profit
    }


# ---------------------------------------------------------------------------
# Main analyser
# ---------------------------------------------------------------------------

class PositionAnalyzer:
    """Analyse TWS positions and infer likely trading strategies."""

    def analyze(self, positions: Dict[str, Dict[str, Any]]) -> List[InferredStrategy]:
        """Examine *positions* (keyed by symbol) and return inferred strategies.

        Each position dict is expected to have at least:
            quantity, entry_price, current_price, market_value,
            unrealized_pnl, side, sec_type
        """
        if not positions:
            return []

        # Separate into stocks and options, group by underlying
        stocks: Dict[str, Tuple[str, Dict[str, Any]]] = {}   # underlying → (symbol, pos)
        options: Dict[str, List[Tuple[str, Dict[str, Any], Dict[str, Any]]]] = {}  # underlying → [(sym, pos, parsed)]

        for symbol, pos in positions.items():
            sec_type = pos.get("sec_type", "")
            underlying = _underlying_for(symbol, pos)

            if sec_type == "OPT":
                parsed = _parse_option_symbol(symbol)
                if parsed:
                    options.setdefault(underlying, []).append((symbol, pos, parsed))
                else:
                    # Can't parse option symbol — use conservative defaults
                    logger.warning("Could not parse option symbol: %s", symbol)
                    options.setdefault(underlying, []).append((symbol, pos, {
                        "underlying": underlying,
                        "right": "?",
                        "strike": abs(pos.get("entry_price", 0)),
                        "expiry": "",
                    }))
            else:
                stocks[underlying] = (symbol, pos)

        results: List[InferredStrategy] = []
        matched_symbols: set = set()
        counter = 0

        # --- Multi-leg option strategies (by underlying) ---
        for underlying, opt_legs in options.items():
            stock_sym, stock_pos = stocks.get(underlying, (None, None))

            detected = self._detect_multi_leg(
                underlying, stock_pos, stock_sym, opt_legs,
            )
            if detected:
                for d in detected:
                    counter += 1
                    d.id = f"inferred_{counter}"
                    results.append(d)
                    # Mark symbols as matched
                    for p in d.positions:
                        matched_symbols.add(p.get("symbol", ""))
                if stock_sym:
                    matched_symbols.add(stock_sym)

        # --- Unmatched stock positions → LongEquity / ShortEquity ---
        for underlying, (symbol, pos) in stocks.items():
            if symbol in matched_symbols:
                continue
            counter += 1
            side = pos.get("side", "LONG")
            stype = "LongEquity" if side == "LONG" else "ShortEquity"
            results.append(InferredStrategy(
                id=f"inferred_{counter}",
                strategy_type=stype,
                description=f"{side.title()} position in {underlying}",
                confidence=0.95,
                symbols=[underlying],
                positions=[{**pos, "symbol": symbol}],
                targets=_equity_targets(pos),
            ))

        # --- Unmatched naked options ---
        for underlying, opt_legs in options.items():
            for sym, pos, parsed in opt_legs:
                if sym in matched_symbols:
                    continue
                counter += 1
                side = pos.get("side", "LONG")
                right = parsed.get("right", "?")
                right_name = "Call" if right == "C" else "Put"
                stype = f"{'Long' if side == 'LONG' else 'Short'}{right_name}"
                results.append(InferredStrategy(
                    id=f"inferred_{counter}",
                    strategy_type=stype,
                    description=f"{side.title()} {right_name} on {underlying}",
                    confidence=0.85,
                    symbols=[underlying],
                    positions=[{**pos, "symbol": sym}],
                    targets={},
                ))

        return results

    # ------------------------------------------------------------------
    # Multi-leg detection
    # ------------------------------------------------------------------

    def _detect_multi_leg(
        self,
        underlying: str,
        stock_pos: Optional[Dict[str, Any]],
        stock_sym: Optional[str],
        opt_legs: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
    ) -> List[InferredStrategy]:
        """Try to match known multi-leg patterns."""
        results: List[InferredStrategy] = []
        used: set = set()

        # Classify legs
        long_calls = [(s, p, x) for s, p, x in opt_legs
                      if x.get("right") == "C" and p.get("side") == "LONG"]
        short_calls = [(s, p, x) for s, p, x in opt_legs
                       if x.get("right") == "C" and p.get("side") == "SHORT"]
        long_puts = [(s, p, x) for s, p, x in opt_legs
                     if x.get("right") == "P" and p.get("side") == "LONG"]
        short_puts = [(s, p, x) for s, p, x in opt_legs
                      if x.get("right") == "P" and p.get("side") == "SHORT"]

        # --- Iron Condor: short call + long call (higher) + short put + long put (lower) ---
        if short_calls and long_calls and short_puts and long_puts:
            sc = short_calls[0]
            lc = long_calls[0]
            sp = short_puts[0]
            lp = long_puts[0]
            if (lc[2]["strike"] > sc[2]["strike"] and
                    lp[2]["strike"] < sp[2]["strike"]):
                pos_list = [
                    {**sc[1], "symbol": sc[0]},
                    {**lc[1], "symbol": lc[0]},
                    {**sp[1], "symbol": sp[0]},
                    {**lp[1], "symbol": lp[0]},
                ]
                results.append(InferredStrategy(
                    strategy_type="IronCondor",
                    description=(
                        f"Iron Condor on {underlying}: "
                        f"sell {sc[2]['strike']}C/{sp[2]['strike']}P, "
                        f"buy {lc[2]['strike']}C/{lp[2]['strike']}P"
                    ),
                    confidence=0.90,
                    symbols=[underlying],
                    positions=pos_list,
                    targets={
                        "max_profit": "net credit received",
                        "profit_target_pct": 0.50,
                    },
                ))
                for leg in [sc, lc, sp, lp]:
                    used.add(leg[0])

        # --- Covered Call: long stock + short call ---
        if stock_pos and stock_pos.get("side") == "LONG":
            for sc in short_calls:
                if sc[0] in used:
                    continue
                stock_qty = abs(stock_pos.get("quantity", 0))
                opt_qty = abs(sc[1].get("quantity", 0)) * 100
                # Allow covered call when stock covers options
                # (stock_qty >= opt_qty) or roughly 1:1 ratio
                if opt_qty > 0 and stock_qty >= opt_qty * 0.67:
                    pos_list = [
                        {**stock_pos, "symbol": stock_sym},
                        {**sc[1], "symbol": sc[0]},
                    ]
                    results.append(InferredStrategy(
                        strategy_type="CoveredCall",
                        description=(
                            f"Covered Call on {underlying}: "
                            f"long stock + short {sc[2]['strike']} call"
                        ),
                        confidence=0.92,
                        symbols=[underlying],
                        positions=pos_list,
                        targets=_covered_call_targets(
                            stock_pos, sc[1], sc[2]["strike"],
                        ),
                    ))
                    used.add(sc[0])
                    break  # Only match one covered call per underlying

        # --- Protective Put: long stock + long put ---
        if stock_pos and stock_pos.get("side") == "LONG":
            for lp in long_puts:
                if lp[0] in used:
                    continue
                pos_list = [
                    {**stock_pos, "symbol": stock_sym},
                    {**lp[1], "symbol": lp[0]},
                ]
                entry = stock_pos.get("entry_price", 0)
                results.append(InferredStrategy(
                    strategy_type="ProtectivePut",
                    description=(
                        f"Protective Put on {underlying}: "
                        f"long stock + long {lp[2]['strike']} put"
                    ),
                    confidence=0.90,
                    symbols=[underlying],
                    positions=pos_list,
                    targets={
                        "stop_loss_price": lp[2]["strike"],
                        "profit_target_pct": 0.10,
                        "max_loss": round(
                            (entry - lp[2]["strike"]) * abs(stock_pos.get("quantity", 0)), 2
                        ) if entry > 0 else 0,
                    },
                ))
                used.add(lp[0])
                break

        # --- Bull Call Spread: long call (lower) + short call (higher) ---
        for lc in long_calls:
            if lc[0] in used:
                continue
            for sc in short_calls:
                if sc[0] in used:
                    continue
                if sc[2]["strike"] > lc[2]["strike"] and sc[2].get("expiry") == lc[2].get("expiry"):
                    pos_list = [
                        {**lc[1], "symbol": lc[0]},
                        {**sc[1], "symbol": sc[0]},
                    ]
                    results.append(InferredStrategy(
                        strategy_type="BullCallSpread",
                        description=(
                            f"Bull Call Spread on {underlying}: "
                            f"buy {lc[2]['strike']}C / sell {sc[2]['strike']}C"
                        ),
                        confidence=0.90,
                        symbols=[underlying],
                        positions=pos_list,
                        targets=_spread_targets(
                            lc[1], sc[1], lc[2]["strike"], sc[2]["strike"],
                            "BullCallSpread",
                        ),
                    ))
                    used.add(lc[0])
                    used.add(sc[0])
                    break

        # --- Bear Put Spread: long put (higher) + short put (lower) ---
        for lp in long_puts:
            if lp[0] in used:
                continue
            for sp in short_puts:
                if sp[0] in used:
                    continue
                if lp[2]["strike"] > sp[2]["strike"] and sp[2].get("expiry") == lp[2].get("expiry"):
                    pos_list = [
                        {**lp[1], "symbol": lp[0]},
                        {**sp[1], "symbol": sp[0]},
                    ]
                    results.append(InferredStrategy(
                        strategy_type="BearPutSpread",
                        description=(
                            f"Bear Put Spread on {underlying}: "
                            f"buy {lp[2]['strike']}P / sell {sp[2]['strike']}P"
                        ),
                        confidence=0.90,
                        symbols=[underlying],
                        positions=pos_list,
                        targets=_spread_targets(
                            lp[1], sp[1], lp[2]["strike"], sp[2]["strike"],
                            "BearPutSpread",
                        ),
                    ))
                    used.add(lp[0])
                    used.add(sp[0])
                    break

        # --- Bull Put Spread (credit): short put (higher) + long put (lower) ---
        for sp in short_puts:
            if sp[0] in used:
                continue
            for lp in long_puts:
                if lp[0] in used:
                    continue
                if sp[2]["strike"] > lp[2]["strike"] and sp[2].get("expiry") == lp[2].get("expiry"):
                    pos_list = [
                        {**sp[1], "symbol": sp[0]},
                        {**lp[1], "symbol": lp[0]},
                    ]
                    results.append(InferredStrategy(
                        strategy_type="BullPutSpread",
                        description=(
                            f"Bull Put Spread on {underlying}: "
                            f"sell {sp[2]['strike']}P / buy {lp[2]['strike']}P"
                        ),
                        confidence=0.90,
                        symbols=[underlying],
                        positions=pos_list,
                        targets=_spread_targets(
                            lp[1], sp[1], lp[2]["strike"], sp[2]["strike"],
                            "BullPutSpread",
                        ),
                    ))
                    used.add(sp[0])
                    used.add(lp[0])
                    break

        # --- Straddle: long call + long put same strike/expiry ---
        for lc in long_calls:
            if lc[0] in used:
                continue
            for lp in long_puts:
                if lp[0] in used:
                    continue
                if (lc[2]["strike"] == lp[2]["strike"] and
                        lc[2].get("expiry") == lp[2].get("expiry")):
                    pos_list = [
                        {**lc[1], "symbol": lc[0]},
                        {**lp[1], "symbol": lp[0]},
                    ]
                    results.append(InferredStrategy(
                        strategy_type="Straddle",
                        description=(
                            f"Straddle on {underlying} at {lc[2]['strike']} strike"
                        ),
                        confidence=0.92,
                        symbols=[underlying],
                        positions=pos_list,
                        targets={
                            "profit_target_pct": 0.20,
                        },
                    ))
                    used.add(lc[0])
                    used.add(lp[0])
                    break

        # --- Strangle: long call + long put different strikes/same expiry ---
        for lc in long_calls:
            if lc[0] in used:
                continue
            for lp in long_puts:
                if lp[0] in used:
                    continue
                if (lc[2]["strike"] != lp[2]["strike"] and
                        lc[2].get("expiry") == lp[2].get("expiry")):
                    pos_list = [
                        {**lc[1], "symbol": lc[0]},
                        {**lp[1], "symbol": lp[0]},
                    ]
                    results.append(InferredStrategy(
                        strategy_type="Strangle",
                        description=(
                            f"Strangle on {underlying}: "
                            f"{lc[2]['strike']}C / {lp[2]['strike']}P"
                        ),
                        confidence=0.88,
                        symbols=[underlying],
                        positions=pos_list,
                        targets={
                            "profit_target_pct": 0.20,
                        },
                    ))
                    used.add(lc[0])
                    used.add(lp[0])
                    break

        return results
