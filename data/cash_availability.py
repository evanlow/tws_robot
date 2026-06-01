"""Cash Availability Analyzer.

Implements deployable-cash estimation by examining live positions, pending
orders, and broker account data to distinguish between:

  - Total cash balance (from broker)
  - Broker-reported buying power / available funds
  - Capital reserved for open obligations (short puts, spreads, etc.)
  - Truly deployable cash available for new opportunities

Configuration is driven by environment variables (or explicit overrides):

  CASH_RESERVE_MODE            gross_assignment | net_premium | broker_margin
  MANUAL_CASH_BUFFER_PCT       fractional e.g. 0.10 for 10%
  MANUAL_CASH_BUFFER_AMOUNT    fixed dollar amount (larger of pct/fixed buffer)
  OPTION_CONTRACT_MULTIPLIER_DEFAULT  100 by default

This module is deliberately **not** connected to a broker: it consumes data
already ingested by the ServiceManager / TWSBridge and produces a structured
``CashAvailabilityResult`` that the API endpoint can serialise to JSON.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class CashReserveMode(str, Enum):
    """How to calculate the cash reserve required per short put position."""
    GROSS_ASSIGNMENT = "gross_assignment"
    NET_PREMIUM = "net_premium"
    BROKER_MARGIN = "broker_margin"


@dataclass
class CashAvailabilityConfig:
    """Runtime configuration for the cash availability analyser.

    All fields have sensible defaults and can be overridden via env vars or
    direct construction.
    """
    reserve_mode: CashReserveMode = CashReserveMode.GROSS_ASSIGNMENT
    manual_cash_buffer_pct: float = 0.10        # 10% of cash balance by default
    manual_cash_buffer_amount: float = 0.0       # fixed dollar buffer
    option_contract_multiplier: int = 100        # shares per contract

    @classmethod
    def from_env(cls) -> "CashAvailabilityConfig":
        """Build config from environment variables."""
        mode_str = os.environ.get(
            "CASH_RESERVE_MODE", "gross_assignment"
        ).lower()
        try:
            mode = CashReserveMode(mode_str)
        except ValueError:
            logger.warning(
                "Unknown CASH_RESERVE_MODE=%r; falling back to gross_assignment",
                mode_str,
            )
            mode = CashReserveMode.GROSS_ASSIGNMENT

        return cls(
            reserve_mode=mode,
            manual_cash_buffer_pct=float(
                os.environ.get("MANUAL_CASH_BUFFER_PCT", "0.10")
            ),
            manual_cash_buffer_amount=float(
                os.environ.get("MANUAL_CASH_BUFFER_AMOUNT", "0")
            ),
            option_contract_multiplier=int(
                os.environ.get("OPTION_CONTRACT_MULTIPLIER_DEFAULT", "100")
            ),
        )


# ---------------------------------------------------------------------------
# Option symbol parsing  (reuse the same regex as position_analyzer.py)
# ---------------------------------------------------------------------------

_OCC_RE = re.compile(
    r"^(?P<underlying>[A-Z0-9]+)"
    r"(?P<date>\d{6})"
    r"(?P<right>[CP])"
    r"(?P<strike>\d{8})$"
)
_COMPACT_RE = re.compile(
    r"^(?P<underlying>[A-Z0-9]+)"
    r"(?P<date>\d{6})"
    r"(?P<right>[CP])"
    r"(?P<strike>[\d.]+)$"
)


def _parse_option_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Parse an OCC-style option symbol into its components.

    Returns a dict with keys ``underlying``, ``expiry``, ``right``, ``strike``
    or ``None`` when the symbol does not look like an option.
    """
    clean = symbol.replace(" ", "")

    m = _OCC_RE.match(clean)
    if m:
        return {
            "underlying": m.group("underlying"),
            "expiry": m.group("date"),
            "right": m.group("right"),
            "strike": float(m.group("strike")) / 1000.0,
        }

    m2 = _COMPACT_RE.match(clean)
    if m2:
        return {
            "underlying": m2.group("underlying"),
            "expiry": m2.group("date"),
            "right": m2.group("right"),
            "strike": float(m2.group("strike")),
        }

    return None


# ---------------------------------------------------------------------------
# Per-position reserve data structures
# ---------------------------------------------------------------------------

