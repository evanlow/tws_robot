from __future__ import annotations

import json
from datetime import datetime, timezone

from autonomous.broker_fill_ingestor import BrokerFillIngestor
from autonomous.order_lifecycle import OrderLifecycleState, OrderLifecycleStore
from autonomous.outcome_evidence_writer import OutcomeEvidenceWriter
from autonomous.trade_store import CLOSED, EXIT_PENDING, OPEN, AutonomousTrade, TradeStore


def _trade_store(tmp_path):
    return TradeStore(path=str(tmp_path / "trades.jsonl"))


def _seed_trade(store: TradeStore, *, quantity: int = 100) -> AutonomousTrade:
    trade = AutonomousTrade(
        autonomous_trade_id="trade-1",
        symbol="AAPL",
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=10,
        entry_time=datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc),
        entry_limit_price=100.0,
        quantity=quantity,
        target_price=110.0,
        stop_price=95.0,
        target_order_id=11,
        stop_order_id=12,
        entry_lifecycle_id="entry-life",
        target_lifecycle_id="target-life",
        stop_lifecycle_id="stop-life",
    )
    store.record_trade(trade)
    return trade


def test_ingests_partial_entry_fills_and_enriched_commission(tmp_path):
    store = _trade_store(tmp_path)
    _seed_trade(store)
    lifecycle = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    ingestor = BrokerFillIngestor(store, lifecycle_store=lifecycle)

    first = ingestor.ingest([
        {
            "execution_id": "e1",
            "order_id": 10,
            "symbol": "AAPL",
            "side": "BOT",
            "quantity": 40,
            "price": 100.0,
            "timestamp": "2026-01-01T14:31:00+00:00",
        }
    ])

    trade = store.get("trade-1")
    assert first.entry_fills == 1
    assert trade is not None
    assert trade.status == OPEN
    assert trade.entry_filled_price == 100.0
    assert len(trade.entry_fills) == 1
    assert lifecycle.get_current("entry-life").state == OrderLifecycleState.PARTIALLY_FILLED

    second = ingestor.ingest([
        {
            "execution_id": "e1",
            "order_id": 10,
            "symbol": "AAPL",
            "side": "BOT",
            "quantity": 40,
            "price": 100.0,
            "commission": 0.4,
            "timestamp": "2026-01-01T14:31:00+00:00",
        },
        {
            "execution_id": "e2",
            "order_id": 10,
            "symbol": "AAPL",
            "side": "BOT",
            "quantity": 60,
            "price": 101.0,
            "commission": 0.6,
            "timestamp": "2026-01-01T14:31:05+00:00",
        },
    ])

    trade = store.get("trade-1")
    assert second.entry_fills == 2
    assert trade is not None
    assert len(trade.entry_fills) == 2
    assert trade.entry_fills[0]["commission"] == 0.4
    assert trade.entry_filled_price == 100.6
    assert lifecycle.get_current("entry-life").state == OrderLifecycleState.FILLED


def test_exit_fill_closes_trade_and_emits_outcome(tmp_path):
    store = _trade_store(tmp_path)
    _seed_trade(store)
    lifecycle = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    writer = OutcomeEvidenceWriter(str(tmp_path / "logs"))
    ingestor = BrokerFillIngestor(store, lifecycle_store=lifecycle, outcome_writer=writer)

    ingestor.ingest([
        {
            "execution_id": "entry-1",
            "order_id": 10,
            "symbol": "AAPL",
            "side": "BOT",
            "quantity": 100,
            "price": 100.5,
            "commission": 1.0,
            "timestamp": "2026-01-01T14:31:00+00:00",
        }
    ])
    result = ingestor.ingest([
        {
            "execution_id": "exit-1",
            "order_id": 11,
            "symbol": "AAPL",
            "side": "SLD",
            "quantity": 100,
            "price": 110.0,
            "commission": 1.25,
            "timestamp": "2026-01-01T15:00:00+00:00",
        }
    ])

    trade = store.get("trade-1")
    assert result.exit_fills == 1
    assert result.trades_closed == 1
    assert result.outcomes_emitted == 1
    assert trade is not None
    assert trade.status == CLOSED
    assert trade.exit_order_id == 11
    assert trade.exit_reason == "TAKE_PROFIT"
    assert trade.exit_price == 110.0
    assert trade.realised_pnl == 947.75
    assert trade.outcome_emitted is True
    assert lifecycle.get_current("target-life").state == OrderLifecycleState.FILLED
    assert lifecycle.get_current("entry-life").state == OrderLifecycleState.CLOSED

    outcome_files = list((tmp_path / "logs").glob("autonomous_evidence_*.jsonl"))
    assert len(outcome_files) == 1
    outcome = json.loads(outcome_files[0].read_text().strip())
    assert outcome["evidence_type"] == "autonomous_outcome"
    assert outcome["outcome"]["commission"] == 2.25
    assert outcome["outcome"]["partial_fill"] is False


def test_partial_exit_fill_does_not_close_trade(tmp_path):
    store = _trade_store(tmp_path)
    _seed_trade(store)
    lifecycle = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    writer = OutcomeEvidenceWriter(str(tmp_path / "logs"))
    ingestor = BrokerFillIngestor(store, lifecycle_store=lifecycle, outcome_writer=writer)

    ingestor.ingest([
        {
            "execution_id": "entry-1",
            "order_id": 10,
            "symbol": "AAPL",
            "side": "BOT",
            "quantity": 100,
            "price": 100.0,
            "timestamp": "2026-01-01T14:31:00+00:00",
        },
        {
            "execution_id": "exit-1",
            "order_id": 11,
            "symbol": "AAPL",
            "side": "SLD",
            "quantity": 40,
            "price": 110.0,
            "timestamp": "2026-01-01T15:00:00+00:00",
        },
    ])

    trade = store.get("trade-1")
    assert trade is not None
    assert trade.status == EXIT_PENDING
    assert len(trade.exit_fills) == 1
    assert lifecycle.get_current("target-life").state == OrderLifecycleState.PARTIALLY_FILLED
    assert list((tmp_path / "logs").glob("autonomous_evidence_*.jsonl")) == []
