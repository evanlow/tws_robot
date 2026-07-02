"""ORB Phase 5 — assisted-live protected order-path rehearsal (#227).

Turns a *valid* ORB proposal into the exact broker-visible protected order
package (entry + stop + target/bracket) that assisted-live would submit —
without ever placing, routing, or simulating an order. This module is
rehearsal/dry-run only: it never calls a live order-submission API, never
calls IBKR ``placeOrder``, never flips the live master switch, and never
starts a continuous live loop.

Safety posture (Prime Directive):
- Live remains disabled by default. Building a rehearsal package never
  enables live trading and never sends an order by itself.
- Assisted-live requires the Phase 4 (#213) live-readiness result to be
  ``ASSISTED_LIVE_CANDIDATE`` *and* the live master switch to be explicitly
  enabled *and* an explicit operator confirmation for this session/account/
  mode. Any one missing fails closed.
- Only long-side Model A/B setups are eligible. Model C, short entries,
  and unknown models are always refused.
- Raw market orders are impossible: the entry must be ``LIMIT``
  (marketable-limit) and both a stop and a target are mandatory. If
  broker-visible bracket/OCA protection cannot be represented, the package
  is refused (fail closed) rather than represented without protection.
- The proposal's account, symbol, session, and evidence must be present and
  must match the confirmed account id; a stale/expired/already-executed
  proposal is always refused.
- Every rehearsal build attempt (success or refusal) is written to the
  autonomous audit log so the rehearsal path is fully reconstructable.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from autonomous.audit import AuditLogger
from autonomous.orb_live_readiness import ASSISTED_LIVE_CANDIDATE
from autonomous.orb_proposals import (
    ORDER_TYPE_LIMIT,
    ORBProposal,
    ProposalError,
    ProposalStatus,
    _validate_proposal,
)

logger = logging.getLogger(__name__)

# Audit-log record kind for every assisted-live rehearsal build attempt.
_AUDIT_KIND = "orb_assisted_live_rehearsal"

# The only entry models eligible for assisted-live rehearsal. Model C stays
# disabled here regardless of any strategy-config override.
ELIGIBLE_ENTRY_MODELS = ("MODEL_A_DISPLACEMENT_GAP", "MODEL_B_BREAK_RETEST")
DISABLED_ENTRY_MODEL = "MODEL_C_REVERSAL"

# Direction eligible for assisted-live rehearsal. Short entries are always
# refused in this phase.
ELIGIBLE_DIRECTION = "LONG"

# Order types this module may ever represent. A raw market order can never
# be constructed here.
ORDER_TYPE_STOP = "STOP"

DEFAULT_TIME_IN_FORCE = "DAY"


class ORBAssistedLiveRefusalReason(str, Enum):
    """Why an assisted-live rehearsal package was refused (fail closed)."""

    PROPOSAL_MISSING = "proposal_missing"
    PROPOSAL_NOT_EXECUTABLE = "proposal_not_executable"
    READINESS_NOT_PASSED = "readiness_not_passed"
    LIVE_MASTER_SWITCH_DISABLED = "live_master_switch_disabled"
    OPERATOR_CONFIRMATION_MISSING = "operator_confirmation_missing"
    ACCOUNT_MISMATCH = "account_mismatch"
    SHORT_DIRECTION = "short_direction"
    MODEL_C_DISABLED = "model_c_disabled"
    UNKNOWN_MODEL = "unknown_model"
    RAW_MARKET_ORDER = "raw_market_order"
    MISSING_STOP = "missing_stop"
    MISSING_TARGET = "missing_target"
    PROTECTION_UNREPRESENTABLE = "protection_unrepresentable"
    INCOMPLETE_EVIDENCE = "incomplete_evidence"


class ORBAssistedLiveRehearsalError(RuntimeError):
    """Raised when an assisted-live rehearsal package cannot be built."""


class ORBAssistedLiveRefusal(ORBAssistedLiveRehearsalError):
    """Raised when a safety gate refuses to build the rehearsal package.

    Carries the structured :class:`ORBAssistedLiveRefusalReason` so callers
    (API, dashboard) can render exactly which gate stopped the rehearsal.
    """

    def __init__(self, reason: ORBAssistedLiveRefusalReason, message: str) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass
class ORBAssistedLiveBracketMetadata:
    """Broker-visible bracket/OCA protection metadata for the rehearsal package.

    Represents the *intended* protective order shape only; nothing here is
    ever submitted to a broker. ``entry_order_type`` is always ``LIMIT`` and
    ``stop_order_type`` is always ``STOP`` — a raw market order can never be
    represented.
    """

    protection_type: str = "BRACKET"
    oca_group: str = ""
    entry_order_type: str = ORDER_TYPE_LIMIT
    stop_order_type: str = ORDER_TYPE_STOP
    target_order_type: str = ORDER_TYPE_LIMIT
    entry_action: str = "BUY"
    stop_action: str = "SELL"
    target_action: str = "SELL"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ORBAssistedLiveRehearsalPackage:
    """The exact broker-visible protected order package assisted-live would
    submit for a valid ORB proposal — rehearsal/dry-run only, never placed.
    """

    rehearsal_id: str
    strategy_name: str
    session_date: str
    symbol: str
    account_id: str
    proposal_id: str
    entry_model: str
    direction: str
    quantity: int
    entry_order_type: str
    entry_limit_price: float
    stop_price: float
    target_price: float
    bracket: ORBAssistedLiveBracketMetadata
    time_in_force: str
    readiness_snapshot: Dict[str, Any]
    operator_confirmation_snapshot: Dict[str, Any]
    audit_event_id: str
    created_at: str
    mode: str = "REHEARSAL"
    status: str = "DRY_RUN_ONLY"
    evidence_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["bracket"] = self.bracket.to_dict()
        return out


def _entry_model_reason(entry_model: str) -> ORBAssistedLiveRefusalReason:
    if entry_model == DISABLED_ENTRY_MODEL:
        return ORBAssistedLiveRefusalReason.MODEL_C_DISABLED
    return ORBAssistedLiveRefusalReason.UNKNOWN_MODEL


def build_assisted_live_rehearsal_package(
    proposal: Optional[ORBProposal],
    readiness_result: Optional[Dict[str, Any]],
    *,
    account_id: Optional[str],
    expected_account_id: Optional[str],
    operator_confirmed: bool,
    live_master_switch_enabled: bool,
    evidence_id: Optional[str] = None,
    time_in_force: str = DEFAULT_TIME_IN_FORCE,
    rehearsal_id: Optional[str] = None,
    audit: Optional[AuditLogger] = None,
    log_dir: str = "logs",
    now_fn: Optional[Callable[[], datetime]] = None,
) -> ORBAssistedLiveRehearsalPackage:
    """Build the assisted-live rehearsal order package for a valid proposal.

    This never places, routes, or simulates an order — it only constructs and
    audit-logs the exact broker-visible protected order package (entry, stop,
    target, bracket/OCA metadata) that assisted-live *would* submit once a
    human explicitly confirms it. Every safety condition below fails closed:
    any one missing or invalid raises :class:`ORBAssistedLiveRefusal` and the
    refusal is still audit-logged so it can be explained after the fact.
    """
    audit_log = audit or AuditLogger(log_dir)
    now = now_fn or (lambda: datetime.now(timezone.utc))

    def _refuse(reason: ORBAssistedLiveRefusalReason, message: str) -> None:
        _log_refusal(audit_log, proposal, reason, message)
        raise ORBAssistedLiveRefusal(reason, message)

    if proposal is None:
        _refuse(
            ORBAssistedLiveRefusalReason.PROPOSAL_MISSING,
            "no ORB proposal was supplied; a rehearsal package requires a valid proposal",
        )
    try:
        # A stale/expired/already-executed proposal (or any other unsafe/invalid
        # proposal) can never be turned into a rehearsal package.
        if proposal.status != ProposalStatus.PENDING.value:
            _refuse(
                ORBAssistedLiveRefusalReason.PROPOSAL_NOT_EXECUTABLE,
                f"proposal '{proposal.proposal_id}' is '{proposal.status}', not PENDING "
                "(stale, expired, skipped, or already executed)",
            )

        if not proposal.stop_price or proposal.stop_price <= 0:
            _refuse(
                ORBAssistedLiveRefusalReason.MISSING_STOP,
                "proposal is missing a positive stop price; stop protection is mandatory",
            )

        if not proposal.target_price or proposal.target_price <= 0:
            _refuse(
                ORBAssistedLiveRefusalReason.MISSING_TARGET,
                "proposal is missing a positive target price; a target is mandatory",
            )

        overall_status = (readiness_result or {}).get("overall_status")
        if overall_status != ASSISTED_LIVE_CANDIDATE:
            _refuse(
                ORBAssistedLiveRefusalReason.READINESS_NOT_PASSED,
                "Phase 4 live-readiness has not passed assisted-live "
                f"(overall_status={overall_status!r}); assisted-live rehearsal is locked",
            )

        if not live_master_switch_enabled:
            _refuse(
                ORBAssistedLiveRefusalReason.LIVE_MASTER_SWITCH_DISABLED,
                "live trading master switch is disabled; assisted-live rehearsal requires "
                "it to be explicitly enabled",
            )

        if not operator_confirmed:
            _refuse(
                ORBAssistedLiveRefusalReason.OPERATOR_CONFIRMATION_MISSING,
                "operator has not explicitly confirmed this session/account/mode",
            )

        account_id_norm = str(account_id or "").strip()
        expected_account_id_norm = str(expected_account_id or "").strip()
        if (
            not account_id_norm
            or not expected_account_id_norm
            or account_id_norm.upper() != expected_account_id_norm.upper()
        ):
            _refuse(
                ORBAssistedLiveRefusalReason.ACCOUNT_MISMATCH,
                f"account id {account_id_norm!r} does not match expected "
                f"{expected_account_id_norm!r} (or either is missing)",
            )

        if proposal.direction != ELIGIBLE_DIRECTION:
            _refuse(
                ORBAssistedLiveRefusalReason.SHORT_DIRECTION,
                f"direction '{proposal.direction}' is not eligible; only LONG is "
                "supported for assisted-live rehearsal",
            )

        if proposal.entry_model not in ELIGIBLE_ENTRY_MODELS:
            _refuse(
                _entry_model_reason(proposal.entry_model),
                f"entry model '{proposal.entry_model}' is not eligible for assisted-live "
                f"rehearsal; only {ELIGIBLE_ENTRY_MODELS} are supported",
            )

        if proposal.order_type != ORDER_TYPE_LIMIT:
            _refuse(
                ORBAssistedLiveRefusalReason.RAW_MARKET_ORDER,
                f"proposal order_type must be {ORDER_TYPE_LIMIT}; a raw market order "
                "can never be represented",
            )

        if not proposal.symbol or not proposal.session_date or not proposal.strategy_name:
            _refuse(
                ORBAssistedLiveRefusalReason.INCOMPLETE_EVIDENCE,
                "proposal is missing symbol, session date, or strategy name",
            )

        quantity = int(proposal.quantity)
        if quantity <= 0:
            _refuse(
                ORBAssistedLiveRefusalReason.PROTECTION_UNREPRESENTABLE,
                "proposal has zero/invalid quantity; a bracket cannot be sized/represented",
            )
        if not (proposal.stop_price < proposal.entry_price < proposal.target_price):
            _refuse(
                ORBAssistedLiveRefusalReason.PROTECTION_UNREPRESENTABLE,
                "stop/entry/target prices do not form a valid long bracket "
                "(stop < entry < target)",
            )

        # Final safety net: re-validate every other invariant a valid, safe,
        # recommend-only proposal must uphold before any bracket is represented.
        try:
            _validate_proposal(proposal)
        except ProposalError as exc:
            _refuse(
                ORBAssistedLiveRefusalReason.PROTECTION_UNREPRESENTABLE,
                f"proposal fails safety validation, protection cannot be represented: {exc}",
            )

        rid = rehearsal_id or uuid.uuid4().hex
        audit_event_id = uuid.uuid4().hex
        bracket = ORBAssistedLiveBracketMetadata(oca_group=f"ORB-OCA-{rid}")

        package = ORBAssistedLiveRehearsalPackage(
            rehearsal_id=rid,
            strategy_name=proposal.strategy_name,
            session_date=proposal.session_date,
            symbol=proposal.symbol,
            account_id=account_id_norm,
            proposal_id=proposal.proposal_id,
            entry_model=proposal.entry_model,
            direction=proposal.direction,
            quantity=quantity,
            entry_order_type=ORDER_TYPE_LIMIT,
            entry_limit_price=proposal.entry_price,
            stop_price=proposal.stop_price,
            target_price=proposal.target_price,
            bracket=bracket,
            time_in_force=time_in_force,
            readiness_snapshot=dict(readiness_result or {}),
            operator_confirmation_snapshot={
                "operator_confirmed": operator_confirmed,
                "account_id": account_id_norm,
                "expected_account_id": expected_account_id_norm,
            },
            audit_event_id=audit_event_id,
            created_at=now().isoformat(),
            evidence_id=evidence_id,
        )

        audit_log.log_decision({
            "kind": _AUDIT_KIND,
            "action": "rehearsal_created",
            "audit_event_id": audit_event_id,
            "rehearsal_id": rid,
            "proposal_id": proposal.proposal_id,
            "strategy": proposal.strategy_name,
            "session_date": proposal.session_date,
            "symbol": proposal.symbol,
            "account_id": account_id_norm,
            "entry_model": proposal.entry_model,
            "direction": proposal.direction,
            "quantity": package.quantity,
            "entry_order_type": package.entry_order_type,
            "entry_limit_price": package.entry_limit_price,
            "stop_price": package.stop_price,
            "target_price": package.target_price,
            "bracket": bracket.to_dict(),
            "time_in_force": time_in_force,
            "evidence_id": evidence_id,
            "readiness_overall_status": overall_status,
        })

        return package
    except ORBAssistedLiveRefusal:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        _refuse(
            ORBAssistedLiveRefusalReason.PROTECTION_UNREPRESENTABLE,
            "proposal has invalid or unexpected field values; protection cannot be "
            f"represented: {exc}",
        )


def _log_refusal(
    audit_log: AuditLogger,
    proposal: Optional[ORBProposal],
    reason: ORBAssistedLiveRefusalReason,
    message: str,
) -> None:
    audit_log.log_decision({
        "kind": _AUDIT_KIND,
        "action": "rehearsal_refused",
        "reason": reason.value,
        "message": message,
        "proposal_id": getattr(proposal, "proposal_id", None),
        "strategy": getattr(proposal, "strategy_name", None),
        "symbol": getattr(proposal, "symbol", None),
        "session_date": getattr(proposal, "session_date", None),
    })


class ORBAssistedLiveRehearsalStore:
    """In-memory store of assisted-live rehearsal packages.

    Thread-safe. Rehearsal packages are only ever created via
    :func:`build_assisted_live_rehearsal_package`, which enforces every
    safety gate and audit-logs both success and refusal before a package
    ever reaches this store. This store never places or simulates an order.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._packages: Dict[str, ORBAssistedLiveRehearsalPackage] = {}

    def add(self, package: ORBAssistedLiveRehearsalPackage) -> ORBAssistedLiveRehearsalPackage:
        with self._lock:
            self._packages[package.rehearsal_id] = package
        return package

    def get(self, rehearsal_id: str) -> Optional[ORBAssistedLiveRehearsalPackage]:
        with self._lock:
            return self._packages.get(rehearsal_id)

    def list(
        self,
        *,
        strategy_name: Optional[str] = None,
        symbol: Optional[str] = None,
        proposal_id: Optional[str] = None,
    ) -> List[ORBAssistedLiveRehearsalPackage]:
        with self._lock:
            items = list(self._packages.values())
        if strategy_name:
            items = [p for p in items if p.strategy_name == strategy_name]
        if symbol:
            sym = symbol.upper()
            items = [p for p in items if p.symbol.upper() == sym]
        if proposal_id:
            items = [p for p in items if p.proposal_id == proposal_id]
        return sorted(items, key=lambda p: p.created_at)