@dataclass
class PositionReserve:
    """Capital reservation record for a single position or spread."""

    symbol: str
    underlying: str
    position_type: str          # e.g. "cash_secured_short_put", "defined_risk_spread"
    expiry: str = ""
    strike: float = 0.0
    contracts: int = 0
    multiplier: int = 100
    gross_assignment_obligation: float = 0.0
    reserve_amount: float = 0.0
    premium_collected: float = 0.0
    current_liability: float = 0.0
    defined_risk_protected: bool = False
    spread_width: float = 0.0
    warning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "type": self.position_type,
            "expiry": self.expiry,
            "strike": round(self.strike, 4),
            "contracts": self.contracts,
            "multiplier": self.multiplier,
            "gross_assignment_obligation": round(self.gross_assignment_obligation, 2),
            "reserve_amount": round(self.reserve_amount, 2),
            "premium_collected": round(self.premium_collected, 2),
            "current_liability": round(self.current_liability, 2),
            "defined_risk_protected": self.defined_risk_protected,
            "spread_width": round(self.spread_width, 2),
            "warning": self.warning,
        }


# ---------------------------------------------------------------------------
# Main result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CashAvailabilityResult:
    """Full output of a cash-availability analysis pass."""

    # Broker-reported fields
    cash_balance: float = 0.0
    broker_buying_power: float = 0.0
    broker_available_funds: float = 0.0
    broker_excess_liquidity: float = 0.0
    broker_initial_margin_req: float = 0.0
    broker_maintenance_margin_req: float = 0.0

    # Reserve breakdown
    reserved_cash_short_puts: float = 0.0
    reserved_cash_defined_risk_spreads: float = 0.0
    reserved_for_pending_orders: float = 0.0
    manual_cash_buffer: float = 0.0
    margin_safety_buffer: float = 0.0

    # Result
    reserved_cash_total: float = 0.0
    deployable_cash: float = 0.0
    reserve_coverage_ratio: Optional[float] = None

    # Flags
    uncovered_short_call_risk: bool = False
    has_short_stock: bool = False
    high_margin_usage: bool = False
    multi_currency_mismatch: bool = False

    # Per-position detail
    position_reserves: List[PositionReserve] = field(default_factory=list)

    # Per-currency cash balances (populated when broker provides them)
    cash_by_currency: Dict[str, float] = field(default_factory=dict)

    # Committed shares (from covered calls)
    committed_shares: Dict[str, int] = field(default_factory=dict)

    # Human-readable warnings
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cash_balance": round(self.cash_balance, 2),
            "broker_buying_power": round(self.broker_buying_power, 2),
            "broker_available_funds": round(self.broker_available_funds, 2),
            "broker_excess_liquidity": round(self.broker_excess_liquidity, 2),
            "broker_initial_margin_req": round(self.broker_initial_margin_req, 2),
            "broker_maintenance_margin_req": round(self.broker_maintenance_margin_req, 2),
            "reserved_cash_total": round(self.reserved_cash_total, 2),
            "reserved_cash_short_puts": round(self.reserved_cash_short_puts, 2),
            "reserved_cash_defined_risk_spreads": round(
                self.reserved_cash_defined_risk_spreads, 2
            ),
            "reserved_for_pending_orders": round(self.reserved_for_pending_orders, 2),
            "manual_cash_buffer": round(self.manual_cash_buffer, 2),
            "margin_safety_buffer": round(self.margin_safety_buffer, 2),
            "deployable_cash": round(self.deployable_cash, 2),
            "reserve_coverage_ratio": (
                round(self.reserve_coverage_ratio, 4)
                if self.reserve_coverage_ratio is not None
                else None
            ),
            "uncovered_short_call_risk": self.uncovered_short_call_risk,
            "has_short_stock": self.has_short_stock,
            "high_margin_usage": self.high_margin_usage,
            "multi_currency_mismatch": self.multi_currency_mismatch,
            "cash_by_currency": {
                k: round(v, 2) for k, v in self.cash_by_currency.items()
            },
            "committed_shares": dict(self.committed_shares),
            "position_reserves": [pr.to_dict() for pr in self.position_reserves],
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Main analyser
# ---------------------------------------------------------------------------

