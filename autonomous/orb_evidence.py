"""ORB Phase 2.7 evidence ledger (autonomous/orb_evidence.py, #211).

A read-only evidence/reporting layer reconstructed purely from the durable
autonomous audit log already written by the earlier ORB phases:

- ``autonomous.orb_proposals`` (``kind == "orb_proposal"``): proposal
  creation/skip/expiry/execution — the setup evidence (opening range,
  confirmation candle, model, gates) for every symbol/session, whether or not
  a trade ever happened.
- ``autonomous.orb_execution`` (``kind == "orb_paper_execution"``): paper
  execution / rejection of a valid proposal.
- ``autonomous.orb_exit_manager`` (``kind == "orb_intraday_exit"``): entry
  fill/failure and exit fill/failure for a paper trade (target, stop,
  force-flat, max-holding, manual close, emergency stop, entry cancellation).

Because every one of those lifecycle events is already audit-logged
(including *rejections* and *no-trade* outcomes), a trader can reconstruct
every ORB decision — trade or no-trade — from these files alone, even after a
process restart. This module never places, routes, or simulates an order; it
only reads and summarizes the existing audit trail.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Audit-log "kind" values written by the earlier ORB phases (#208/#209/#210).
KIND_PROPOSAL = "orb_proposal"
KIND_PAPER_EXECUTION = "orb_paper_execution"
KIND_INTRADAY_EXIT = "orb_intraday_exit"
KIND_SESSION_CONTROL = "orb_session_control"

_ORB_KINDS = frozenset({
    KIND_PROPOSAL, KIND_PAPER_EXECUTION, KIND_INTRADAY_EXIT, KIND_SESSION_CONTROL,
})

# Matches the exact ``autonomous_trading_YYYYMMDD.jsonl`` naming written by
# :class:`autonomous.audit.AuditLogger`. This only enforces the 8-digit shape
# of the date stamp (not calendar validity, e.g. ``99999999`` would match) —
# malformed-but-8-digit names are harmless here since each file is parsed
# independently and unreadable/invalid JSON lines are already skipped.
_LOG_FILE_RE = re.compile(r"autonomous_trading_\d{8}\.jsonl$")

# Estimated per-share commission used when no explicit commission model is
# wired to a paper trade (paper trades never incur a real commission). This
# mirrors the backtest lab's default so evidence stays comparable across
# backtest and paper stages.
DEFAULT_COMMISSION_PER_SHARE = 0.005

# Promotion classifications (shared vocabulary with autonomous.orb_backtest_reports).
READY_FOR_PAPER = "READY_FOR_PAPER"
NEEDS_MORE_DATA = "NEEDS_MORE_DATA"
DO_NOT_TRADE = "DO_NOT_TRADE"
TINY_LIVE_CANDIDATE = "TINY_LIVE_CANDIDATE"


# ---------------------------------------------------------------------------
# Reading the audit trail
# ---------------------------------------------------------------------------

def _log_files(log_dir: str) -> List[Path]:
    """Every daily audit log file, validated against the exact date-stamped name.

    ``glob`` alone would also match a malformed name like
    ``autonomous_trading_abc.jsonl``; the regex enforces the strict
    ``autonomous_trading_YYYYMMDD.jsonl`` naming written by
    :class:`autonomous.audit.AuditLogger`.
    """
    base = Path(log_dir)
    if not base.exists():
        return []
    try:
        return sorted(p for p in base.iterdir() if _LOG_FILE_RE.match(p.name))
    except OSError:  # pragma: no cover - defensive
        return []


def iter_orb_records(log_dir: str = "logs") -> Iterator[Dict[str, Any]]:
    """Yield every ORB-kind audit record across all daily audit log files.

    Missing/unreadable files or malformed lines are skipped defensively; the
    evidence ledger must never crash a review because a single log line is
    corrupt.
    """
    for path in _log_files(log_dir):
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("kind") in _ORB_KINDS:
                        yield rec
        except OSError:  # pragma: no cover - defensive
            continue


def _matches(rec: Dict[str, Any], strategy_name: Optional[str], session_date: Optional[str]) -> bool:
    if strategy_name is not None and rec.get("strategy") != strategy_name:
        return False
    if session_date is not None and rec.get("session_date") != session_date:
        return False
    return True


# ---------------------------------------------------------------------------
# Proposal lifecycle evidence
# ---------------------------------------------------------------------------

@dataclass
class ProposalEvidence:
    """Full lifecycle of a single recommend-only ORB proposal.

    The setup-context fields (``entry_model`` through ``gates``) are
    reconstructed from the ``card`` payload persisted on the ``proposal_created``
    audit record (see :meth:`autonomous.orb_proposals.ORBProposalStore._log`)
    so a skipped/expired/no-trade proposal still shows the full trade card —
    entry model, opening range, confirmation candle, gate results, and setup
    evidence — from the audit log alone, even after a restart.
    """

    proposal_id: str
    strategy_name: str
    symbol: str
    session_date: str
    status: str = "PENDING"
    reason: Optional[str] = None
    skip_reason: Optional[str] = None
    expiry_reason: Optional[str] = None
    trade_id: Optional[str] = None
    created_at: Optional[str] = None

    # Setup/trade-card context reconstructed from the ``proposal_created``
    # audit record's ``card`` payload (absent for older records predating
    # this enrichment).
    entry_model: Optional[str] = None
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    risk_per_share: Optional[float] = None
    reward_per_share: Optional[float] = None
    rr_ratio: Optional[float] = None
    quantity: Optional[int] = None
    range_high: Optional[float] = None
    range_low: Optional[float] = None
    range_width_pct: Optional[float] = None
    confirmation_candle: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    gates: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _apply_proposal_card(item: "ProposalEvidence", card: Dict[str, Any]) -> None:
    """Populate the setup/trade-card fields of ``item`` from a proposal ``card``."""
    item.entry_model = card.get("entry_model")
    item.direction = card.get("direction")
    item.entry_price = card.get("entry_price")
    item.stop_price = card.get("stop_price")
    item.target_price = card.get("target_price")
    item.risk_per_share = card.get("risk_per_share")
    item.reward_per_share = card.get("reward_per_share")
    item.rr_ratio = card.get("rr_ratio")
    item.quantity = card.get("quantity")
    item.range_high = card.get("range_high")
    item.range_low = card.get("range_low")
    item.range_width_pct = card.get("range_width_pct")
    item.confirmation_candle = card.get("confirmation_candle")
    item.evidence = card.get("evidence")
    item.gates = card.get("gates")


def build_proposal_ledger(
    log_dir: str = "logs",
    *,
    strategy_name: Optional[str] = None,
    session_date: Optional[str] = None,
) -> Dict[str, ProposalEvidence]:
    """Reconstruct every proposal's lifecycle keyed by ``proposal_id``."""
    out: Dict[str, ProposalEvidence] = {}
    for rec in iter_orb_records(log_dir):
        if rec.get("kind") != KIND_PROPOSAL:
            continue
        if not _matches(rec, strategy_name, session_date):
            continue
        pid = rec.get("proposal_id")
        if not pid:
            continue
        action = rec.get("action")
        item = out.get(pid)
        if item is None:
            item = ProposalEvidence(
                proposal_id=pid,
                strategy_name=rec.get("strategy", ""),
                symbol=rec.get("symbol", ""),
                session_date=rec.get("session_date", ""),
            )
            out[pid] = item
        if action == "proposal_created":
            item.created_at = rec.get("timestamp")
            card = rec.get("card")
            if card:
                _apply_proposal_card(item, card)
        item.status = rec.get("status", item.status)
        if action == "proposal_skipped":
            item.skip_reason = rec.get("reason")
        elif action == "proposal_expired":
            item.expiry_reason = rec.get("reason")
        elif action == "proposal_executed":
            item.trade_id = rec.get("trade_id")
    return out


