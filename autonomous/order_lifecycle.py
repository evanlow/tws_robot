"""Append-only autonomous broker order lifecycle records.

The lifecycle store is deliberately small and file-backed.  It complements the
coarser :mod:`autonomous.trade_store` trade lifecycle by recording each broker
order transition as an append-only event that can be replayed after restart.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class OrderLifecycleState(str, Enum):
    PLANNED = "PLANNED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    PROTECTIVE_STOP_PENDING = "PROTECTIVE_STOP_PENDING"
    PROTECTIVE_STOP_CONFIRMED = "PROTECTIVE_STOP_CONFIRMED"
    TARGET_PENDING = "TARGET_PENDING"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    RECONCILED = "RECONCILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    STALE_QUOTE_BLOCKED = "STALE_QUOTE_BLOCKED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    ORPHANED_ORDER = "ORPHANED_ORDER"
    DUPLICATE_ORDER_BLOCKED = "DUPLICATE_ORDER_BLOCKED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


ENTRY = "entry"
TARGET = "target"
STOP = "stop"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return _now()


@dataclass
class OrderLifecycleEvent:
    """One append-only lifecycle transition for an autonomous broker order."""

    lifecycle_id: str
    state: OrderLifecycleState
    symbol: str
    timestamp: datetime = field(default_factory=_now)
    order_role: str = ENTRY
    broker_order_id: Optional[int] = None
    autonomous_trade_id: Optional[str] = None
    parent_lifecycle_id: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["timestamp"] = _iso(self.timestamp)
        return data

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OrderLifecycleEvent":
        kwargs = dict(payload)
        kwargs["state"] = OrderLifecycleState(kwargs["state"])
        kwargs["timestamp"] = _parse_ts(kwargs.get("timestamp"))
        metadata = kwargs.get("metadata")
        kwargs["metadata"] = metadata if isinstance(metadata, dict) else {}
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in kwargs.items() if k in known}
        return cls(**kwargs)


class OrderLifecycleStore:
    """Append-only JSONL order lifecycle store."""

    def __init__(self, path: str = "logs/autonomous_order_lifecycle.jsonl") -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def record_transition(
        self,
        *,
        lifecycle_id: str,
        state: OrderLifecycleState | str,
        symbol: str,
        order_role: str = ENTRY,
        broker_order_id: Optional[int] = None,
        autonomous_trade_id: Optional[str] = None,
        parent_lifecycle_id: Optional[str] = None,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OrderLifecycleEvent:
        event = OrderLifecycleEvent(
            lifecycle_id=lifecycle_id,
            state=OrderLifecycleState(state),
            symbol=symbol,
            order_role=order_role,
            broker_order_id=int(broker_order_id) if broker_order_id is not None else None,
            autonomous_trade_id=autonomous_trade_id,
            parent_lifecycle_id=parent_lifecycle_id,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        self.append(event)
        return event

    def append(self, event: OrderLifecycleEvent) -> None:
        record = {
            "op": "TRANSITION",
            "event": event.to_dict(),
            "ts": _iso(_now()),
        }
        with self._lock:
            os.makedirs(self._path.parent, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str, sort_keys=True))
                fh.write("\n")

    def list_events(self, lifecycle_id: Optional[str] = None) -> List[OrderLifecycleEvent]:
        events: List[OrderLifecycleEvent] = []
        if not self._path.exists():
            return events
        with self._lock:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if record.get("op") != "TRANSITION":
                        continue
                    try:
                        event = OrderLifecycleEvent.from_dict(record.get("event") or {})
                    except (KeyError, TypeError, ValueError):
                        continue
                    if lifecycle_id is None or event.lifecycle_id == lifecycle_id:
                        events.append(event)
        return events

    def current_states(self) -> Dict[str, OrderLifecycleEvent]:
        current: Dict[str, OrderLifecycleEvent] = {}
        for event in self.list_events():
            current[event.lifecycle_id] = event
        return current

    def get_current(self, lifecycle_id: str) -> Optional[OrderLifecycleEvent]:
        return self.current_states().get(lifecycle_id)

    def find_by_broker_order_id(self, broker_order_id: int) -> List[OrderLifecycleEvent]:
        return [
            event for event in self.list_events()
            if event.broker_order_id == int(broker_order_id)
        ]

    def serialise(self, events: Iterable[OrderLifecycleEvent]) -> List[Dict[str, Any]]:
        return [event.to_dict() for event in events]