class CashAvailabilityAnalyzer:
    """Compute deployable cash from live positions, orders, and broker data.

    Typical usage::

        analyzer = CashAvailabilityAnalyzer()
        result = analyzer.analyze(
            account_summary=svc.get_account_summary(),
            positions=svc.get_positions(),
            orders=svc.get_orders(),
        )
        return jsonify(result.to_dict())
    """

    def __init__(self, config: Optional[CashAvailabilityConfig] = None) -> None:
        self.config = config or CashAvailabilityConfig.from_env()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        account_summary: Dict[str, Any],
        positions: Dict[str, Dict[str, Any]],
        orders: Optional[List[Dict[str, Any]]] = None,
    ) -> CashAvailabilityResult:
        """Run a full cash-availability analysis.

        Parameters
        ----------
        account_summary:
            Dict as returned by ``ServiceManager.get_account_summary()``.
            Expected keys include ``cash_balance``, ``buying_power``,
            ``available_funds``, ``excess_liquidity``, ``init_margin_req``,
            ``maint_margin_req``, and optionally ``cash_by_currency``.
        positions:
            Dict keyed by symbol (as returned by
            ``ServiceManager.get_positions()``).  Each value dict should
            contain at least ``quantity``, ``entry_price``, ``market_value``,
            ``side``, ``sec_type``.
        orders:
            Optional list of pending orders (as stored by
            ``ServiceManager._orders``).  Used to reserve capital for open
            buy orders.
        """
        orders = orders or []
        result = CashAvailabilityResult()

        # -- Broker fields --------------------------------------------------
        result.cash_balance = account_summary.get("cash_balance", 0.0)
        result.broker_buying_power = account_summary.get("buying_power", 0.0)
        result.broker_available_funds = account_summary.get(
            "available_funds", 0.0
        )
        result.broker_excess_liquidity = account_summary.get(
            "excess_liquidity", 0.0
        )
        result.broker_initial_margin_req = account_summary.get(
            "init_margin_req", 0.0
        )
        result.broker_maintenance_margin_req = account_summary.get(
            "maint_margin_req", 0.0
        )
        result.cash_by_currency = dict(
            account_summary.get("cash_by_currency", {})
        )

        # -- Multi-currency warning -----------------------------------------
        non_usd = {
            k: v
            for k, v in result.cash_by_currency.items()
            if k not in ("USD", "BASE") and abs(v) > 0.01
        }
        if non_usd:
            result.multi_currency_mismatch = True
            currencies = ", ".join(sorted(non_usd.keys()))
            result.warnings.append(
                f"Non-USD cash balances detected ({currencies}). "
                "Cross-currency deployable cash may not be immediately available "
                "for USD trades without FX conversion."
            )

        # -- Analyse positions ----------------------------------------------
        self._analyze_positions(positions, result)

        # -- Pending orders -------------------------------------------------
        result.reserved_for_pending_orders = self._reserve_for_orders(
            orders, result.warnings
        )

        # -- Manual buffer --------------------------------------------------
        buf_pct = result.cash_balance * self.config.manual_cash_buffer_pct
        buf_fixed = self.config.manual_cash_buffer_amount
        result.manual_cash_buffer = max(buf_pct, buf_fixed)

        # -- Margin safety buffer -------------------------------------------
        # If broker reports excess liquidity and it is very tight (< 10% of
        # cash balance) add a conservative safety margin buffer.
        result.margin_safety_buffer = self._compute_margin_safety_buffer(result)

        # -- Aggregate reserves --------------------------------------------
        result.reserved_cash_total = (
            result.reserved_cash_short_puts
            + result.reserved_cash_defined_risk_spreads
            + result.reserved_for_pending_orders
            + result.manual_cash_buffer
            + result.margin_safety_buffer
        )

        # -- Deployable cash -----------------------------------------------
        result.deployable_cash = max(
            0.0,
            result.cash_balance - result.reserved_cash_total,
        )

        # -- Reserve coverage ratio ----------------------------------------
        if result.reserved_cash_total > 0:
            result.reserve_coverage_ratio = (
                result.cash_balance / result.reserved_cash_total
            )
        elif result.cash_balance > 0:
            # No reserves and positive cash: ratio is undefined (null in JSON)
            result.reserve_coverage_ratio = None
        else:
            result.reserve_coverage_ratio = 0.0

        # -- Top-level warnings --------------------------------------------
        if result.deployable_cash <= 0:
            result.warnings.append(
                "Estimated deployable cash is zero or negative. "
                "No new positions recommended until reserves are reduced."
            )
        elif result.cash_balance < result.reserved_cash_total:
            result.warnings.append(
                "Cash balance is less than total reserved capital. "
                "Short-put obligations may exceed available cash."
            )

        if result.uncovered_short_call_risk:
            result.warnings.append(
                "Uncovered (naked) short call detected. "
                "This position has theoretically unlimited risk. "
                "Automated opportunity recommendations are restricted."
            )

        if result.high_margin_usage:
            result.warnings.append(
                "High margin usage detected. "
                "Deployable cash may be further constrained by broker margin rules."
            )

        return result

    # ------------------------------------------------------------------
    # Position analysis
    # ------------------------------------------------------------------

    def _analyze_positions(
        self,
        positions: Dict[str, Dict[str, Any]],
        result: CashAvailabilityResult,
    ) -> None:
        """Classify all positions and compute their cash reserves.

        Groups options by underlying so that spread detection works across
        the full option book for each underlying.
        """
        multiplier = self.config.option_contract_multiplier

        # Separate stock and option positions by underlying
        stocks: Dict[str, Dict[str, Any]] = {}     # underlying → pos
        short_puts: Dict[str, List[Dict[str, Any]]] = {}   # underlying → [pos_info]
        long_puts: Dict[str, List[Dict[str, Any]]] = {}
        short_calls: Dict[str, List[Dict[str, Any]]] = {}
        long_calls: Dict[str, List[Dict[str, Any]]] = {}
        short_stock: List[Dict[str, Any]] = []

        for symbol, pos in positions.items():
            sec_type = pos.get("sec_type", "")
            side = pos.get("side", "LONG")
            qty = pos.get("quantity", 0)

            if sec_type == "OPT":
                parsed = _parse_option_symbol(symbol)
                info: Dict[str, Any] = {
                    "symbol": symbol,
                    "pos": pos,
                    "parsed": parsed,
                    "multiplier": multiplier,
                }
                if parsed is None:
                    info["warning"] = (
                        f"Could not parse option symbol {symbol!r}; "
                        "excluding from automated reserve calculations."
                    )
                    result.warnings.append(info["warning"])
                    # Still emit a conservative reserve entry with no value
                    result.position_reserves.append(PositionReserve(
                        symbol=symbol,
                        underlying=symbol,
                        position_type="unparseable_option",
                        warning=info["warning"],
                    ))
                    continue

                und = parsed["underlying"]
                right = parsed["right"]

                if side == "SHORT":
                    if right == "P":
                        short_puts.setdefault(und, []).append(info)
                    elif right == "C":
                        short_calls.setdefault(und, []).append(info)
                else:  # LONG
                    if right == "P":
                        long_puts.setdefault(und, []).append(info)
                    elif right == "C":
                        long_calls.setdefault(und, []).append(info)

            elif sec_type in ("STK", ""):
                if side == "SHORT":
                    short_stock.append({"symbol": symbol, "pos": pos})
                else:
                    # Long stock — record for covered-call matching
                    stocks[symbol] = pos

            else:
                # Futures, warrants, etc. — not handled; skip silently
                pass

        # --- Short stock (margin / risk warning) -------------------------
        for ss in short_stock:
            sym = ss["symbol"]
            pos = ss["pos"]
            mv = abs(pos.get("market_value", 0.0))
            result.warnings.append(
                f"Short stock position in {sym} detected "
                f"(market value ${mv:,.0f}). "
                "Short stock requires margin and creates buy-to-cover obligations. "
                "Deployable cash may be further reduced by broker margin rules."
            )
            result.has_short_stock = True
            result.high_margin_usage = True

        # --- Bear call spread matching ------------------------------------
        # For each underlying with short calls, first try to match them with
        # a higher-strike long call (same underlying/expiry, sufficient qty).
        # Matched pairs are bear call spreads (defined-risk).
        # Unmatched short calls go on to covered-call / naked-call processing.
        #
        # Structure: {(und, expiry): [spread_record, ...]}
        bear_call_spread_records: Dict[tuple, List[Dict[str, Any]]] = {}
        # Short calls not protected by a long call
        remaining_short_calls: Dict[str, List[Dict[str, Any]]] = {}

        for und, scall_list in short_calls.items():
            lcall_list = long_calls.get(und, [])
            # Sort short calls ascending by strike so we match lowest first
            sc_sorted = sorted(
                scall_list,
                key=lambda x: x["parsed"]["strike"],
            )
            # Sort long calls descending by strike (highest strike first)
            lc_sorted = sorted(
                lcall_list,
                key=lambda x: x["parsed"]["strike"],
                reverse=True,
            )
            used_long_calls: set = set()

            for sc in sc_sorted:
                sym = sc["symbol"]
                parsed = sc["parsed"]
                pos = sc["pos"]
                short_strike = parsed["strike"]
                short_expiry = parsed.get("expiry", "")
                contracts = int(abs(pos.get("quantity", 0)))

                # Find a higher-strike long call in same expiry with enough qty
                matched_lc = None
                for lc in lc_sorted:
                    if lc["symbol"] in used_long_calls:
                        continue
                    lc_parsed = lc["parsed"]
                    lc_qty = int(abs(lc["pos"].get("quantity", 0)))
                    if (
                        lc_parsed["strike"] > short_strike
                        and lc_parsed.get("expiry") == short_expiry
                        and lc_qty >= contracts
                    ):
                        matched_lc = lc
                        break

                if matched_lc is not None:
                    used_long_calls.add(matched_lc["symbol"])
                    spread_width = matched_lc["parsed"]["strike"] - short_strike
                    reserve = contracts * multiplier * spread_width
                    key = (und, short_expiry)
                    bear_call_spread_records.setdefault(key, []).append({
                        "sym": sym,
                        "parsed": parsed,
                        "pos": pos,
                        "contracts": contracts,
                        "short_strike": short_strike,
                        "spread_width": spread_width,
                        "reserve": reserve,
                        "used_in_iron_condor": False,
                    })
                else:
                    remaining_short_calls.setdefault(und, []).append(sc)

        # --- Covered-call matching (with partial coverage support) --------
        # Only consider short calls not already matched as bear call spreads.
        for und, scall_list in remaining_short_calls.items():
            stock_pos = stocks.get(und)
            stock_qty = int(abs(stock_pos.get("quantity", 0))) if stock_pos else 0

            for sc in scall_list:
                sym = sc["symbol"]
                parsed = sc["parsed"]
                pos = sc["pos"]
                contracts = int(abs(pos.get("quantity", 0)))
                shares_needed = contracts * multiplier
                entry_price = abs(pos.get("entry_price", 0.0))
                prem_total = contracts * multiplier * entry_price
                current_liability = abs(pos.get("market_value", 0.0))

                if stock_qty >= shares_needed:
                    # Fully covered — mark shares as committed; no cash reserve
                    result.committed_shares[und] = (
                        result.committed_shares.get(und, 0) + shares_needed
                    )
                    stock_qty -= shares_needed
                    result.position_reserves.append(PositionReserve(
                        symbol=sym,
                        underlying=und,
                        position_type="covered_short_call",
                        expiry=parsed.get("expiry", ""),
                        strike=parsed.get("strike", 0.0),
                        contracts=contracts,
                        multiplier=multiplier,
                        reserve_amount=0.0,
                        premium_collected=prem_total,
                        current_liability=current_liability,
                        defined_risk_protected=True,
                    ))
                elif stock_qty > 0:
                    # Partially covered — split into covered and uncovered legs
                    covered_contracts = stock_qty // multiplier
                    uncovered_contracts = contracts - covered_contracts
                    covered_shares = covered_contracts * multiplier

                    result.committed_shares[und] = (
                        result.committed_shares.get(und, 0) + covered_shares
                    )
                    stock_qty = 0

                    if covered_contracts > 0:
                        result.position_reserves.append(PositionReserve(
                            symbol=sym,
                            underlying=und,
                            position_type="covered_short_call",
                            expiry=parsed.get("expiry", ""),
                            strike=parsed.get("strike", 0.0),
                            contracts=covered_contracts,
                            multiplier=multiplier,
                            reserve_amount=0.0,
                            premium_collected=covered_contracts * multiplier * entry_price,
                            current_liability=(
                                current_liability * covered_contracts / contracts
                            ),
                            defined_risk_protected=True,
                        ))

                    result.uncovered_short_call_risk = True
                    result.position_reserves.append(PositionReserve(
                        symbol=sym,
                        underlying=und,
                        position_type="uncovered_short_call",
                        expiry=parsed.get("expiry", ""),
                        strike=parsed.get("strike", 0.0),
                        contracts=uncovered_contracts,
                        multiplier=multiplier,
                        reserve_amount=0.0,
                        premium_collected=uncovered_contracts * multiplier * entry_price,
                        current_liability=(
                            current_liability * uncovered_contracts / contracts
                        ),
                        warning=(
                            f"Partially uncovered short call {sym}: "
                            f"{uncovered_contracts} of {contracts} contracts "
                            "lack stock coverage."
                        ),
                    ))
                else:
                    # Fully uncovered (naked) short call
                    result.uncovered_short_call_risk = True
                    result.position_reserves.append(PositionReserve(
                        symbol=sym,
                        underlying=und,
                        position_type="uncovered_short_call",
                        expiry=parsed.get("expiry", ""),
                        strike=parsed.get("strike", 0.0),
                        contracts=contracts,
                        multiplier=multiplier,
                        reserve_amount=0.0,
                        premium_collected=prem_total,
                        current_liability=current_liability,
                        warning=(
                            f"Uncovered short call {sym}: "
                            "margin requirement governed by broker rules."
                        ),
                    ))

        # --- Short put spread detection + iron condor detection ----------
        # After matching bull put spreads, check each spread for a paired
        # bear call spread on the same underlying/expiry.  When one is found
        # the position is an iron condor; reserve = max spread width only.
        total_short_put_reserve = 0.0
        total_spread_reserve = 0.0

        for und, sp_list in short_puts.items():
            lp_list = long_puts.get(und, [])

            # Sort short puts descending by strike, long puts ascending
            sp_sorted = sorted(
                sp_list,
                key=lambda x: x["parsed"]["strike"] if x["parsed"] else 0,
                reverse=True,
            )
            lp_sorted = sorted(
                lp_list,
                key=lambda x: x["parsed"]["strike"] if x["parsed"] else 0,
            )

            used_long_puts: set = set()

            for sp in sp_sorted:
                sym = sp["symbol"]
                parsed = sp["parsed"]
                pos = sp["pos"]
                short_strike = parsed["strike"]
                short_expiry = parsed.get("expiry", "")
                contracts = int(abs(pos.get("quantity", 0)))
                prem_per_share = abs(pos.get("entry_price", 0.0))
                premium_collected = contracts * multiplier * prem_per_share
                current_liability = abs(pos.get("market_value", 0.0))
                gross_obligation = contracts * multiplier * short_strike

                # Try to match with a protective long put
                matched_lp = None
                for lp in lp_sorted:
                    if lp["symbol"] in used_long_puts:
                        continue
                    lp_parsed = lp["parsed"]
                    lp_qty = int(abs(lp["pos"].get("quantity", 0)))
                    if (
                        lp_parsed["strike"] < short_strike
                        and lp_parsed.get("expiry") == short_expiry
                        and lp_qty >= contracts
                    ):
                        matched_lp = lp
                        break

                if matched_lp is not None:
                    # Bull put spread — check for iron condor pairing
                    used_long_puts.add(matched_lp["symbol"])
                    put_spread_width = short_strike - matched_lp["parsed"]["strike"]

                    ic_key = (und, short_expiry)
                    bc_records = bear_call_spread_records.get(ic_key, [])
                    matched_bc = None
                    for bc_rec in bc_records:
                        if (
                            not bc_rec.get("used_in_iron_condor")
                            and bc_rec["contracts"] == contracts
                            and bc_rec["short_strike"] > short_strike
                        ):
                            matched_bc = bc_rec
                            break

                    if matched_bc is not None:
                        # Iron condor — reserve max loss of the wider spread
                        matched_bc["used_in_iron_condor"] = True
                        ic_spread_width = max(
                            put_spread_width, matched_bc["spread_width"]
                        )
                        ic_reserve = contracts * multiplier * ic_spread_width
                        total_spread_reserve += ic_reserve
                        result.position_reserves.append(PositionReserve(
                            symbol=sym,
                            underlying=und,
                            position_type="iron_condor",
                            expiry=short_expiry,
                            strike=short_strike,
                            contracts=contracts,
                            multiplier=multiplier,
                            gross_assignment_obligation=gross_obligation,
                            reserve_amount=ic_reserve,
                            premium_collected=premium_collected,
                            current_liability=current_liability,
                            defined_risk_protected=True,
                            spread_width=ic_spread_width,
                        ))
                    else:
                        # Standalone bull put spread
                        put_reserve = contracts * multiplier * put_spread_width
                        total_spread_reserve += put_reserve
                        result.position_reserves.append(PositionReserve(
                            symbol=sym,
                            underlying=und,
                            position_type="defined_risk_put_spread",
                            expiry=short_expiry,
                            strike=short_strike,
                            contracts=contracts,
                            multiplier=multiplier,
                            gross_assignment_obligation=gross_obligation,
                            reserve_amount=put_reserve,
                            premium_collected=premium_collected,
                            current_liability=current_liability,
                            defined_risk_protected=True,
                            spread_width=put_spread_width,
                        ))
                else:
                    # Naked (cash-secured) short put
                    if (
                        self.config.reserve_mode
                        == CashReserveMode.GROSS_ASSIGNMENT
                    ):
                        reserve = gross_obligation
                    elif (
                        self.config.reserve_mode == CashReserveMode.NET_PREMIUM
                    ):
                        reserve = max(0.0, gross_obligation - premium_collected)
                    else:
                        # BROKER_MARGIN: fall back to gross for safety
                        reserve = gross_obligation

                    total_short_put_reserve += reserve
                    result.position_reserves.append(PositionReserve(
                        symbol=sym,
                        underlying=und,
                        position_type="cash_secured_short_put",
                        expiry=short_expiry,
                        strike=short_strike,
                        contracts=contracts,
                        multiplier=multiplier,
                        gross_assignment_obligation=gross_obligation,
                        reserve_amount=reserve,
                        premium_collected=premium_collected,
                        current_liability=current_liability,
                        defined_risk_protected=False,
                    ))

        # --- Standalone bear call spread reserves -------------------------
        # Any bear call spread not consumed by an iron condor is its own
        # defined-risk position.
        for (und, expiry), bc_records in bear_call_spread_records.items():
            for bc_rec in bc_records:
                if bc_rec.get("used_in_iron_condor"):
                    continue
                parsed = bc_rec["parsed"]
                pos = bc_rec["pos"]
                contracts = bc_rec["contracts"]
                spread_width = bc_rec["spread_width"]
                reserve = bc_rec["reserve"]
                prem = contracts * multiplier * abs(pos.get("entry_price", 0.0))
                current_liability = abs(pos.get("market_value", 0.0))
                gross_obligation = contracts * multiplier * parsed.get("strike", 0.0)

                total_spread_reserve += reserve
                result.position_reserves.append(PositionReserve(
                    symbol=bc_rec["sym"],
                    underlying=und,
                    position_type="defined_risk_call_spread",
                    expiry=expiry,
                    strike=parsed.get("strike", 0.0),
                    contracts=contracts,
                    multiplier=multiplier,
                    gross_assignment_obligation=gross_obligation,
                    reserve_amount=reserve,
                    premium_collected=prem,
                    current_liability=current_liability,
                    defined_risk_protected=True,
                    spread_width=spread_width,
                ))

        result.reserved_cash_short_puts = total_short_put_reserve
        result.reserved_cash_defined_risk_spreads = total_spread_reserve

        # --- High margin usage check -------------------------------------
        init_margin = result.broker_initial_margin_req
        if init_margin > 0 and result.cash_balance > 0:
            margin_utilisation = init_margin / result.cash_balance
            if margin_utilisation > 0.80:
                result.high_margin_usage = True

    # ------------------------------------------------------------------
    # Order reserve calculation
    # ------------------------------------------------------------------

    def _reserve_for_orders(
        self,
        orders: List[Dict[str, Any]],
        warnings: List[str],
    ) -> float:
        """Estimate capital reserved for pending (open) orders.

        Buy orders reserve ``limit_price × quantity`` (× multiplier for options).
        Pending short-put orders also reserve capital: gross assignment obligation
        by default, or spread max loss when paired with a pending protective long put
        in the same order list.

        Only unexecuted orders in PENDING / RECORDED / OPEN / SUBMITTED status are
        included.  Terminal statuses (FILLED, CANCELLED, REJECTED) are ignored.
        """
        _ACTIVE_STATUSES = {"PENDING", "RECORDED", "OPEN", "SUBMITTED"}
        _BUY_ACTIONS = {"BUY", "BTO", "LONG"}
        _SELL_ACTIONS = {"SELL", "STO", "SHORT"}
        multiplier = self.config.option_contract_multiplier

        # First pass: collect active pending long-put orders for spread matching
        pending_long_puts: List[Dict[str, Any]] = []
        for order in orders:
            status = (order.get("status") or "").upper()
            if status and status not in _ACTIVE_STATUSES:
                continue
            action = (order.get("action") or order.get("side") or "").upper()
            if action not in _BUY_ACTIONS:
                continue
            symbol = (order.get("symbol") or "").replace(" ", "").upper()
            qty = abs(float(order.get("quantity", 0) or 0))
            parsed = _parse_option_symbol(symbol)
            if parsed and parsed["right"] == "P":
                pending_long_puts.append({
                    "underlying": parsed["underlying"],
                    "expiry": parsed["expiry"],
                    "strike": parsed["strike"],
                    "contracts": int(qty),
                    "used": False,
                })

        total = 0.0
        for order in orders:
            status = (order.get("status") or "").upper()
            if status and status not in _ACTIVE_STATUSES:
                continue

            action = (order.get("action") or order.get("side") or "").upper()
            sec_type = (order.get("sec_type") or "").upper()
            symbol = (order.get("symbol") or "").replace(" ", "").upper()
            qty = abs(float(order.get("quantity", 0) or 0))
            limit_price = float(order.get("limit_price", 0) or 0)

            if action in _BUY_ACTIONS:
                if sec_type in ("OPT", "OPTION"):
                    reserve = qty * limit_price * multiplier
                elif sec_type in ("STK", "STOCK"):
                    reserve = qty * limit_price
                else:
                    # No sec_type — try symbol parsing to detect options
                    parsed_buy = _parse_option_symbol(symbol)
                    if parsed_buy is not None:
                        reserve = qty * limit_price * multiplier
                    else:
                        reserve = qty * limit_price
                if reserve > 0:
                    total += reserve

            elif action in _SELL_ACTIONS:
                # Pending short-put orders must reserve assignment capital.
                # Try to identify the order as a put option via symbol parsing
                # (sec_type field is often absent from locally-recorded orders).
                parsed = _parse_option_symbol(symbol)
                if parsed and parsed["right"] == "P":
                    contracts = int(qty)
                    short_strike = parsed["strike"]
                    short_expiry = parsed["expiry"]
                    und = parsed["underlying"]
                    gross_obligation = contracts * multiplier * short_strike

                    # Check for a paired pending long put (spread protection)
                    matched_lp = None
                    for lp in pending_long_puts:
                        if (
                            not lp["used"]
                            and lp["underlying"] == und
                            and lp["expiry"] == short_expiry
                            and lp["strike"] < short_strike
                            and lp["contracts"] >= contracts
                        ):
                            matched_lp = lp
                            break

                    if matched_lp is not None:
                        matched_lp["used"] = True
                        spread_width = short_strike - matched_lp["strike"]
                        reserve = contracts * multiplier * spread_width
                    elif (
                        self.config.reserve_mode == CashReserveMode.NET_PREMIUM
                    ):
                        credit = contracts * multiplier * limit_price
                        reserve = max(0.0, gross_obligation - credit)
                    else:
                        # GROSS_ASSIGNMENT and BROKER_MARGIN both default to gross
                        reserve = gross_obligation

                    if reserve > 0:
                        total += reserve

        return total

    # ------------------------------------------------------------------
    # Margin safety buffer
    # ------------------------------------------------------------------

    def _compute_margin_safety_buffer(
        self, result: CashAvailabilityResult
    ) -> float:
        """Return a conservative margin-safety buffer.

        If excess liquidity is reported and below 10% of cash balance, add a
        buffer equal to the gap so deployable cash is not over-stated.
        """
        excess = result.broker_excess_liquidity
        cash = result.cash_balance
        if excess <= 0 or cash <= 0:
            return 0.0
        # If excess liquidity < 10% of cash, signal tightness
        if excess < cash * 0.10:
            return cash * 0.05  # add 5% buffer
        return 0.0
