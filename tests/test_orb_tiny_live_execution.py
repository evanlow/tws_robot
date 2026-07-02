"""Tests for ORB Phase 6 human-confirmed tiny-live assisted execution (#229).

Covers the safety posture of ``autonomous.orb_tiny_live_execution``: a real
broker order can only be submitted from a valid, not-previously-submitted
Phase 5 rehearsal package after an explicit final human confirmation, with
every Phase 4 readiness gate and every other live safety gate re-checked
immediately before submit. Uses a fake broker adapter; never calls a real
broker. Proves no broker call happens on refused paths.
"""

from datetime import datetime, timezone

import pytest

from autonomous.audit import AuditLogger
from autonomous.opening_range import (
    BreakoutConfirmation,
    Candle,
    ORBDirection,
    ORBEntryModel,
    ORBSetup,
    OpeningRange,
)
from autonomous.orb_live_order_adapter import (
    FakeORBLiveOrderAdapter,
    ORBLiveOrderAdapterError,
)
from autonomous.orb_live_order_rehearsal import (
    build_assisted_live_rehearsal_package,
)
from autonomous.orb_live_readiness import ASSISTED_LIVE_CANDIDATE, LOCKED
from autonomous.orb_proposals import ORBProposalStore, ProposalGates, ProposalStatus
from autonomous.orb_tiny_live_execution import (
    ORBTinyLiveOrderStore,
    ORBTinyLiveRefusal,
    ORBTinyLiveRefusalReason,
    submit_tiny_live_order,
)

ACCOUNT_ID = "DU12345"


def _setup(symbol="QQQ", session_date="2026-06-01", model=ORBEntryModel.MODEL_A_DISPLACEMENT_GAP,
           direction=ORBDirection.LONG, entry=104.0, stop=103.0, target=106.0):
    start = datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc)
    c5 = Candle(symbol, "5m", start, start, 103.0, 103.5, 102.8, 103.4, 1000.0)
    rng = OpeningRange(symbol, session_date, start, start, 102.0, 100.0, c5)
    conf = BreakoutConfirmation(symbol, direction, c5, 102.0, 100.0, start)
    return ORBSetup(
        symbol=symbol, direction=direction, model=model, detected_at=start,
        entry_price=entry, stop_price=stop, target_price=target,
        risk_per_share=abs(entry - stop), reward_per_share=abs(target - entry),
        rr_ratio=abs(target - entry) / abs(entry - stop),
        opening_range=rng, confirmation=conf, evidence={},
    )


def _proposal_and_store(**kwargs):
    store = ORBProposalStore(log_dir="/tmp")
    proposal = store.create_from_setup(
        _setup(**kwargs), strategy_name="ORB1", session_date=kwargs.get("session_date", "2026-06-01"),
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    return store, proposal


def _rehearsal(proposal, *, audit, log_dir):
    result = {"overall_status": ASSISTED_LIVE_CANDIDATE}
    return build_assisted_live_rehearsal_package(
        proposal, result,
        account_id=ACCOUNT_ID, expected_account_id=ACCOUNT_ID,
        operator_confirmed=True, live_master_switch_enabled=True,
        audit=audit, log_dir=log_dir,
    )


def _gates(**overrides):
    gates = dict(
        confirm_live_order=True,
        operator="alice",
        expected_account_id=ACCOUNT_ID,
        account_id=ACCOUNT_ID,
        notes="confirming tiny live trade",
        live_master_switch_enabled=True,
        emergency_stop_active=False,
        market_data_source="ibkr",
        daily_live_orb_trade_count=0,
        max_live_orb_trades_per_day=1,
        account_equity=5_000_000.0,
        max_deployable_cash_pct=0.01,
    )
    gates.update(overrides)
    return gates


@pytest.fixture
def env(tmp_path):
    log_dir = str(tmp_path / "logs")
    audit = AuditLogger(log_dir)
    store, proposal = _proposal_and_store()
    rehearsal = _rehearsal(proposal, audit=audit, log_dir=log_dir)
    readiness = {"overall_status": ASSISTED_LIVE_CANDIDATE}
    adapter = FakeORBLiveOrderAdapter()
    order_store = ORBTinyLiveOrderStore(state_dir=log_dir)
    return {
        "proposal": proposal,
        "rehearsal": rehearsal,
        "readiness": readiness,
        "adapter": adapter,
        "order_store": order_store,
        "audit": audit,
        "log_dir": log_dir,
    }


def _submit(env, **overrides):
    kwargs = _gates(**overrides.pop("gates", {}))
    return submit_tiny_live_order(
        overrides.pop("rehearsal", env["rehearsal"]),
        overrides.pop("proposal", env["proposal"]),
        overrides.pop("readiness", env["readiness"]),
        adapter=overrides.pop("adapter", env["adapter"]),
        order_store=overrides.pop("order_store", None),
        already_submitted=overrides.pop("already_submitted", False),
        audit=env["audit"],
        log_dir=env["log_dir"],
        **kwargs,
    )


# ---- happy path -------------------------------------------------------

def test_successful_submit_calls_adapter_and_records_broker_ids(env):
    group = _submit(env)
    adapter = env["adapter"]

    assert adapter.submit_calls == 1
    assert group.status == "SUBMITTED"
    assert group.protection_broker_visible is True
    assert group.entry_broker_order_id
    assert group.stop_broker_order_id
    assert group.target_broker_order_id
    assert group.rehearsal_id == env["rehearsal"].rehearsal_id
    assert group.proposal_id == env["proposal"].proposal_id
    assert group.account_id == ACCOUNT_ID
    assert group.quantity == env["rehearsal"].quantity

    # Audit logged.
    records = _audit_records(env["log_dir"])
    assert any(
        r.get("kind") == "orb_tiny_live_execution" and r.get("action") == "tiny_live_order_submitted"
        for r in records
    )


def _audit_records(log_dir):
    import json
    from pathlib import Path
    files = list(Path(log_dir).glob("autonomous_trading_*.jsonl"))
    records = []
    for f in files:
        for line in f.read_text().splitlines():
            records.append(json.loads(line))
    return records


# ---- fail-closed gates: no broker call on any refused path -------------

def test_missing_rehearsal_refused_no_broker_call(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, rehearsal=None)
    assert exc.value.reason == ORBTinyLiveRefusalReason.REHEARSAL_MISSING
    assert env["adapter"].submit_calls == 0


def test_rehearsal_not_dry_run_refused(env):
    env["rehearsal"].status = "SUBMITTED"
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env)
    assert exc.value.reason == ORBTinyLiveRefusalReason.REHEARSAL_NOT_DRY_RUN
    assert env["adapter"].submit_calls == 0