# ---------------------------------------------------------------------------
# Trade evidence (proposal + paper execution + intraday exit, joined)
# ---------------------------------------------------------------------------

@dataclass
class TradeEvidence:
    """Per-trade evidence: everything needed to explain a single ORB trade."""

    trade_id: str
    proposal_id: Optional[str] = None
    strategy_name: str = ""
    symbol: str = ""
    session_date: str = ""
    entry_model: Optional[str] = None
    setup_ref: Optional[str] = None
    quantity: Optional[int] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    protection_status: Optional[str] = None
    mode: Optional[str] = None

    actual_entry_price: Optional[float] = None
    entry_slippage: Optional[float] = None
    exit_price: Optional[float] = None
    exit_slippage: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_r: Optional[float] = None
    mfe_r: Optional[float] = None
    mae_r: Optional[float] = None

    status: str = "SUBMITTED"
    failure_note: Optional[str] = None
    operator_notes: str = ""

    def risk_dollars(self) -> Optional[float]:
        if self.quantity is None or self.entry_price is None or self.stop_price is None:
            return None
        return round((self.entry_price - self.stop_price) * self.quantity, 2)

    def rr_ratio(self) -> Optional[float]:
        if self.entry_price is None or self.stop_price is None or self.target_price is None:
            return None
        risk = self.entry_price - self.stop_price
        if risk <= 0:
            return None
        return round((self.target_price - self.entry_price) / risk, 4)

    def commission(self, commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE) -> Optional[float]:
        """Estimated round-trip commission (entry + exit) for a closed trade.

        Paper trades never incur a real commission; this is a conservative
        cost-sensitivity estimate consistent with the backtest lab so paper
        evidence stays comparable to backtest evidence.
        """
        if self.quantity is None or self.status != "CLOSED":
            return None
        return round(2 * float(commission_per_share) * abs(self.quantity), 2)

    def realized_pnl(self) -> Optional[float]:
        if self.quantity is None or self.actual_entry_price is None or self.exit_price is None:
            return None
        return round((self.exit_price - self.actual_entry_price) * self.quantity, 2)

    def result(self) -> str:
        """WIN / LOSS / BREAKEVEN / OPEN / FAILED classification."""
        if self.status == "FAILED":
            return "FAILED"
        if self.realized_r is None:
            return "OPEN"
        if self.realized_r > 0:
            return "WIN"
        if self.realized_r < 0:
            return "LOSS"
        return "BREAKEVEN"

    def to_dict(self, *, commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE) -> Dict[str, Any]:
        out = asdict(self)
        out["risk_dollars"] = self.risk_dollars()
        out["rr_ratio"] = self.rr_ratio()
        out["commission"] = self.commission(commission_per_share)
        out["realized_pnl"] = self.realized_pnl()
        out["result"] = self.result()
        return out


