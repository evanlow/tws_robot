"""Append-only idempotency locks for autonomous live order submission.

The store is intentionally conservative.  Active locks block duplicate live
entries for the same symbol/action until the matching trade is terminal or an
operator explicitly clears a stale lock.  This protects the restart window
between broker submission and local evidence/trade-store writes.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


IN_FLIGHT = "IN_FLIGHT"
SUBMITTED = "SUBMITTED"
CLEARED = "CLEARED"

ACTIVE_STATUSES = {IN_FLIGHT, SUBMITTED}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return _now()


@dataclass
class IdempotencyLock:
    """Current state for one idempotency key."""

    key: str
    status: str
    symbol: str
    intended_action: str
    lock_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    run_id: Optional[str] = None
    decision_id: Optional[str] = None
    basket_id: Optional[str] = None
    leg_id: Optional[str] = None
    signal_timestamp: Optional[str] = None
    broker_order_id: Optional[int] = None
    autonomous_trade_id: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def is_stale(self, *, older_than_minutes: int, now: Optional[datetime] = None) -> bool:
        ref = now or _now()
        updated = self.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return ref - updated >= timedelta(minutes=max(0, older_than_minutes))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = _iso(self.created_at)
        data["updated_at"] = _iso(self.updated_at)
        return data

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "IdempotencyLock":
        kwargs = dict(payload)
        kwargs["created_at"] = _parse_dt(kwargs.get("created_at"))
        kwargs["updated_at"] = _parse_dt(kwargs.get("updated_at"))
        metadata = kwargs.get("metadata")
        kwargs["metadata"] = metadata if isinstance(metadata, dict) else {}
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in kwargs.items() if k in known}
        return cls(**kwargs)


@dataclass(frozen=True)
class LockAcquisition:
    acquired: bool
    lock: IdempotencyLock
    existing: Optional[IdempotencyLock] = None
    reason: str = ""


class IdempotencyStore:
    """Append-only JSONL idempotency lock store."""

    def __init__(self, path: str = "logs/autonomous_idempotency.jsonl") -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def build_key(
        *,
        symbol: str,
        intended_action: str = "BUY",
        basket_id: Optional[str] = None,
        leg_id: Optional[str] = None,
    ) -> str:
        symbol_part = str(symbol or "").strip().upper()
        action_part = str(intended_action or "").strip().upper()
        if basket_id or leg_id:
            return f"autonomous-live:{action_part}:{symbol_part}:{basket_id or 'single'}:{leg_id or 'entry'}"
        return f"autonomous-live:{action_part}:{symbol_part}"

    def acquire(
        self,
        *,
        symbol: str,
        intended_action: str = "BUY",
        run_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        basket_id: Optional[str] = None,
        leg_id: Optional[str] = None,
        signal_timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LockAcquisition:
        key = self.build_key(
            symbol=symbol,
            intended_action=intended_action,
            basket_id=basket_id,
            leg_id=leg_id,
        )
        with self._lock:
            current = self._replay_unlocked().get(key)
            if current is not None and current.active:
                return LockAcquisition(
                    acquired=False,
                    lock=current,
                    existing=current,
                    reason=f"active idempotency lock exists for {key}",
                )
            lock = IdempotencyLock(
                key=key,
                status=IN_FLIGHT,
                symbol=str(symbol or "").strip().upper(),
                intended_action=str(intended_action or "").strip().upper(),
                run_id=run_id,
                decision_id=decision_id,
                basket_id=basket_id,
                leg_id=leg_id,
                signal_timestamp=signal_timestamp,
                reason="acquired before broker submission",
                metadata=dict(metadata or {}),
            )
            self._append_unlocked("ACQUIRE", lock)
            return LockAcquisition(acquired=True, lock=lock, reason="acquired")

    def mark_submitted(
        self,
        key: str,
        *,
        broker_order_id: Optional[int] = None,
        autonomous_trade_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IdempotencyLock:
        with self._lock:
            current = self._replay_unlocked().get(key)
            if current is None:
                raise KeyError(f"idempotency key not found: {key}")
            updated = IdempotencyLock.from_dict(current.to_dict())
            updated.status = SUBMITTED
            updated.updated_at = _now()
            updated.broker_order_id = (
                int(broker_order_id) if broker_order_id is not None else current.broker_order_id
            )
            updated.autonomous_trade_id = autonomous_trade_id or current.autonomous_trade_id
            updated.reason = "broker submission accepted"
            updated.metadata.update(dict(metadata or {}))
            self._append_unlocked("SUBMITTED", updated)
            return updated

    def clear(self, key: str, *, reason: str = "cleared") -> Optional[IdempotencyLock]:
        with self._lock:
            current = self._replay_unlocked().get(key)
            if current is None:
                return None
            updated = IdempotencyLock.from_dict(current.to_dict())
            updated.status = CLEARED
            updated.updated_at = _now()
            updated.reason = reason
            self._append_unlocked("CLEAR", updated)
            return updated

    def current_locks(self) -> Dict[str, IdempotencyLock]:
        with self._lock:
            return self._replay_unlocked()

    def active_locks(self) -> List[IdempotencyLock]:
        return [lock for lock in self.current_locks().values() if lock.active]

    def list_stale(
        self,
        *,
        older_than_minutes: int,
        now: Optional[datetime] = None,
    ) -> List[IdempotencyLock]:
        return [
            lock for lock in self.active_locks()
            if lock.is_stale(older_than_minutes=older_than_minutes, now=now)
        ]

    def _append_unlocked(self, op: str, lock: IdempotencyLock) -> None:
        record = {
            "op": op,
            "key": lock.key,
            "lock": lock.to_dict(),
            "ts": _iso(_now()),
        }
        os.makedirs(self._path.parent, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str, sort_keys=True))
            fh.write("\n")

    def _replay_unlocked(self) -> Dict[str, IdempotencyLock]:
        current: Dict[str, IdempotencyLock] = {}
        if not self._path.exists():
            return current
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    lock = IdempotencyLock.from_dict(record.get("lock") or {})
                except (TypeError, ValueError, KeyError):
                    continue
                if lock.key:
                    current[lock.key] = lock
        return current

    def serialise(self, locks: Iterable[IdempotencyLock]) -> List[Dict[str, Any]]:
        return [lock.to_dict() for lock in locks]
