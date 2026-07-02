"""ORB Phase 6 — human-confirmed tiny-live assisted execution (#229).

Turns a *validated Phase 5 assisted-live rehearsal package* into a real,
tiny-live protected broker order group — but only after an explicit final
human confirmation and only after every Phase 4 (#213) live-readiness gate
and every other live safety gate is re-checked immediately before submit.

This is the first ORB phase that may place a real broker order. It remains
tightly controlled:

- Not fully autonomous: there is no continuous loop here, and nothing in
  this module is ever invoked without an explicit operator HTTP request.
- No automatic promotion: a passing Phase 4 readiness result or a Phase 5
  rehearsal package never causes an order to be submitted by itself; the
  operator must supply a fresh, explicit ``confirm_live_order`` payload for
  every single submit call.
- The submitted order group must come from a valid, not-previously-submitted
  Phase 5 rehearsal package, built for a proposal that still belongs to the
  same strategy/session/symbol.
- Every gate below fails closed: any missing/invalid condition refuses the
  submit (raising :class:`ORBTinyLiveRefusal`) and the refusal is still
  audit-logged so it is always explainable after the fact.
- Raw market orders are impossible: only a marketable-limit entry with a
  mandatory stop and target/bracket leg can ever be represented, and the
  narrow :class:`~autonomous.orb_live_order_adapter.ORBLiveOrderAdapter`
  interface cannot express anything else.
- If the broker adapter cannot confirm broker-visible protection, the
  order group is cancelled immediately and the submit fails closed.
- Only long-side Model A/B setups are eligible. Model C, short entries, and
  non-equity instruments are always refused.
- Max live ORB trades per day defaults to 1 and tiny-live cash/risk caps
  from Phase 4 always apply.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from autonomous.audit import AuditLogger
from autonomous.orb_live_order_adapter import (
    ORBLiveBracketOrderRequest,
    ORBLiveOrderAdapter,
    ORBLiveOrderAdapterError,
)
from autonomous.orb_live_order_rehearsal import (
    ELIGIBLE_DIRECTION,
    ELIGIBLE_ENTRY_MODELS,
    ORDER_TYPE_LIMIT,
    ORBAssistedLiveRehearsalPackage,
)
from autonomous.orb_live_readiness import ASSISTED_LIVE_CANDIDATE
from autonomous.orb_proposals import ORBProposal, ProposalStatus

logger = logging.getLogger(__name__)

# Audit-log record kind for every tiny-live submit attempt (success or refusal).
_AUDIT_KIND = "orb_tiny_live_execution"

# The rehearsal must still be in this status; a rehearsal already submitted
# (or otherwise mutated away from dry-run) can never be submitted again.
_REHEARSAL_REQUIRED_STATUS = "DRY_RUN_ONLY"

DEFAULT_ACCEPTABLE_MARKET_DATA_SOURCES = ("ibkr",)

# Hard ceiling mirrored from autonomous.orb_live_readiness.MAX_TINY_LIVE_CASH_PCT
# so a caller can never bypass the tiny-live cash cap by supplying a larger cap.
MAX_TINY_LIVE_CASH_PCT = 0.01


class ORBTinyLiveRefusalReason(str, Enum):
    """Why a tiny-live submit attempt was refused (fail closed)."""

    REHEARSAL_MISSING = "rehearsal_missing"
    REHEARSAL_NOT_DRY_RUN = "rehearsal_not_dry_run"
    REHEARSAL_ALREADY_SUBMITTED = "rehearsal_already_submitted"
    PROPOSAL_MISSING = "proposal_missing"
    PROPOSAL_MISMATCH = "proposal_mismatch"
    PROPOSAL_NOT_EXECUTABLE = "proposal_not_executable"
    READINESS_NOT_PASSED = "readiness_not_passed"
    LIVE_MASTER_SWITCH_DISABLED = "live_master_switch_disabled"
    EMERGENCY_STOP_ACTIVE = "emergency_stop_active"
    ACCOUNT_MISMATCH = "account_mismatch"
    OPERATOR_CONFIRMATION_MISSING = "operator_confirmation_missing"
    MARKET_DATA_UNACCEPTABLE = "market_data_unacceptable"
    DAILY_CAP_REACHED = "daily_cap_reached"
    RISK_CAP_EXCEEDED = "risk_cap_exceeded"
    RISK_CAP_UNVERIFIABLE = "risk_cap_unverifiable"
    RAW_MARKET_ORDER = "raw_market_order"
    MISSING_STOP = "missing_stop"
    MISSING_TARGET = "missing_target"
    PROTECTION_UNREPRESENTABLE = "protection_unrepresentable"
    SHORT_DIRECTION = "short_direction"
    MODEL_C_DISABLED = "model_c_disabled"
    UNKNOWN_MODEL = "unknown_model"
    NON_EQUITY = "non_equity"
    PROTECTION_NOT_BROKER_VISIBLE = "protection_not_broker_visible"
    BROKER_SUBMIT_FAILED = "broker_submit_failed"


class ORBTinyLiveExecutionError(RuntimeError):
    """Raised when a tiny-live order group cannot be submitted."""


class ORBTinyLiveRefusal(ORBTinyLiveExecutionError):
    """Raised when a safety gate refuses a tiny-live submit attempt.

    Carries the structured :class:`ORBTinyLiveRefusalReason` so callers
    (API, dashboard) can render exactly which gate stopped the submit.
    """

    def __init__(self, reason: ORBTinyLiveRefusalReason, message: str) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass
class ORBTinyLiveOrderGroup:
    """A submitted tiny-live protected long bracket/OCA order group."""

    order_group_id: str
    rehearsal_id: str
    proposal_id: str
    strategy_name: str
    session_date: str
    symbol: str
    account_id: str
    entry_model: str
    direction: str
    quantity: int
    entry_order_type: str
    entry_limit_price: float
    stop_price: float
    target_price: float
    oca_group: str
    time_in_force: str
    entry_broker_order_id: str
    stop_broker_order_id: str
    target_broker_order_id: str
    protection_broker_visible: bool
    readiness_snapshot: Dict[str, Any]
    operator_confirmation: Dict[str, Any]
    audit_event_id: str
    created_at: str
    status: str = "SUBMITTED"
    mode: str = "TINY_LIVE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _refusal_from_broker_error(exc: Exception) -> ORBTinyLiveRefusalReason:
    if isinstance(exc, ORBLiveOrderAdapterError):
        return ORBTinyLiveRefusalReason.BROKER_SUBMIT_FAILED
    return ORBTinyLiveRefusalReason.BROKER_SUBMIT_FAILED


def submit_tiny_live_order(
    rehearsal: Optional[ORBAssistedLiveRehearsalPackage],
    proposal: Optional[ORBProposal],
    readiness_result: Optional[Dict[str, Any]],
    *,
    confirm_live_order: bool,
    operator: Optional[str],
    expected_account_id: Optional[str],
    account_id: Optional[str],
    notes: Optional[str] = None,
    live_master_switch_enabled: bool,
    emergency_stop_active: bool,
    market_data_source: Optional[str],
    acceptable_market_data_sources: Sequence[str] = DEFAULT_ACCEPTABLE_MARKET_DATA_SOURCES,
    daily_live_orb_trade_count: int = 0,
    max_live_orb_trades_per_day: int = 1,
    account_equity: Optional[float] = None,
    max_deployable_cash_pct: float = MAX_TINY_LIVE_CASH_PCT,
    asset_class: str = "EQUITY",
    adapter: ORBLiveOrderAdapter,
    already_submitted: bool = False,
    audit: Optional[AuditLogger] = None,
    log_dir: str = "logs",
    now_fn: Optional[Callable[[], datetime]] = None,
) -> ORBTinyLiveOrderGroup:
    """Submit a validated Phase 5 rehearsal package as a tiny-live order group.

    Re-checks Phase 4 readiness and every other live safety gate immediately
    before submit. Raises :class:`ORBTinyLiveRefusal` (fail closed) on any
    missing/invalid gate; the refusal is still audit-logged. Only calls the
    broker adapter once every gate has passed, and cancels the order group
    immediately if the adapter cannot confirm broker-visible protection.
    """
    audit_log = audit or AuditLogger(log_dir)
    now = now_fn or (lambda: datetime.now(timezone.utc))

    def _refuse(reason: ORBTinyLiveRefusalReason, message: str) -> None:
        _log_refusal(audit_log, rehearsal, proposal, reason, message)
        raise ORBTinyLiveRefusal(reason, message)

    if rehearsal is None:
        _refuse(
            ORBTinyLiveRefusalReason.REHEARSAL_MISSING,
            "no assisted-live rehearsal package was supplied; tiny-live submit "
            "requires a valid Phase 5 rehearsal package",
        )

    if rehearsal.status != _REHEARSAL_REQUIRED_STATUS:
        _refuse(
            ORBTinyLiveRefusalReason.REHEARSAL_NOT_DRY_RUN,
            f"rehearsal '{rehearsal.rehearsal_id}' is '{rehearsal.status}', not "
            f"'{_REHEARSAL_REQUIRED_STATUS}'",
        )

    if already_submitted:
        _refuse(
            ORBTinyLiveRefusalReason.REHEARSAL_ALREADY_SUBMITTED,
            f"rehearsal '{rehearsal.rehearsal_id}' has already been submitted "
            "as a tiny-live order group",
        )

    if proposal is None:
        _refuse(
            ORBTinyLiveRefusalReason.PROPOSAL_MISSING,
            f"no proposal '{rehearsal.proposal_id}' was found for rehearsal "
            f"'{rehearsal.rehearsal_id}'",
        )

    if (
        proposal.proposal_id != rehearsal.proposal_id
        or proposal.strategy_name != rehearsal.strategy_name
        or proposal.session_date != rehearsal.session_date
        or proposal.symbol != rehearsal.symbol
    ):
        _refuse(
            ORBTinyLiveRefusalReason.PROPOSAL_MISMATCH,
            "proposal no longer matches the rehearsal's strategy/session/symbol/id",
        )

    if proposal.status != ProposalStatus.PENDING.value:
        _refuse(
            ORBTinyLiveRefusalReason.PROPOSAL_NOT_EXECUTABLE,
            f"proposal '{proposal.proposal_id}' is '{proposal.status}', not PENDING",
        )

    overall_status = (readiness_result or {}).get("overall_status")
    if overall_status != ASSISTED_LIVE_CANDIDATE:
        _refuse(
            ORBTinyLiveRefusalReason.READINESS_NOT_PASSED,
            "Phase 4 live-readiness has not passed assisted-live "
            f"(overall_status={overall_status!r}); tiny-live submit is locked",
        )

    if not live_master_switch_enabled:
        _refuse(
            ORBTinyLiveRefusalReason.LIVE_MASTER_SWITCH_DISABLED,
            "live trading master switch is disabled; tiny-live submit requires "
            "it to be explicitly enabled",
        )

    if emergency_stop_active:
        _refuse(
            ORBTinyLiveRefusalReason.EMERGENCY_STOP_ACTIVE,
            "emergency stop is currently active; tiny-live submit is blocked",
        )

    account_id_norm = str(account_id or "").strip()
    expected_account_id_norm = str(expected_account_id or "").strip()
    if (
        not account_id_norm
        or not expected_account_id_norm
        or account_id_norm.upper() != expected_account_id_norm.upper()
    ):
        _refuse(
            ORBTinyLiveRefusalReason.ACCOUNT_MISMATCH,
            f"account id {account_id_norm!r} does not match expected "
            f"{expected_account_id_norm!r} (or either is missing)",
        )

    if not confirm_live_order or not str(operator or "").strip():
        _refuse(
            ORBTinyLiveRefusalReason.OPERATOR_CONFIRMATION_MISSING,
            "operator has not supplied a fresh, explicit final confirmation "
            "(confirm_live_order=true and a named operator are both required)",
        )

    acceptable_sources = {s.lower() for s in (acceptable_market_data_sources or ())}
    if str(market_data_source or "").lower() not in acceptable_sources:
        _refuse(
            ORBTinyLiveRefusalReason.MARKET_DATA_UNACCEPTABLE,
            f"market_data_source '{market_data_source}' is not in "
            f"{sorted(acceptable_sources)}; tiny-live submit requires an "
            "acceptable, healthy live market-data source",
        )

    if daily_live_orb_trade_count >= max_live_orb_trades_per_day:
        _refuse(
            ORBTinyLiveRefusalReason.DAILY_CAP_REACHED,
            f"daily live ORB trade cap of {max_live_orb_trades_per_day} already "
            f"reached ({daily_live_orb_trade_count} submitted today)",
        )

    if asset_class.upper() != "EQUITY":
        _refuse(
            ORBTinyLiveRefusalReason.NON_EQUITY,
            f"asset_class '{asset_class}' is not eligible; only EQUITY "
            "instruments are supported for tiny-live ORB submit",
        )

    if rehearsal.direction != ELIGIBLE_DIRECTION:
        _refuse(
            ORBTinyLiveRefusalReason.SHORT_DIRECTION,
            f"direction '{rehearsal.direction}' is not eligible; only LONG is "
            "supported for tiny-live submit",
        )

    if rehearsal.entry_model not in ELIGIBLE_ENTRY_MODELS:
        _refuse(
            ORBTinyLiveRefusalReason.MODEL_C_DISABLED
            if "MODEL_C" in rehearsal.entry_model
            else ORBTinyLiveRefusalReason.UNKNOWN_MODEL,
            f"entry model '{rehearsal.entry_model}' is not eligible for "
            f"tiny-live submit; only {ELIGIBLE_ENTRY_MODELS} are supported",
        )

    if rehearsal.entry_order_type != ORDER_TYPE_LIMIT:
        _refuse(
            ORBTinyLiveRefusalReason.RAW_MARKET_ORDER,
            f"rehearsal entry_order_type must be {ORDER_TYPE_LIMIT}; a raw "
            "market order can never be submitted",
        )

    if not rehearsal.stop_price or rehearsal.stop_price <= 0:
        _refuse(
            ORBTinyLiveRefusalReason.MISSING_STOP,
            "rehearsal is missing a positive stop price; stop protection is mandatory",
        )

    if not rehearsal.target_price or rehearsal.target_price <= 0:
        _refuse(
            ORBTinyLiveRefusalReason.MISSING_TARGET,
            "rehearsal is missing a positive target price; a target is mandatory",
        )

    if not (rehearsal.stop_price < rehearsal.entry_limit_price < rehearsal.target_price):
        _refuse(
            ORBTinyLiveRefusalReason.PROTECTION_UNREPRESENTABLE,
            "stop/entry/target prices do not form a valid long bracket "
            "(stop < entry < target)",
        )

    bracket = rehearsal.bracket
    if bracket is None or not getattr(bracket, "oca_group", None):
        _refuse(
            ORBTinyLiveRefusalReason.PROTECTION_UNREPRESENTABLE,
            "rehearsal has no representable bracket/OCA protection metadata",
        )

    if account_equity is None or account_equity <= 0:
        _refuse(
            ORBTinyLiveRefusalReason.RISK_CAP_UNVERIFIABLE,
            "account equity is unavailable; the tiny-live cash/risk cap cannot "
            "be verified so submit is refused",
        )

    if max_deployable_cash_pct <= 0 or max_deployable_cash_pct > MAX_TINY_LIVE_CASH_PCT:
        _refuse(
            ORBTinyLiveRefusalReason.RISK_CAP_UNVERIFIABLE,
            f"max_deployable_cash_pct {max_deployable_cash_pct!r} is not a valid "
            f"tiny-live cap (must be in (0, {MAX_TINY_LIVE_CASH_PCT}])",
        )

    position_value = rehearsal.quantity * rehearsal.entry_limit_price
    cash_cap = account_equity * max_deployable_cash_pct
    if position_value > cash_cap:
        _refuse(
            ORBTinyLiveRefusalReason.RISK_CAP_EXCEEDED,
            f"position value {position_value:.2f} exceeds tiny-live cash cap "
            f"{cash_cap:.2f} ({max_deployable_cash_pct * 100:.2f}% of "
            f"{account_equity:.2f})",
        )

    order_group_id = uuid.uuid4().hex
    request = ORBLiveBracketOrderRequest(
        order_group_id=order_group_id,
        symbol=rehearsal.symbol,
        account_id=account_id_norm,
        quantity=int(rehearsal.quantity),
        entry_order_type=rehearsal.entry_order_type,
        entry_limit_price=rehearsal.entry_limit_price,
        stop_price=rehearsal.stop_price,
        target_price=rehearsal.target_price,
        oca_group=bracket.oca_group,
        time_in_force=rehearsal.time_in_force,
    )

    operator_confirmation = {
        "confirm_live_order": bool(confirm_live_order),
        "operator": operator,
        "notes": notes,
        "account_id": account_id_norm,
        "expected_account_id": expected_account_id_norm,
        "confirmed_at": now().isoformat(),
    }

    try:
        submission = adapter.submit_protected_long_bracket(request)
    except Exception as exc:  # noqa: BLE001 - any broker error fails closed
        _refuse(
            _refusal_from_broker_error(exc),
            f"broker adapter failed to submit the protected order group: {exc}",
        )
        raise  # pragma: no cover - _refuse always raises

    if not submission.protection_broker_visible:
        try:
            adapter.cancel_if_pending(order_group_id)
        except Exception:  # noqa: BLE001 - never let a cancel failure mask the refusal
            logger.exception(
                "Failed to cancel tiny-live order group %s after unconfirmed "
                "protection", order_group_id,
            )
        _refuse(
            ORBTinyLiveRefusalReason.PROTECTION_NOT_BROKER_VISIBLE,
            f"broker adapter could not confirm broker-visible protection for "
            f"order group '{order_group_id}'; the order group was cancelled",
        )

    audit_event_id = uuid.uuid4().hex
    group = ORBTinyLiveOrderGroup(
        order_group_id=order_group_id,
        rehearsal_id=rehearsal.rehearsal_id,
        proposal_id=proposal.proposal_id,
        strategy_name=proposal.strategy_name,
        session_date=proposal.session_date,
        symbol=proposal.symbol,
        account_id=account_id_norm,
        entry_model=rehearsal.entry_model,
        direction=rehearsal.direction,
        quantity=int(rehearsal.quantity),
        entry_order_type=rehearsal.entry_order_type,
        entry_limit_price=rehearsal.entry_limit_price,
        stop_price=rehearsal.stop_price,
        target_price=rehearsal.target_price,
        oca_group=bracket.oca_group,
        time_in_force=rehearsal.time_in_force,
        entry_broker_order_id=submission.entry_broker_order_id,
        stop_broker_order_id=submission.stop_broker_order_id,
        target_broker_order_id=submission.target_broker_order_id,
        protection_broker_visible=submission.protection_broker_visible,
        readiness_snapshot=dict(readiness_result or {}),
        operator_confirmation=operator_confirmation,
        audit_event_id=audit_event_id,
        created_at=now().isoformat(),
    )

    audit_log.log_decision({
        "kind": _AUDIT_KIND,
        "action": "tiny_live_order_submitted",
        "audit_event_id": audit_event_id,
        "order_group_id": order_group_id,
        "rehearsal_id": rehearsal.rehearsal_id,
        "proposal_id": proposal.proposal_id,
        "strategy": proposal.strategy_name,
        "session_date": proposal.session_date,
        "symbol": proposal.symbol,
        "account_id": account_id_norm,
        "entry_model": rehearsal.entry_model,
        "direction": rehearsal.direction,
        "quantity": group.quantity,
        "entry_order_type": group.entry_order_type,
        "entry_limit_price": group.entry_limit_price,
        "stop_price": group.stop_price,
        "target_price": group.target_price,
        "entry_broker_order_id": group.entry_broker_order_id,
        "stop_broker_order_id": group.stop_broker_order_id,
        "target_broker_order_id": group.target_broker_order_id,
        "protection_broker_visible": group.protection_broker_visible,
        "readiness_overall_status": overall_status,
        "operator_confirmation": operator_confirmation,
    })

    return group


def _log_refusal(
    audit_log: AuditLogger,
    rehearsal: Optional[ORBAssistedLiveRehearsalPackage],
    proposal: Optional[ORBProposal],
    reason: ORBTinyLiveRefusalReason,
    message: str,
) -> None:
    audit_log.log_decision({
        "kind": _AUDIT_KIND,
        "action": "tiny_live_order_refused",
        "reason": reason.value,
        "message": message,
        "rehearsal_id": getattr(rehearsal, "rehearsal_id", None),
        "proposal_id": getattr(proposal, "proposal_id", None) or getattr(rehearsal, "proposal_id", None),
        "strategy": getattr(proposal, "strategy_name", None) or getattr(rehearsal, "strategy_name", None),
        "symbol": getattr(proposal, "symbol", None) or getattr(rehearsal, "symbol", None),
        "session_date": getattr(proposal, "session_date", None) or getattr(rehearsal, "session_date", None),
    })


class ORBTinyLiveOrderStore:
    """Thread-safe in-memory store of submitted tiny-live order groups.

    Also tracks which rehearsal ids have already been submitted (so a
    rehearsal can never be submitted twice) and the daily submitted-order
    count per strategy/session (so the daily live ORB trade cap can be
    enforced). Order groups only ever reach this store via
    :func:`submit_tiny_live_order`, which enforces every safety gate and
    audit-logs both success and refusal before a group ever reaches here.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._groups: Dict[str, ORBTinyLiveOrderGroup] = {}
        self._by_rehearsal: Dict[str, str] = {}

    def is_rehearsal_submitted(self, rehearsal_id: str) -> bool:
        with self._lock:
            return rehearsal_id in self._by_rehearsal

    def add(self, group: ORBTinyLiveOrderGroup) -> ORBTinyLiveOrderGroup:
        with self._lock:
            self._groups[group.order_group_id] = group
            self._by_rehearsal[group.rehearsal_id] = group.order_group_id
        return group

    def get(self, order_group_id: str) -> Optional[ORBTinyLiveOrderGroup]:
        with self._lock:
            return self._groups.get(order_group_id)

    def list(
        self,
        *,
        strategy_name: Optional[str] = None,
        symbol: Optional[str] = None,
        session_date: Optional[str] = None,
    ) -> List[ORBTinyLiveOrderGroup]:
        with self._lock:
            items = list(self._groups.values())
        if strategy_name:
            items = [g for g in items if g.strategy_name == strategy_name]
        if symbol:
            sym = symbol.upper()
            items = [g for g in items if g.symbol.upper() == sym]
        if session_date:
            items = [g for g in items if g.session_date == session_date]
        return sorted(items, key=lambda g: g.created_at)

    def daily_count(self, strategy_name: str, session_date: str) -> int:
        """Number of tiny-live order groups already submitted for this session."""
        with self._lock:
            return sum(
                1 for g in self._groups.values()
                if g.strategy_name == strategy_name and g.session_date == session_date
            )

    def mark_cancelled(self, order_group_id: str) -> Optional[ORBTinyLiveOrderGroup]:
        with self._lock:
            group = self._groups.get(order_group_id)
            if group is not None:
                group.status = "CANCELLED"
            return group
