from __future__ import annotations

from datetime import datetime, timedelta, timezone

from autonomous.idempotency import IN_FLIGHT, SUBMITTED, IdempotencyLock, IdempotencyStore


def test_idempotency_store_blocks_active_duplicate_and_allows_after_clear(tmp_path):
    store = IdempotencyStore(path=str(tmp_path / "idempotency.jsonl"))

    first = store.acquire(symbol="aaa", intended_action="buy", run_id="run-1")
    duplicate = store.acquire(symbol="AAA", intended_action="BUY", run_id="run-2")

    assert first.acquired is True
    assert first.lock.key == "autonomous-live:BUY:AAA"
    assert duplicate.acquired is False
    assert duplicate.existing is not None
    assert duplicate.existing.key == first.lock.key

    store.clear(first.lock.key, reason="test terminal state")
    reacquired = store.acquire(symbol="AAA", intended_action="BUY", run_id="run-3")

    assert reacquired.acquired is True
    assert reacquired.lock.key == first.lock.key


def test_idempotency_store_marks_submitted_and_replays_latest_state(tmp_path):
    store = IdempotencyStore(path=str(tmp_path / "idempotency.jsonl"))

    acquired = store.acquire(symbol="AAA", run_id="run-1", decision_id="decision-1")
    store.mark_submitted(
        acquired.lock.key,
        broker_order_id=700,
        autonomous_trade_id="trade-1",
        metadata={"quantity": 2},
    )

    current = store.current_locks()[acquired.lock.key]
    assert current.status == SUBMITTED
    assert current.broker_order_id == 700
    assert current.autonomous_trade_id == "trade-1"
    assert current.metadata["quantity"] == 2
    assert store.active_locks()[0].key == acquired.lock.key


def test_idempotency_store_lists_and_clears_stale_active_locks(tmp_path):
    store = IdempotencyStore(path=str(tmp_path / "idempotency.jsonl"))
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    lock = IdempotencyLock(
        key="autonomous-live:BUY:AAA",
        status=IN_FLIGHT,
        symbol="AAA",
        intended_action="BUY",
        created_at=old,
        updated_at=old,
    )
    store._append_unlocked("ACQUIRE", lock)

    stale = store.list_stale(older_than_minutes=10)

    assert [item.key for item in stale] == ["autonomous-live:BUY:AAA"]
    cleared = store.clear(lock.key, reason="operator cleared stale lock")
    assert cleared is not None
    assert store.active_locks() == []
