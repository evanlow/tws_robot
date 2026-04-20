"""Multi-Account Manager.

Aggregates positions, equity, and risk metrics across multiple trading
accounts and provides unified portfolio views.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AccountSnapshot:
    """Point-in-time snapshot of a single account."""
    account_id: str
    label: str = ""
    equity: float = 0.0
    cash_balance: float = 0.0
    margin_used: float = 0.0
    margin_available: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    position_count: int = 0
    positions: List[Dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "label": self.label,
            "equity": round(self.equity, 2),
            "cash_balance": round(self.cash_balance, 2),
            "margin_used": round(self.margin_used, 2),
            "margin_available": round(self.margin_available, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "position_count": self.position_count,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AggregateView:
    """Aggregated metrics across all tracked accounts."""
    total_equity: float = 0.0
    total_cash: float = 0.0
    total_margin_used: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    total_positions: int = 0
    account_count: int = 0
    largest_account: str = ""
    concentration_pct: float = 0.0  # largest account as % of total
    accounts: List[Dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "total_equity": round(self.total_equity, 2),
            "total_cash": round(self.total_cash, 2),
            "total_margin_used": round(self.total_margin_used, 2),
            "total_unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "total_realized_pnl": round(self.total_realized_pnl, 2),
            "total_positions": self.total_positions,
            "account_count": self.account_count,
            "largest_account": self.largest_account,
            "concentration_pct": round(self.concentration_pct, 2),
            "accounts": self.accounts,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class CrossAccountRisk:
    """Cross-account risk assessment."""
    duplicate_symbols: List[str] = field(default_factory=list)
    total_symbol_exposure: Dict[str, float] = field(default_factory=dict)
    over_concentrated_symbols: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "duplicate_symbols": self.duplicate_symbols,
            "total_symbol_exposure": {k: round(v, 2) for k, v in self.total_symbol_exposure.items()},
            "over_concentrated_symbols": self.over_concentrated_symbols,
            "warnings": self.warnings,
        }


class MultiAccountManager:
    """Manages and aggregates data across multiple trading accounts.

    Each account is tracked via periodic snapshots.  The manager provides
    aggregate views (total equity, combined positions) and cross-account
    risk analysis (duplicate symbols, concentration).
    """

    def __init__(self, concentration_limit: float = 0.20):
        self.concentration_limit = concentration_limit
        self._accounts: Dict[str, AccountSnapshot] = {}
        self._history: Dict[str, List[AccountSnapshot]] = {}

    # ------------------------------------------------------------------
    # Account Management
    # ------------------------------------------------------------------

    def update_account(self, snapshot: AccountSnapshot) -> None:
        """Update or add an account snapshot."""
        self._accounts[snapshot.account_id] = snapshot
        if snapshot.account_id not in self._history:
            self._history[snapshot.account_id] = []
        self._history[snapshot.account_id].append(snapshot)
        logger.debug("Account %s updated — equity: %.2f", snapshot.account_id, snapshot.equity)

    def remove_account(self, account_id: str) -> bool:
        """Remove an account from tracking. Returns True if found."""
        removed = self._accounts.pop(account_id, None)
        return removed is not None

    def get_account(self, account_id: str) -> Optional[AccountSnapshot]:
        """Return the latest snapshot for an account."""
        return self._accounts.get(account_id)

    def list_accounts(self) -> List[AccountSnapshot]:
        """Return latest snapshots for all tracked accounts."""
        return list(self._accounts.values())

    # ------------------------------------------------------------------
    # Aggregate View
    # ------------------------------------------------------------------

    def get_aggregate_view(self) -> AggregateView:
        """Build an aggregated view across all accounts."""
        if not self._accounts:
            return AggregateView()

        total_equity = 0.0
        total_cash = 0.0
        total_margin = 0.0
        total_upnl = 0.0
        total_rpnl = 0.0
        total_pos = 0
        largest_eq = 0.0
        largest_id = ""
        acct_list: List[Dict] = []

        for snap in self._accounts.values():
            total_equity += snap.equity
            total_cash += snap.cash_balance
            total_margin += snap.margin_used
            total_upnl += snap.unrealized_pnl
            total_rpnl += snap.realized_pnl
            total_pos += snap.position_count
            if snap.equity > largest_eq:
                largest_eq = snap.equity
                largest_id = snap.account_id
            acct_list.append(snap.to_dict())

        conc = largest_eq / total_equity if total_equity > 0 else 0.0

        return AggregateView(
            total_equity=total_equity,
            total_cash=total_cash,
            total_margin_used=total_margin,
            total_unrealized_pnl=total_upnl,
            total_realized_pnl=total_rpnl,
            total_positions=total_pos,
            account_count=len(self._accounts),
            largest_account=largest_id,
            concentration_pct=conc * 100,
            accounts=acct_list,
        )

    # ------------------------------------------------------------------
    # Cross-Account Risk
    # ------------------------------------------------------------------

    def analyze_cross_account_risk(self) -> CrossAccountRisk:
        """Identify risk arising from cross-account holdings.

        Detects duplicate symbols held in multiple accounts and
        flags symbols whose combined exposure exceeds the concentration
        limit.
        """
        symbol_exposure: Dict[str, float] = {}
        symbol_accounts: Dict[str, List[str]] = {}

        total_equity = sum(s.equity for s in self._accounts.values())

        for snap in self._accounts.values():
            for pos in snap.positions:
                sym = pos.get("symbol", "?")
                mv = abs(pos.get("market_value", 0))
                symbol_exposure[sym] = symbol_exposure.get(sym, 0.0) + mv
                if sym not in symbol_accounts:
                    symbol_accounts[sym] = []
                if snap.account_id not in symbol_accounts[sym]:
                    symbol_accounts[sym].append(snap.account_id)

        duplicates = [sym for sym, accts in symbol_accounts.items() if len(accts) > 1]
        over_concentrated: List[str] = []
        warnings: List[str] = []

        if total_equity > 0:
            for sym, exposure in symbol_exposure.items():
                pct = exposure / total_equity
                if pct > self.concentration_limit:
                    over_concentrated.append(sym)
                    warnings.append(
                        f"{sym} combined exposure {pct*100:.1f}% exceeds "
                        f"{self.concentration_limit*100:.0f}% limit"
                    )

        if duplicates:
            warnings.append(
                f"{len(duplicates)} symbol(s) held in multiple accounts: "
                + ", ".join(sorted(duplicates))
            )

        return CrossAccountRisk(
            duplicate_symbols=sorted(duplicates),
            total_symbol_exposure=symbol_exposure,
            over_concentrated_symbols=sorted(over_concentrated),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_account_history(self, account_id: str, limit: int = 30) -> List[AccountSnapshot]:
        """Return recent historical snapshots for an account."""
        return list(self._history.get(account_id, [])[-limit:])

    def get_summary(self) -> dict:
        agg = self.get_aggregate_view()
        return {
            "account_count": agg.account_count,
            "total_equity": round(agg.total_equity, 2),
            "total_positions": agg.total_positions,
            "concentration_limit_pct": round(self.concentration_limit * 100, 2),
        }
