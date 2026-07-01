"""Regression test: ORB plans must never reach the generic naked-entry paper
adapter path.

``TradePlanner`` produces ORB ``TradePlan`` objects with stop/target
metadata, but the engine's generic ``_execute_paper``/``_execute_paper_basket``
only submit a bare LIMIT buy — they do not carry stop/target protection or
route through the Phase 2.5 ``ORBPaperExecutor`` bracket-preferred path. An
ORB candidate accepted via ``allowed_signal_labels`` must therefore be
rejected before ``paper_adapter.buy()`` is ever called.
"""

from pathlib import Path

from autonomous import (
    AutonomousMode,
    AutonomousTradingConfig,
    AutonomousTradingEngine,
    CandidateScanner,
    CandidateSignal,
    DecisionStatus,
    StaticSignalProvider,
)
from autonomous.audit import AuditLogger
from data.cash_availability import CashAvailabilityAnalyzer


def _orb_signal(symbol="QQQ"):
    return CandidateSignal(
        symbol=symbol,
        strength_score=100,
        signal_label="ORB_LONG_MODEL_A",
        last_price=101.5,
        support_price=100.5,
        resistance_price=105.5,
        extras={
            "strategy": "opening_range_breakout",
            "setup_model": "MODEL_A_DISPLACEMENT_GAP",
            "direction": "LONG",
            "entry_price": 101.5,
            "stop_price": 100.5,
            "target_price": 105.5,
            "risk_per_share": 1.0,
            "reward_per_share": 4.0,
            "rr_ratio": 4.0,
        },
    )


def _make_orb_engine(tmp_path: Path, paper_adapter=None, mode=AutonomousMode.PAPER_EXECUTE):
    signal = _orb_signal()
    provider = StaticSignalProvider([signal])
    scanner = CandidateScanner(
        signal_provider=provider,
        symbols=[{"symbol": signal.symbol, "security": signal.symbol, "sector": "X", "sub_industry": ""}],
    )
    audit = AuditLogger(log_dir=str(tmp_path))
    cfg = AutonomousTradingConfig(
        mode=mode,
        require_user_confirmation=False,
        allowed_signal_labels=["ORB_LONG_MODEL_A", "ORB_LONG_MODEL_B"],
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {"cash_balance": 100_000, "equity": 100_000},
        positions_provider=lambda: {},
        config=cfg,
        paper_adapter=paper_adapter,
        audit_logger=audit,
    )


def test_orb_candidate_in_paper_execute_does_not_call_paper_adapter_buy(tmp_path):
    placed = []

    class _Adapter:
        def buy(self, **kw):
            placed.append(kw)
            return 99

    engine = _make_orb_engine(tmp_path, paper_adapter=_Adapter())
    d = engine.run_once(confirm=True)

    assert placed == [], "ORB plan must never reach the naked-entry paper adapter"
    assert d.status is DecisionStatus.EXECUTION_FAILED
    assert d.rejection_reason == (
        "ORB paper execution must use ORBProposal/ORBPaperExecutor protected path"
    )


def test_orb_candidate_recommend_only_is_unaffected(tmp_path):
    """recommend-only planning of ORB candidates must still work."""
    engine = _make_orb_engine(tmp_path, mode=AutonomousMode.RECOMMEND_ONLY)
    d = engine.run_once()
    assert d.status is DecisionStatus.RECOMMENDED
    assert d.trade_plan["strategy"] == "opening_range_breakout"
