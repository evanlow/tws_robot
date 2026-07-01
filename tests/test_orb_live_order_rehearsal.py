"""Tests for ORB Phase 5 assisted-live protected order-path rehearsal (#227).

Covers: a valid rehearsal package built from a valid ORB proposal, readiness
failure, live-master-switch-disabled, operator-confirmation-missing, account
mismatch, missing stop/target, Model C refusal, short-direction refusal, raw
market order refusal, stale/expired/executed proposal refusal, and that a
successful (and refused) build is always audit-logged. Never places an order.
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
from autonomous.orb_live_readiness import ASSISTED_LIVE_CANDIDATE, LOCKED
from autonomous.orb_live_order_rehearsal import (
    ORBAssistedLiveRefusal,
    ORBAssistedLiveRefusalReason,
    ORBAssistedLiveRehearsalStore,
    build_assisted_live_rehearsal_package,
)
from autonomous.orb_proposals import ProposalGates, ProposalStatus, build_proposal


def _candle(symbol="QQQ", o=103.0, h=103.5, l=102.8, c=103.4):
    start = datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc)
    return Candle(symbol, "5m", start, start, o, h, l, c, volume=1000.0)


def _setup(
    symbol="QQQ",
    entry=104.0,
    stop=103.0,
    target=106.0,
    direction=ORBDirection.LONG,
    model=ORBEntryModel.MODEL_A_DISPLACEMENT_GAP,
):
    rng = OpeningRange(
        symbol=symbol, session_date="2026-06-01",
        range_start=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        range_end=datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc),
        high=102.0, low=100.0, source_candle=_candle(symbol),
    )
    conf = BreakoutConfirmation(
        symbol=symbol, direction=direction, candle_5m=_candle(symbol),
        range_high=102.0, range_low=100.0,
        confirmed_at=datetime(2026, 6, 1, 9, 50, tzinfo=timezone.utc),
    )
    risk = entry - stop
    return ORBSetup(
        symbol=symbol, direction=direction, model=model,
        detected_at=datetime(2026, 6, 1, 9, 51, tzinfo=timezone.utc),
        entry_price=entry, stop_price=stop, target_price=target,
        risk_per_share=risk, reward_per_share=target - entry,
        rr_ratio=(target - entry) / risk if risk else 0.0,
        opening_range=rng, confirmation=conf,
        evidence={"gap_low": 103.1},
    )


def _proposal(**overrides):
    setup_kwargs = {}
    for key in ("symbol", "entry", "stop", "target", "direction", "model"):
        if key in overrides:
            setup_kwargs[key] = overrides.pop(key)
    return build_proposal(
        _setup(**setup_kwargs), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
        equity=100_000.0, risk_per_trade_equity_pct=0.002,
        **overrides,
    )


def _readiness(status=ASSISTED_LIVE_CANDIDATE):
    return {"overall_status": status, "requested_mode": "assisted_live"}


def _kwargs(**overrides):
    base = dict(
        account_id="U123456",
        expected_account_id="U123456",
        operator_confirmed=True,
        live_master_switch_enabled=True,
        evidence_id="rev-2026-06-01-ORB1",
    )
    base.update(overrides)
    return base


@pytest.fixture
def audit(tmp_path):
    return AuditLogger(str(tmp_path))


def _log_lines(tmp_path):
    files = list(tmp_path.glob("autonomous_trading_*.jsonl"))
    assert files, "expected an audit log file"
    return files[0].read_text(encoding="utf-8").strip().splitlines()


# ---- success path ---------------------------------------------------------

def test_valid_proposal_builds_rehearsal_package(audit, tmp_path):
    proposal = _proposal()
    pkg = build_assisted_live_rehearsal_package(
        proposal, _readiness(), audit=audit, **_kwargs()
    )
    assert pkg.strategy_name == "ORB1"
    assert pkg.session_date == "2026-06-01"
    assert pkg.symbol == "QQQ"
    assert pkg.account_id == "U123456"
    assert pkg.proposal_id == proposal.proposal_id
    assert pkg.entry_model == "MODEL_A_DISPLACEMENT_GAP"
    assert pkg.direction == "LONG"
    assert pkg.quantity == proposal.quantity
    assert pkg.entry_order_type == "LIMIT"
    assert pkg.entry_limit_price == proposal.entry_price
    assert pkg.stop_price == proposal.stop_price
    assert pkg.target_price == proposal.target_price
    assert pkg.bracket.entry_order_type == "LIMIT"
    assert pkg.bracket.stop_order_type == "STOP"
    assert pkg.time_in_force == "DAY"
    assert pkg.readiness_snapshot["overall_status"] == ASSISTED_LIVE_CANDIDATE
    assert pkg.operator_confirmation_snapshot["operator_confirmed"] is True
    assert pkg.audit_event_id
    assert pkg.evidence_id == "rev-2026-06-01-ORB1"
    assert pkg.mode == "REHEARSAL"
    assert pkg.status == "DRY_RUN_ONLY"

    lines = _log_lines(tmp_path)
    assert any('"rehearsal_created"' in line for line in lines)


def test_model_b_is_eligible(audit):
    proposal = _proposal(model=ORBEntryModel.MODEL_B_BREAK_RETEST)
    pkg = build_assisted_live_rehearsal_package(
        proposal, _readiness(), audit=audit, **_kwargs()
    )
    assert pkg.entry_model == "MODEL_B_BREAK_RETEST"


def test_rehearsal_store_add_get_list(audit):
    proposal = _proposal()
    pkg = build_assisted_live_rehearsal_package(
        proposal, _readiness(), audit=audit, **_kwargs()
    )
    store = ORBAssistedLiveRehearsalStore()
    store.add(pkg)
    assert store.get(pkg.rehearsal_id) is pkg
    assert store.get("missing") is None
    assert store.list(strategy_name="ORB1") == [pkg]
    assert store.list(symbol="AAPL") == []
    assert store.list(proposal_id=proposal.proposal_id) == [pkg]


# ---- fail-closed paths ------------------------------------------------------

def test_missing_proposal_refused(audit, tmp_path):
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(None, _readiness(), audit=audit, **_kwargs())
    assert exc.value.reason == ORBAssistedLiveRefusalReason.PROPOSAL_MISSING
    assert any('"rehearsal_refused"' in line for line in _log_lines(tmp_path))


def test_readiness_not_passed_refused(audit):
    proposal = _proposal()
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(status=LOCKED), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.READINESS_NOT_PASSED


def test_missing_readiness_result_refused(audit):
    proposal = _proposal()
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(proposal, None, audit=audit, **_kwargs())
    assert exc.value.reason == ORBAssistedLiveRefusalReason.READINESS_NOT_PASSED


def test_live_master_switch_disabled_refused(audit):
    proposal = _proposal()
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit,
            **_kwargs(live_master_switch_enabled=False),
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.LIVE_MASTER_SWITCH_DISABLED


def test_operator_confirmation_missing_refused(audit):
    proposal = _proposal()
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit,
            **_kwargs(operator_confirmed=False),
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.OPERATOR_CONFIRMATION_MISSING


def test_account_mismatch_refused(audit):
    proposal = _proposal()
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit,
            **_kwargs(account_id="U999999"),
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.ACCOUNT_MISMATCH


def test_account_missing_refused(audit):
    proposal = _proposal()
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit,
            **_kwargs(account_id=None),
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.ACCOUNT_MISMATCH


def test_model_c_refused(audit):
    proposal = _proposal(model=ORBEntryModel.MODEL_C_REVERSAL)
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.MODEL_C_DISABLED


def test_unknown_model_refused(audit):
    proposal = _proposal()
    proposal.entry_model = "MODEL_Z_UNKNOWN"
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.UNKNOWN_MODEL


def test_short_direction_refused(audit):
    proposal = _proposal()
    # Mutate directly since build_proposal itself rejects SHORT setups.
    proposal.direction = "SHORT"
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.SHORT_DIRECTION


def test_raw_market_order_refused(audit):
    proposal = _proposal()
    proposal.order_type = "MARKET"
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.RAW_MARKET_ORDER


def test_missing_stop_refused(audit):
    proposal = _proposal()
    proposal.stop_price = 0.0
    proposal.gates.stop_present = False
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.MISSING_STOP


def test_missing_target_refused(audit):
    proposal = _proposal()
    proposal.target_price = 0.0
    proposal.gates.target_present = False
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.MISSING_TARGET


def test_stale_expired_proposal_refused(audit):
    proposal = _proposal()
    proposal.status = ProposalStatus.EXPIRED.value
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.PROPOSAL_NOT_EXECUTABLE


def test_already_executed_proposal_refused(audit):
    proposal = _proposal()
    proposal.status = ProposalStatus.EXECUTED.value
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.PROPOSAL_NOT_EXECUTABLE


def test_skipped_proposal_refused(audit):
    proposal = _proposal()
    proposal.status = ProposalStatus.SKIPPED.value
    with pytest.raises(ORBAssistedLiveRefusal) as exc:
        build_assisted_live_rehearsal_package(
            proposal, _readiness(), audit=audit, **_kwargs()
        )
    assert exc.value.reason == ORBAssistedLiveRefusalReason.PROPOSAL_NOT_EXECUTABLE


def test_no_live_order_side_effects(audit):
    """Never calls a broker/live path; the package is a plain, inert dict."""
    proposal = _proposal()
    pkg = build_assisted_live_rehearsal_package(
        proposal, _readiness(), audit=audit, **_kwargs()
    )
    d = pkg.to_dict()
    assert isinstance(d, dict)
    assert d["mode"] == "REHEARSAL"
    assert d["status"] == "DRY_RUN_ONLY"