def test_already_submitted_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, already_submitted=True)
    assert exc.value.reason == ORBTinyLiveRefusalReason.REHEARSAL_ALREADY_SUBMITTED
    assert env["adapter"].submit_calls == 0


def test_proposal_missing_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, proposal=None)
    assert exc.value.reason == ORBTinyLiveRefusalReason.PROPOSAL_MISSING
    assert env["adapter"].submit_calls == 0


def test_proposal_mismatch_refused(env):
    _, other_proposal = _proposal_and_store(symbol="AAPL")
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, proposal=other_proposal)
    assert exc.value.reason == ORBTinyLiveRefusalReason.PROPOSAL_MISMATCH
    assert env["adapter"].submit_calls == 0


def test_proposal_not_pending_refused(env):
    env["proposal"].status = ProposalStatus.EXECUTED.value
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env)
    assert exc.value.reason == ORBTinyLiveRefusalReason.PROPOSAL_NOT_EXECUTABLE
    assert env["adapter"].submit_calls == 0


def test_readiness_not_passed_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, readiness={"overall_status": LOCKED})
    assert exc.value.reason == ORBTinyLiveRefusalReason.READINESS_NOT_PASSED
    assert env["adapter"].submit_calls == 0


def test_live_master_switch_disabled_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"live_master_switch_enabled": False})
    assert exc.value.reason == ORBTinyLiveRefusalReason.LIVE_MASTER_SWITCH_DISABLED
    assert env["adapter"].submit_calls == 0


def test_emergency_stop_active_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"emergency_stop_active": True})
    assert exc.value.reason == ORBTinyLiveRefusalReason.EMERGENCY_STOP_ACTIVE
    assert env["adapter"].submit_calls == 0


def test_account_mismatch_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"account_id": "DU99999"})
    assert exc.value.reason == ORBTinyLiveRefusalReason.ACCOUNT_MISMATCH
    assert env["adapter"].submit_calls == 0


def test_operator_confirmation_missing_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"confirm_live_order": False})
    assert exc.value.reason == ORBTinyLiveRefusalReason.OPERATOR_CONFIRMATION_MISSING
    assert env["adapter"].submit_calls == 0


def test_operator_name_missing_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"operator": "  "})
    assert exc.value.reason == ORBTinyLiveRefusalReason.OPERATOR_CONFIRMATION_MISSING
    assert env["adapter"].submit_calls == 0


def test_market_data_unacceptable_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"market_data_source": "yahoo"})
    assert exc.value.reason == ORBTinyLiveRefusalReason.MARKET_DATA_UNACCEPTABLE
    assert env["adapter"].submit_calls == 0