def build_trade_ledger(
    log_dir: str = "logs",
    *,
    strategy_name: Optional[str] = None,
    session_date: Optional[str] = None,
) -> Dict[str, TradeEvidence]:
    """Reconstruct every paper trade's full evidence, keyed by ``trade_id``."""
    trades: Dict[str, TradeEvidence] = {}

    for rec in iter_orb_records(log_dir):
        kind = rec.get("kind")
        if kind == KIND_PAPER_EXECUTION and rec.get("action") == "orb_paper_executed":
            if not _matches(rec, strategy_name, session_date):
                continue
            tid = rec.get("trade_id")
            if not tid:
                continue
            trades[tid] = TradeEvidence(
                trade_id=tid,
                proposal_id=rec.get("proposal_id"),
                strategy_name=rec.get("strategy", ""),
                symbol=rec.get("symbol", ""),
                session_date=rec.get("session_date", ""),
                entry_model=rec.get("entry_model"),
                setup_ref=rec.get("setup_ref"),
                quantity=rec.get("quantity"),
                entry_price=rec.get("entry_price"),
                stop_price=rec.get("stop_price"),
                target_price=rec.get("target_price"),
                protection_status=rec.get("protection_status"),
                mode=rec.get("mode"),
            )

    for rec in iter_orb_records(log_dir):
        if rec.get("kind") != KIND_INTRADAY_EXIT:
            continue
        tid = rec.get("trade_id")
        trade = trades.get(tid) if tid else None
        if trade is None:
            continue
        action = rec.get("action")
        if action == "entry_filled":
            trade.actual_entry_price = rec.get("fill_price")
            trade.entry_slippage = rec.get("entry_slippage")
            trade.status = "OPEN"
        elif action == "entry_failed":
            trade.status = "FAILED"
            trade.failure_note = rec.get("note")
        elif action == "exit_filled":
            trade.exit_price = rec.get("fill_price")
            trade.exit_reason = rec.get("reason")
            trade.realized_r = rec.get("realized_r")
            trade.exit_slippage = rec.get("exit_slippage")
            trade.mfe_r = rec.get("mfe_r")
            trade.mae_r = rec.get("mae_r")
            trade.status = "CLOSED"
        elif action == "exit_failed_no_price":
            trade.status = "FAILED"
            trade.failure_note = "no live price available to flatten position"
            trade.exit_reason = rec.get("would_exit_reason")
        elif action == "cancel_entry":
            trade.status = "CANCELLED"
            trade.exit_reason = "ENTRY_CANCELLED"

    return trades


