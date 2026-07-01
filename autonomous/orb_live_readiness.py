"""ORB Phase 4 — tiny-live / assisted-live readiness gates (autonomous/orb_live_readiness.py, #213).

Defines the guarded path from paper ORB evidence to tiny-live / assisted-live
review. This module never places, routes, or simulates an order and never
enables live trading by itself — it only evaluates whether every required
readiness gate currently passes, and audit-logs the evaluation.

Safety posture (Prime Directive):
- Live remains locked by default: :func:`evaluate_orb_live_readiness` returns
  :data:`LOCKED` unless *every* required gate passes.
- Tiny-live is evidence-gated: candidate status is computed from paper
  evidence thresholds (trade count, average realized R-multiple after costs,
  drawdown, consecutive losses, entry slippage) — never from manual optimism.
- Assisted-live additionally requires an explicit account/session
  confirmation from the operator; a mismatched or missing account id always
  fails closed.
- A broker-visible protective stop/target/bracket must be confirmed (via the
  strategy config's ``require_stop``/``require_target``/``require_bracket``
  flags and zero unresolved protection failures) before live entry can be
  considered.
- Long-only until a separate short-side lifecycle exists; Model C stays
  disabled until deterministic and evidence-backed. Both are hard gates here.
- Every readiness evaluation and operator decision is written to the
  autonomous audit log (:class:`autonomous.audit.AuditLogger`).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from autonomous.audit import AuditLogger
from autonomous.orb_evidence import PromotionCriteria, classify_promotion

logger = logging.getLogger(__name__)

# Audit-log record kind for every live-readiness evaluation / operator decision.
_AUDIT_KIND = "orb_live_readiness"

# Modes that may be requested for readiness evaluation. Any other value is
# rejected and always evaluates as LOCKED.
TINY_LIVE_CANDIDATE_MODE = "tiny_live_candidate"
ASSISTED_LIVE_MODE = "assisted_live"
_SUPPORTED_MODES = frozenset({TINY_LIVE_CANDIDATE_MODE, ASSISTED_LIVE_MODE})

# Market-data sources acceptable for live ORB consideration. Yahoo/advisory
# feeds are never acceptable for live execution (mirrors
# ``autonomous.runner_config.AutonomousLiveRunnerConfig.live_market_data_provider``).
DEFAULT_ACCEPTABLE_MARKET_DATA_SOURCES = ("ibkr",)

# Hard ceiling for tiny-live deployable-cash sizing: 1% of deployable cash.
# Mirrors the "tiny" in tiny-live — anything larger is not a tiny-live
# experiment and must go through the full live-readiness/fit-for-trading
# review instead.
MAX_TINY_LIVE_CASH_PCT = 0.01


class ORBLiveReadinessStatus(str, Enum):
    """Overall live-readiness outcome. Never implies an order was placed."""

    LOCKED = "LOCKED"
    TINY_LIVE_CANDIDATE = "TINY_LIVE_CANDIDATE"
    ASSISTED_LIVE_CANDIDATE = "ASSISTED_LIVE_CANDIDATE"


LOCKED = ORBLiveReadinessStatus.LOCKED.value
TINY_LIVE_CANDIDATE = ORBLiveReadinessStatus.TINY_LIVE_CANDIDATE.value
ASSISTED_LIVE_CANDIDATE = ORBLiveReadinessStatus.ASSISTED_LIVE_CANDIDATE.value


# ---------------------------------------------------------------------------
# R-multiple statistics (drawdown / consecutive losses)
# ---------------------------------------------------------------------------

def compute_r_stats(realized_r_values: Sequence[Optional[float]]) -> Dict[str, Any]:
    """Compute max drawdown (in cumulative R) and max consecutive losses.

    ``realized_r_values`` must be in chronological order (oldest first).
    ``None`` values are skipped. Drawdown is measured against the running
    peak of cumulative realized R, matching common trading-evidence
    convention. Returns zeros for an empty/all-``None`` sequence.
    """
    running = 0.0
    peak = 0.0
    max_drawdown_r = 0.0
    consecutive_losses = 0
    max_consecutive_losses = 0
    for r in realized_r_values:
        if r is None:
            continue
        running += float(r)
        if running > peak:
            peak = running
        drawdown = peak - running
        if drawdown > max_drawdown_r:
            max_drawdown_r = drawdown
        if r < 0:
            consecutive_losses += 1
            if consecutive_losses > max_consecutive_losses:
                max_consecutive_losses = consecutive_losses
        else:
            consecutive_losses = 0
    return {
        "max_drawdown_r": round(max_drawdown_r, 4),
        "max_consecutive_losses": max_consecutive_losses,
    }


# ---------------------------------------------------------------------------
# Configurable evidence thresholds and tiny-live risk caps
# ---------------------------------------------------------------------------

@dataclass
class ORBLiveReadinessCriteria:
    """Conservative, configurable evidence thresholds for live readiness."""

    min_paper_trades_diagnostic: int = 10
    min_paper_trades_tiny_live: int = 50
    min_avg_r_after_costs: float = 0.1
    max_drawdown_r: float = 5.0
    max_consecutive_losses: int = 5
    max_avg_entry_slippage_bps: float = 15.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def promotion_criteria(self) -> PromotionCriteria:
        """Reuse the evidence-ledger promotion thresholds for paper->tiny-live."""
        return PromotionCriteria(
            min_trade_count=self.min_paper_trades_diagnostic,
            min_avg_r=0.0,
            tiny_live_min_trade_count=self.min_paper_trades_tiny_live,
            tiny_live_min_avg_r=self.min_avg_r_after_costs,
        )


@dataclass
class TinyLiveRiskCaps:
    """Tiny-live risk caps. Must always be strictly tighter than paper caps."""

    max_deployable_cash_pct: float = 0.005
    max_live_orb_trades_per_day: int = 1

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def validate(self, paper_max_trades_per_session: Optional[int] = None) -> List[str]:
        """Return a list of validation errors (empty means the caps are safe)."""
        errors: List[str] = []
        if not (0 < self.max_deployable_cash_pct <= MAX_TINY_LIVE_CASH_PCT):
            errors.append(
                "tiny-live max_deployable_cash_pct must be > 0 and <= "
                f"{MAX_TINY_LIVE_CASH_PCT} ({MAX_TINY_LIVE_CASH_PCT * 100:.0f}%)"
            )
        if self.max_live_orb_trades_per_day < 1:
            errors.append("tiny-live max_live_orb_trades_per_day must be >= 1")
        if self.max_live_orb_trades_per_day > 1:
            errors.append(
                "tiny-live max_live_orb_trades_per_day must be exactly 1 by default"
            )
        if (
            paper_max_trades_per_session is not None
            and self.max_live_orb_trades_per_day > paper_max_trades_per_session
        ):
            errors.append(
                "tiny-live max_live_orb_trades_per_day "
                f"({self.max_live_orb_trades_per_day}) must not exceed the paper "
                f"max_total_orb_trades_per_session ({paper_max_trades_per_session})"
            )
        return errors


# ---------------------------------------------------------------------------
# Readiness evaluation input
# ---------------------------------------------------------------------------

@dataclass
class ORBLiveReadinessInput:
    """All external facts a readiness evaluation needs.

    Kept broker/network free so this module stays deterministic and fully
    unit-testable: the caller (API layer) gathers these facts from the ORB
    session manager, evidence ledger, connected services, and live-runner
    config, then passes them in here.
    """

    strategy_name: str
    strategy_config: Dict[str, Any]
    paper_summary: Dict[str, Any]
    requested_mode: str = TINY_LIVE_CANDIDATE_MODE

    # Evidence beyond what paper_summary carries.
    max_drawdown_r: float = 0.0
    max_consecutive_losses: int = 0
    avg_entry_slippage_bps: Optional[float] = None
    unresolved_protection_failures: int = 0
    data_quality_failures: int = 0
    emergency_stop_incidents_from_orb: int = 0

    # Market data / connectivity.
    market_data_provider_healthy: bool = False
    market_data_source: str = "unknown"
    acceptable_market_data_sources: Sequence[str] = field(
        default_factory=lambda: DEFAULT_ACCEPTABLE_MARKET_DATA_SOURCES
    )
    broker_connected: bool = False
    broker_account_id: Optional[str] = None
    expected_account_id: Optional[str] = None

    # Master switches / operator confirmations.
    live_master_switch_enabled: bool = False
    emergency_stop_available: bool = True
    emergency_stop_tested: bool = False
    emergency_stop_currently_active: bool = False
    operator_confirmed_account: bool = False
    operator_confirmed_mode: bool = False

    # Risk caps, and paper session cap used to prove tiny-live caps are
    # strictly stricter than paper.
    tiny_live_caps: TinyLiveRiskCaps = field(default_factory=TinyLiveRiskCaps)
    paper_max_trades_per_session: Optional[int] = None


def _bool_check(key: str, label: str, passed: bool, reason: str) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "passed": bool(passed),
        "reasons": [] if passed else [reason],
    }


def evaluate_orb_live_readiness(
    data: ORBLiveReadinessInput,
    criteria: Optional[ORBLiveReadinessCriteria] = None,
    *,
    audit: Optional[AuditLogger] = None,
    log_dir: str = "logs",
) -> Dict[str, Any]:
    """Evaluate every tiny-live / assisted-live readiness gate.

    Returns a dict with an ``overall_status`` (one of
    :data:`ORBLiveReadinessStatus`), the full ``checklist`` (pass/fail with
    actionable reasons), and the evidence-driven ``paper_evidence_status``
    used to gate tiny-live candidacy. Never places or simulates an order.
    Always audit-logs the evaluation, regardless of outcome.
    """
    c = criteria or ORBLiveReadinessCriteria()
    cfg = data.strategy_config or {}
    params = cfg.get("parameters") or {}
    checklist: List[Dict[str, Any]] = []

    requested_mode = str(data.requested_mode or "")
    mode_supported = requested_mode in _SUPPORTED_MODES
    checklist.append(_bool_check(
        "requested_mode_supported", "Requested mode is tiny-live or assisted-live",
        mode_supported,
        f"unsupported requested_mode '{requested_mode}'; expected one of "
        f"{sorted(_SUPPORTED_MODES)}",
    ))

    config_valid = bool(cfg.get("name")) and bool(cfg.get("symbols"))
    checklist.append(_bool_check(
        "config_valid_and_persisted", "ORB config valid and persisted",
        config_valid, "ORB strategy config is missing or incomplete",
    ))

    promotion = classify_promotion(
        data.paper_summary, criteria=c.promotion_criteria(),
    )
    paper_evidence_ok = promotion["status"] == "TINY_LIVE_CANDIDATE"
    r_stats_ok = (
        data.max_drawdown_r <= c.max_drawdown_r
        and data.max_consecutive_losses <= c.max_consecutive_losses
    )
    slippage_ok = (
        data.avg_entry_slippage_bps is None
        or data.avg_entry_slippage_bps <= c.max_avg_entry_slippage_bps
    )
    evidence_reasons: List[str] = []
    if not paper_evidence_ok:
        evidence_reasons.extend(promotion.get("reasons") or [])
    if data.max_drawdown_r > c.max_drawdown_r:
        evidence_reasons.append(
            f"max_drawdown_r {data.max_drawdown_r} exceeds {c.max_drawdown_r}"
        )
    if data.max_consecutive_losses > c.max_consecutive_losses:
        evidence_reasons.append(
            f"max_consecutive_losses {data.max_consecutive_losses} exceeds "
            f"{c.max_consecutive_losses}"
        )
    if not slippage_ok:
        evidence_reasons.append(
            f"avg_entry_slippage_bps {data.avg_entry_slippage_bps} exceeds "
            f"{c.max_avg_entry_slippage_bps}"
        )
    checklist.append(_bool_check(
        "paper_evidence_meets_thresholds", "Paper evidence meets tiny-live thresholds",
        paper_evidence_ok and r_stats_ok and slippage_ok,
        "; ".join(evidence_reasons) or "paper evidence does not meet tiny-live thresholds",
    ))

    no_protection_failures = data.unresolved_protection_failures == 0
    checklist.append(_bool_check(
        "no_unresolved_protection_failures", "No unresolved protection failures",
        no_protection_failures,
        f"{data.unresolved_protection_failures} unresolved protection failure(s)",
    ))

    no_data_quality_failures = data.data_quality_failures == 0
    checklist.append(_bool_check(
        "no_repeated_data_quality_failures", "No repeated data-quality failures",
        no_data_quality_failures,
        f"{data.data_quality_failures} repeated data-quality failure(s)",
    ))

    no_emergency_incidents = data.emergency_stop_incidents_from_orb == 0
    checklist.append(_bool_check(
        "no_emergency_stop_incidents", "No emergency-stop incidents caused by ORB logic",
        no_emergency_incidents,
        f"{data.emergency_stop_incidents_from_orb} emergency-stop incident(s) caused by ORB logic",
    ))

    data_provider_healthy = data.market_data_provider_healthy
    checklist.append(_bool_check(
        "data_provider_healthy", "Paper/runtime data provider healthy",
        data_provider_healthy, "market-data provider is not healthy",
    ))

    acceptable_sources = {s.lower() for s in (data.acceptable_market_data_sources or ())}
    source_acceptable = str(data.market_data_source or "").lower() in acceptable_sources
    checklist.append(_bool_check(
        "market_data_source_acceptable", "Market-data source acceptable for live",
        source_acceptable,
        f"market_data_source '{data.market_data_source}' not in {sorted(acceptable_sources)}",
    ))

    account_present = bool(data.broker_connected and data.broker_account_id)
    account_matches = (
        not data.expected_account_id
        or (
            account_present
            and str(data.broker_account_id).strip().upper()
            == str(data.expected_account_id).strip().upper()
        )
    )
    broker_confirmed = account_present and account_matches
    checklist.append(_bool_check(
        "broker_connection_confirmed", "Broker connection/account confirmation present",
        broker_confirmed,
        "broker not connected or account id missing/mismatched",
    ))

    checklist.append(_bool_check(
        "live_master_switch_enabled", "Live trading master switch explicitly enabled",
        data.live_master_switch_enabled,
        "live trading master switch is disabled",
    ))

    cap_errors = data.tiny_live_caps.validate(data.paper_max_trades_per_session)
    checklist.append(_bool_check(
        "tiny_live_caps_valid", "Tiny-live caps set and stricter than paper caps",
        not cap_errors, "; ".join(cap_errors) or "tiny-live caps invalid",
    ))

    require_stop = bool(cfg.get("require_stop", False))
    require_target = bool(cfg.get("require_target", False))
    require_bracket = bool(cfg.get("require_bracket", False))
    protection_mandatory = require_stop and require_target and require_bracket
    checklist.append(_bool_check(
        "protection_mandatory", "Stop/target/bracket protection mandatory",
        protection_mandatory,
        "strategy config does not require stop, target, and bracket protection",
    ))

    emergency_stop_ready = data.emergency_stop_available and data.emergency_stop_tested
    checklist.append(_bool_check(
        "emergency_stop_tested_available", "Emergency stop tested / available",
        emergency_stop_ready,
        "emergency stop is unavailable or has not been tested",
    ))

    checklist.append(_bool_check(
        "emergency_stop_not_currently_active", "Emergency stop is not currently tripped",
        not data.emergency_stop_currently_active,
        "emergency stop is currently active; live readiness stays locked until cleared",
    ))

    long_only = not bool(params.get("short_enabled", False))
    checklist.append(_bool_check(
        "long_only", "Long-only (no short entries)",
        long_only, "strategy config enables short entries",
    ))

    model_c_disabled = not bool(params.get("model_c_enabled", False))
    checklist.append(_bool_check(
        "model_c_disabled", "Model C remains disabled",
        model_c_disabled, "strategy config enables Model C",
    ))

    account_confirmed = bool(data.operator_confirmed_account and data.operator_confirmed_mode)
    checklist.append(_bool_check(
        "operator_confirmation", "Operator confirms account id and mode",
        account_confirmed,
        "operator has not confirmed both the account id and the requested mode",
    ))

    if requested_mode == ASSISTED_LIVE_MODE:
        assisted_session_confirmed = account_confirmed and bool(data.expected_account_id)
        checklist.append(_bool_check(
            "assisted_live_session_confirmed",
            "Assisted-live account/session confirmation present",
            assisted_session_confirmed,
            "assisted-live requires an explicit expected_account_id plus operator confirmation",
        ))

    all_passed = all(item["passed"] for item in checklist)
    if not all_passed:
        overall_status = LOCKED
    elif requested_mode == ASSISTED_LIVE_MODE:
        overall_status = ASSISTED_LIVE_CANDIDATE
    else:
        overall_status = TINY_LIVE_CANDIDATE

    failing = [item["key"] for item in checklist if not item["passed"]]
    result = {
        "strategy_name": data.strategy_name,
        "requested_mode": requested_mode,
        "overall_status": overall_status,
        "live_trading_locked": overall_status == LOCKED,
        "paper_evidence_status": promotion["status"],
        "paper_evidence_reasons": promotion.get("reasons") or [],
        "checklist": checklist,
        "failing_gates": failing,
        "criteria": c.as_dict(),
        "tiny_live_caps": data.tiny_live_caps.as_dict(),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }

    audit_log = audit or AuditLogger(log_dir)
    audit_log.log_decision({
        "kind": _AUDIT_KIND,
        "action": "evaluate",
        "strategy": data.strategy_name,
        "requested_mode": requested_mode,
        "overall_status": overall_status,
        "failing_gates": failing,
    })

    return result


def log_operator_decision(
    strategy_name: str,
    decision: str,
    *,
    requested_mode: str = TINY_LIVE_CANDIDATE_MODE,
    operator: Optional[str] = None,
    notes: Optional[str] = None,
    audit: Optional[AuditLogger] = None,
    log_dir: str = "logs",
) -> None:
    """Audit-log an explicit operator decision on a live-readiness result.

    This never changes any live-trading switch itself; it only records that
    an operator reviewed and accepted/rejected a readiness result (e.g.
    confirming account id and mode before any future promotion step).
    """
    audit_log = audit or AuditLogger(log_dir)
    audit_log.log_decision({
        "kind": _AUDIT_KIND,
        "action": "operator_decision",
        "strategy": strategy_name,
        "requested_mode": requested_mode,
        "decision": decision,
        "operator": operator,
        "notes": notes,
    })