def test_daily_cap_reached_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"daily_live_orb_trade_count": 1, "max_live_orb_trades_per_day": 1})
    assert exc.value.reason == ORBTinyLiveRefusalReason.DAILY_CAP_REACHED
    assert env["adapter"].submit_calls == 0


def test_risk_cap_unverifiable_refused_when_equity_unknown(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"account_equity": None})
    assert exc.value.reason == ORBTinyLiveRefusalReason.RISK_CAP_UNVERIFIABLE
    assert env["adapter"].submit_calls == 0


def test_risk_cap_exceeded_refused(env):
    # Tiny position value vs. a tiny account equity blows the 1% cash cap.
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, gates={"account_equity": 100.0})
    assert exc.value.reason == ORBTinyLiveRefusalReason.RISK_CAP_EXCEEDED
    assert env["adapter"].submit_calls == 0


def test_short_direction_refused(env):
    env["rehearsal"].direction = "SHORT"
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env)
    assert exc.value.reason == ORBTinyLiveRefusalReason.SHORT_DIRECTION
    assert env["adapter"].submit_calls == 0


def test_model_c_refused(env):
    env["rehearsal"].entry_model = "MODEL_C_REVERSAL"
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env)
    assert exc.value.reason == ORBTinyLiveRefusalReason.MODEL_C_DISABLED
    assert env["adapter"].submit_calls == 0


def test_non_equity_asset_class_refused(env):
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        submit_tiny_live_order(
            env["rehearsal"], env["proposal"], env["readiness"],
            adapter=env["adapter"], audit=env["audit"], log_dir=env["log_dir"],
            asset_class="FOREX", **_gates(),
        )
    assert exc.value.reason == ORBTinyLiveRefusalReason.NON_EQUITY
    assert env["adapter"].submit_calls == 0


def test_raw_market_order_refused(env):
    env["rehearsal"].entry_order_type = "MARKET"
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env)
    assert exc.value.reason == ORBTinyLiveRefusalReason.RAW_MARKET_ORDER
    assert env["adapter"].submit_calls == 0


def test_missing_stop_refused(env):
    env["rehearsal"].stop_price = 0.0
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env)
    assert exc.value.reason == ORBTinyLiveRefusalReason.MISSING_STOP
    assert env["adapter"].submit_calls == 0


def test_missing_target_refused(env):
    env["rehearsal"].target_price = 0.0
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env)
    assert exc.value.reason == ORBTinyLiveRefusalReason.MISSING_TARGET
    assert env["adapter"].submit_calls == 0


def test_broken_bracket_ordering_refused(env):
    env["rehearsal"].target_price = 1.0  # below entry -> invalid bracket
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env)
    assert exc.value.reason == ORBTinyLiveRefusalReason.PROTECTION_UNREPRESENTABLE
    assert env["adapter"].submit_calls == 0


# ---- broker adapter: protection confirmation is mandatory --------------

def test_protection_not_broker_visible_fails_closed_and_cancels(env):
    adapter = FakeORBLiveOrderAdapter(protection_broker_visible=False)
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, adapter=adapter)
    assert exc.value.reason == ORBTinyLiveRefusalReason.PROTECTION_NOT_BROKER_VISIBLE
    assert adapter.submit_calls == 1
    assert adapter.cancel_calls == 1
    assert len(adapter.cancelled) == 1

    records = _audit_records(env["log_dir"])
    assert any(
        r.get("kind") == "orb_tiny_live_execution" and r.get("action") == "tiny_live_order_refused"
        and r.get("reason") == "protection_not_broker_visible"
        for r in records
    )


def test_broker_submit_failure_fails_closed(env):
    adapter = FakeORBLiveOrderAdapter(raise_on_submit=ORBLiveOrderAdapterError("simulated outage"))
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, adapter=adapter)
    assert exc.value.reason == ORBTinyLiveRefusalReason.BROKER_SUBMIT_FAILED


# ---- order store ---------------------------------------------------------

def test_order_store_tracks_rehearsal_and_daily_count(env):
    store = env["order_store"]
    assert store.is_rehearsal_submitted(env["rehearsal"].rehearsal_id) is False
    group = _submit(env)
    store.add(group)
    assert store.is_rehearsal_submitted(env["rehearsal"].rehearsal_id) is True
    assert store.daily_count("ORB1", "2026-06-01") == 1
    assert store.get(group.order_group_id).order_group_id == group.order_group_id

    cancelled = store.mark_cancelled(group.order_group_id)
    assert cancelled.status == "CANCELLED"


# ---- durable idempotency / process-restart safety ------------------------