# ---------------------------------------------------------------------------
# Rejections (blocked/failed execution attempts that never became a trade)
# ---------------------------------------------------------------------------

def build_rejection_ledger(
    log_dir: str = "logs",
    *,
    strategy_name: Optional[str] = None,
    session_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Paper-execution attempts that were blocked/rejected before a trade existed."""
    out: List[Dict[str, Any]] = []
    for rec in iter_orb_records(log_dir):
        if rec.get("kind") != KIND_PAPER_EXECUTION:
            continue
        if rec.get("action") != "orb_paper_rejected":
            continue
        if not _matches(rec, strategy_name, session_date):
            continue
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Per-session evidence (trade and no-trade sessions alike)
# ---------------------------------------------------------------------------

def _no_trade_explanation(
    proposals: List[ProposalEvidence],
    rejections: List[Dict[str, Any]],
    symbols_watched: Optional[List[str]],
) -> str:
    if not proposals and not rejections:
        watched = ", ".join(symbols_watched) if symbols_watched else "the watched symbols"
        return (
            f"No ORB setup proposal was generated for {watched} this session "
            "(no confirmed Model A/B breakout was detected, or candle data was "
            "insufficient/degraded)."
        )
    parts: List[str] = []
    skipped = [p for p in proposals if p.status == "SKIPPED"]
    expired = [p for p in proposals if p.status == "EXPIRED"]
    if skipped:
        reasons = sorted({p.skip_reason or "unspecified" for p in skipped})
        parts.append(f"{len(skipped)} proposal(s) skipped ({', '.join(reasons)})")
    if expired:
        reasons = sorted({p.expiry_reason or "unspecified" for p in expired})
        parts.append(f"{len(expired)} proposal(s) expired ({', '.join(reasons)})")
    if rejections:
        reasons = sorted({r.get("reason", "unspecified") for r in rejections})
        parts.append(f"{len(rejections)} execution attempt(s) blocked ({', '.join(reasons)})")
    if not parts:
        return "No trade was taken this session."
    return "No trade was taken this session: " + "; ".join(parts) + "."


def build_session_evidence(
    log_dir: str,
    strategy_name: str,
    session_date: str,
    *,
    symbols_watched: Optional[List[str]] = None,
    config_snapshot: Optional[Dict[str, Any]] = None,
    commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE,
) -> Dict[str, Any]:
    """Build the full end-of-session review for one ORB strategy/session.

    Works identically for a trade day and a no-trade day: a no-trade session
    always has a populated ``no_trade_explanation`` reconstructed from the
    proposal skip/expiry reasons and any blocked execution attempts, so it is
    just as explainable as a trade day.
    """
    proposal_ledger = build_proposal_ledger(
        log_dir, strategy_name=strategy_name, session_date=session_date,
    )
    proposals = sorted(proposal_ledger.values(), key=lambda p: p.created_at or "")

    trade_ledger = build_trade_ledger(
        log_dir, strategy_name=strategy_name, session_date=session_date,
    )
    trades = sorted(trade_ledger.values(), key=lambda t: t.trade_id)

    rejections = build_rejection_ledger(
        log_dir, strategy_name=strategy_name, session_date=session_date,
    )

    by_status: Dict[str, int] = defaultdict(int)
    for p in proposals:
        by_status[p.status] += 1

    exits_by_reason: Dict[str, int] = defaultdict(int)
    for t in trades:
        if t.exit_reason:
            exits_by_reason[t.exit_reason] += 1

    no_trade = len(trades) == 0
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_name": strategy_name,
        "session_date": session_date,
        "symbols_watched": list(symbols_watched or []),
        "config_snapshot": config_snapshot or {},
        "proposals": {
            "total": len(proposals),
            "created": len(proposals),
            "skipped": by_status.get("SKIPPED", 0),
            "expired": by_status.get("EXPIRED", 0),
            "executed": by_status.get("EXECUTED", 0),
            "pending": by_status.get("PENDING", 0),
            "items": [p.to_dict() for p in proposals],
        },
        "rejections": rejections,
        "trades": {
            "total": len(trades),
            "closed": sum(1 for t in trades if t.status == "CLOSED"),
            "failed": sum(1 for t in trades if t.status == "FAILED"),
            "open": sum(1 for t in trades if t.status == "OPEN"),
            "exits_by_reason": dict(exits_by_reason),
            "items": [t.to_dict(commission_per_share=commission_per_share) for t in trades],
        },
        "no_trade": no_trade,
        "no_trade_explanation": (
            _no_trade_explanation(proposals, rejections, symbols_watched) if no_trade else None
        ),
    }


# ---------------------------------------------------------------------------
# Multi-session evidence summaries and grouping (promotion review)
# ---------------------------------------------------------------------------

_GROUP_KEYS = {
    "symbol": lambda t: t.get("symbol"),
    "model": lambda t: t.get("entry_model"),
    "date": lambda t: t.get("session_date"),
    "result": lambda t: t.get("result"),
}


def group_trades(trades: Iterable[Dict[str, Any]], by: str) -> Dict[str, List[Dict[str, Any]]]:
    """Group trade evidence dicts by symbol, model, date, or result."""
    keyfn = _GROUP_KEYS.get(by)
    if keyfn is None:
        raise ValueError(f"unknown grouping '{by}'; expected one of {sorted(_GROUP_KEYS)}")
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in trades:
        out[str(keyfn(t))].append(t)
    return dict(out)


def _avg(values: List[float]) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def build_evidence_summary(
    log_dir: str,
    strategy_name: str,
    *,
    commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE,
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Aggregate every trade/proposal evidence record for a strategy.

    Distinguishes backtest evidence (``logs/orb_backtest_evidence_*.jsonl``,
    written by :mod:`autonomous.orb_backtest_reports`) from paper evidence
    (this module's trade ledger) so a trader can see both stages side by
    side, and derives a promotion classification from the paper evidence.

    ``symbols`` should be the strategy's configured/watched symbols; it is
    used to scope backtest evidence that predates ``strategy_name`` tagging
    (see :func:`_load_backtest_evidence`) so an unrelated strategy never
    inherits another strategy's saved readiness.
    """
    proposal_ledger = build_proposal_ledger(log_dir, strategy_name=strategy_name)
    trade_ledger = build_trade_ledger(log_dir, strategy_name=strategy_name)
    trade_dicts = [t.to_dict(commission_per_share=commission_per_share) for t in trade_ledger.values()]

    closed = [t for t in trade_dicts if t["status"] == "CLOSED"]
    cancelled = [t for t in trade_dicts if t["status"] == "CANCELLED"]
    wins = [t for t in closed if t["result"] == "WIN"]
    losses = [t for t in closed if t["result"] == "LOSS"]
    failed = [t for t in trade_dicts if t["status"] == "FAILED"]

    paper_summary = {
        "total_trades": len(trade_dicts),
        "closed_trades": len(closed),
        "cancelled_trades": len(cancelled),
        "failed_trades": len(failed),
        "win_count": len(wins),
        "loss_count": len(losses),
        # Win rate is wins / all closed trades (including breakeven trades in
        # the denominator), not wins / (wins + losses).
        "win_rate": round(len(wins) / len(closed), 4) if closed else None,
        "avg_realized_r": _avg([t["realized_r"] for t in closed]),
        "avg_mfe_r": _avg([t["mfe_r"] for t in closed]),
        "avg_mae_r": _avg([t["mae_r"] for t in closed]),
        "avg_entry_slippage": _avg([t["entry_slippage"] for t in trade_dicts]),
        "avg_exit_slippage": _avg([t["exit_slippage"] for t in closed]),
        "total_commission": round(sum(t["commission"] or 0.0 for t in closed), 2),
        "total_realized_pnl": round(sum(t["realized_pnl"] or 0.0 for t in closed), 2),
    }

    backtest_evidence = _load_backtest_evidence(log_dir, strategy_name, symbols=symbols)

    by_symbol = group_trades(trade_dicts, "symbol")
    by_model = group_trades(trade_dicts, "model")
    by_date = group_trades(trade_dicts, "date")
    by_result = group_trades(trade_dicts, "result")

    promotion = classify_promotion(paper_summary, backtest_evidence)

    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_name": strategy_name,
        "proposal_count": len(proposal_ledger),
        "paper": paper_summary,
        "backtest": backtest_evidence,
        "trades": trade_dicts,
        "by_symbol": {k: len(v) for k, v in by_symbol.items()},
        "by_model": {k: len(v) for k, v in by_model.items()},
        "by_date": {k: len(v) for k, v in by_date.items()},
        "by_result": {k: len(v) for k, v in by_result.items()},
        "promotion": promotion,
    }


def _load_backtest_evidence(
    log_dir: str,
    strategy_name: str,
    *,
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Best-effort summary of saved backtest evidence relevant to this strategy.

    Scoping precedence, most to least precise:

    1. Records with an explicit ``strategy_name`` field (written by
       :func:`autonomous.orb_backtest_reports.save_evidence` when the backtest
       lab is run against a specific configured strategy) are matched exactly
       against ``strategy_name`` and never leak into another strategy's
       summary.
    2. Older/standalone records have no ``strategy_name`` (the backtest lab
       can be run before any ORB strategy is configured). For those, if the
       caller supplies the strategy's configured/watched ``symbols``, a
       record only counts when its ``symbols`` overlap — mirroring the same
       symbol-overlap heuristic already used by
       :meth:`autonomous.orb_session_manager.ORBSessionManager._has_paper_evidence`.
    3. If neither an explicit ``strategy_name`` match nor ``symbols`` are
       available (no strategy-scoped records exist and the caller did not
       supply watched symbols), every record counts. This last resort keeps
       ad-hoc/standalone backtest evidence visible before any strategy has
       been configured, at the cost of potentially over-counting; callers
       that know a strategy's watched symbols should always pass ``symbols``.
    """
    base = Path(log_dir)
    want_symbols = {s.upper() for s in (symbols or [])}
    statuses: List[str] = []
    count = 0
    try:
        files = sorted(base.glob("orb_backtest_evidence_*.jsonl"))
    except OSError:  # pragma: no cover - defensive
        files = []
    for path in files:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rec_strategy = rec.get("strategy_name")
                if rec_strategy is not None:
                    if rec_strategy != strategy_name:
                        continue
                elif want_symbols:
                    rec_symbols = {str(s).upper() for s in (rec.get("symbols") or [])}
                    if not (rec_symbols & want_symbols):
                        continue
                count += 1
                status = (rec.get("readiness") or {}).get("status")
                if status:
                    statuses.append(status)
        except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
            continue
    latest_status = statuses[-1] if statuses else None
    return {"saved_evidence_count": count, "latest_readiness_status": latest_status}


@dataclass
class PromotionCriteria:
    """Conservative thresholds for classifying paper evidence for promotion.

    Promotion classification (:func:`classify_promotion`) is driven by
    ``avg_realized_r`` rather than ``win_rate`` precisely because win rate
    (wins / all closed trades, including breakeven trades in the
    denominator — see ``paper_summary["win_rate"]`` in
    :func:`build_evidence_summary`) can look healthy while average realized R
    is flat or negative; a high win rate with a poor average R is not, by
    itself, evidence of a promotable edge.
    """

    min_trade_count: int = 20
    min_avg_r: float = 0.0
    max_failed_trade_ratio: float = 0.1
    tiny_live_min_trade_count: int = 50
    tiny_live_min_avg_r: float = 0.1

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_promotion(
    paper_summary: Dict[str, Any],
    backtest_evidence: Optional[Dict[str, Any]] = None,
    criteria: Optional[PromotionCriteria] = None,
) -> Dict[str, Any]:
    """Classify READY_FOR_PAPER / NEEDS_MORE_DATA / DO_NOT_TRADE / TINY_LIVE_CANDIDATE.

    This is a conservative, evidence-driven classification only. It never
    enables live trading by itself — ``TINY_LIVE_CANDIDATE`` merely flags that
    paper evidence has reached a stage worth an explicit, separate human
    promotion decision.
    """
    c = criteria or PromotionCriteria()
    reasons: List[str] = []

    total = paper_summary.get("total_trades", 0)
    closed = paper_summary.get("closed_trades", 0)
    failed = paper_summary.get("failed_trades", 0)
    avg_r = paper_summary.get("avg_realized_r")

    if closed == 0:
        backtest_status = (backtest_evidence or {}).get("latest_readiness_status")
        if backtest_status == READY_FOR_PAPER:
            return {
                "status": READY_FOR_PAPER,
                "reasons": ["backtest evidence is READY_FOR_PAPER; no paper trades recorded yet"],
                "criteria": c.as_dict(),
            }
        return {
            "status": NEEDS_MORE_DATA,
            "reasons": ["no closed paper trades recorded yet"],
            "criteria": c.as_dict(),
        }

    failed_ratio = failed / total if total else 0.0
    if failed_ratio > c.max_failed_trade_ratio:
        reasons.append(
            f"failed-trade ratio {failed_ratio:.2f} above {c.max_failed_trade_ratio}"
        )
    if avg_r is not None and avg_r < c.min_avg_r:
        reasons.append(f"avg_realized_r {avg_r} below minimum {c.min_avg_r}")

    if reasons:
        return {"status": DO_NOT_TRADE, "reasons": reasons, "criteria": c.as_dict()}

    if closed < c.min_trade_count:
        return {
            "status": NEEDS_MORE_DATA,
            "reasons": [f"closed trades {closed} below minimum {c.min_trade_count}"],
            "criteria": c.as_dict(),
        }

    if closed >= c.tiny_live_min_trade_count and (avg_r or 0.0) >= c.tiny_live_min_avg_r:
        return {
            "status": TINY_LIVE_CANDIDATE,
            "reasons": [
                f"closed trades {closed} >= {c.tiny_live_min_trade_count} and "
                f"avg_realized_r {avg_r} >= {c.tiny_live_min_avg_r}"
            ],
            "criteria": c.as_dict(),
        }

    return {
        "status": READY_FOR_PAPER,
        "reasons": ["paper evidence meets minimum trade-count and avg-R thresholds"],
        "criteria": c.as_dict(),
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_CSV_COLUMNS = [
    "trade_id", "proposal_id", "strategy_name", "symbol", "session_date",
    "entry_model", "quantity", "entry_price", "actual_entry_price", "stop_price",
    "target_price", "exit_price", "exit_reason", "entry_slippage", "exit_slippage",
    "commission", "realized_r", "mfe_r", "mae_r", "realized_pnl", "status", "result",
]


def export_evidence(
    log_dir: str,
    strategy_name: str,
    fmt: str = "json",
    *,
    commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE,
    symbols: Optional[List[str]] = None,
) -> str:
    """Export the full evidence summary for a strategy as JSON or CSV text."""
    summary = build_evidence_summary(
        log_dir, strategy_name, commission_per_share=commission_per_share, symbols=symbols,
    )
    fmt = (fmt or "json").lower()
    if fmt == "json":
        return json.dumps(summary, indent=2, sort_keys=True)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for t in summary["trades"]:
            writer.writerow(t)
        return buf.getvalue()
    raise ValueError(f"unsupported export format '{fmt}'; expected 'json' or 'csv'")