def test_reservation_written_before_broker_call_blocks_retry_after_memory_loss(env):
    """A durable PENDING_SUBMIT reservation must survive "process restart".

    Simulates the process losing its in-memory order store (e.g. a crash)
    right after a successful broker submit by dropping the original store
    instance and reloading a fresh one from the same on-disk state. The
    second submit attempt (fresh adapter, fresh store object) must be
    refused without ever calling the broker adapter again.
    """
    store = env["order_store"]
    group = _submit(env, order_store=store)
    assert group.status == "SUBMITTED"
    assert store.is_rehearsal_submitted(env["rehearsal"].rehearsal_id) is True

    # Simulate a fresh process: brand-new store object reloaded from disk,
    # and a brand-new adapter instance so a call would be unambiguous.
    reloaded_store = ORBTinyLiveOrderStore(state_dir=env["log_dir"])
    assert reloaded_store.is_rehearsal_submitted(env["rehearsal"].rehearsal_id) is True

    fresh_adapter = FakeORBLiveOrderAdapter()
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, adapter=fresh_adapter, order_store=reloaded_store)
    assert exc.value.reason == ORBTinyLiveRefusalReason.REHEARSAL_ALREADY_SUBMITTED
    assert fresh_adapter.submit_calls == 0


def test_pending_reservation_alone_blocks_resubmit_even_without_a_finalized_group(env):
    """A reservation that never reached ``finalize_submitted`` still blocks.

    Simulates a crash strictly between the durable reservation being written
    and the broker adapter returning (or the finalize step running): the
    store never receives ``add()``/``finalize_submitted`` for this rehearsal,
    yet a fresh submit attempt must still be refused and must not call the
    broker adapter, because the durable in-memory-store-loss scenario cannot
    distinguish "broker call succeeded but crashed before recording it" from
    "still in flight".
    """
    store = env["order_store"]
    reserved = store.reserve_pending(
        "order-group-simulated",
        rehearsal_id=env["rehearsal"].rehearsal_id,
        proposal_id=env["proposal"].proposal_id,
        strategy_name=env["proposal"].strategy_name,
        session_date=env["proposal"].session_date,
    )
    assert reserved is True

    reloaded_store = ORBTinyLiveOrderStore(state_dir=env["log_dir"])
    assert reloaded_store.is_rehearsal_submitted(env["rehearsal"].rehearsal_id) is True

    fresh_adapter = FakeORBLiveOrderAdapter()
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, adapter=fresh_adapter, order_store=reloaded_store)
    assert exc.value.reason == ORBTinyLiveRefusalReason.REHEARSAL_ALREADY_SUBMITTED
    assert fresh_adapter.submit_calls == 0


def test_broker_failure_releases_reservation_so_retry_is_possible(env):
    """A genuine broker failure (no order created) must not permanently block."""
    store = env["order_store"]
    failing_adapter = FakeORBLiveOrderAdapter(
        raise_on_submit=ORBLiveOrderAdapterError("simulated outage")
    )
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, adapter=failing_adapter, order_store=store)
    assert exc.value.reason == ORBTinyLiveRefusalReason.BROKER_SUBMIT_FAILED
    assert store.is_rehearsal_submitted(env["rehearsal"].rehearsal_id) is False

    working_adapter = FakeORBLiveOrderAdapter()
    group = _submit(env, adapter=working_adapter, order_store=store)
    assert group.status == "SUBMITTED"
    assert working_adapter.submit_calls == 1


def test_mark_needs_reconciliation_keeps_order_group_durably_blocking(env):
    """If the proposal cannot be marked EXECUTED, the group is flagged, not silent."""
    store = env["order_store"]
    group = _submit(env, order_store=store)
    reconciled = store.mark_needs_reconciliation(group.order_group_id)
    assert reconciled.status == "SUBMITTED_NEEDS_PROPOSAL_RECONCILIATION"

    # Still durably blocking: a fresh store reloaded from disk still refuses
    # a resubmit for the same rehearsal, and never calls the adapter again.
    reloaded_store = ORBTinyLiveOrderStore(state_dir=env["log_dir"])
    assert reloaded_store.get(group.order_group_id).status == (
        "SUBMITTED_NEEDS_PROPOSAL_RECONCILIATION"
    )
    fresh_adapter = FakeORBLiveOrderAdapter()
    with pytest.raises(ORBTinyLiveRefusal) as exc:
        _submit(env, adapter=fresh_adapter, order_store=reloaded_store)
    assert exc.value.reason == ORBTinyLiveRefusalReason.REHEARSAL_ALREADY_SUBMITTED
    assert fresh_adapter.submit_calls == 0
