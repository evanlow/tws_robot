"""Trade lifecycle store for autonomous paper trades.

Persists :class:`AutonomousTrade` records to an append-only JSONL file
(``logs/autonomous_trades.jsonl`` by default).  Each line is a single
JSON object representing either a full snapshot (``op == "OPEN"``) or
a delta update (``op == "UPDATE"``) keyed by
``autonomous_trade_id``.  Reading replays the log in order so the
latest non-null value for every field wins.

This is deliberately MVP-simple — JSONL keeps it consistent with the
existing autonomous audit log and avoids introducing a new database
dependency.  Malformed lines are tolerated and skipped so a partial
write can never break the runner.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


# Lifecycle states ----------------------------------------------------------

OPEN = "OPEN"
EXIT_PENDING = "EXIT_PENDING"
CLOSED = "CLOSED"
FAILED = "FAILED"

VALID_STATUSES = (OPEN, EXIT_PENDING, CLOSED, FAILED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


@dataclass
class AutonomousTrade:
    """Lifecycle record for a single autonomous paper trade."""

    autonomous_trade_id: str
    symbol: str
    trade_type: str          # MVP: BUY_SHARES only
    status: str              # OPEN, EXIT_PENDING, CLOSED, FAILED
    entry_order_id: int
    entry_time: datetime
    entry_limit_price: float
    quantity: int
    entry_filled_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    max_holding_days: int = 5
    exit_order_id: Optional[int] = None
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    realised_pnl: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    # Bracket child IDs (live trades only) — used by AutonomousLiveRunner
    # to reconcile a target/stop fill into a CLOSED status.
    target_order_id: Optional[int] = None
    stop_order_id: Optional[int] = None

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["entry_time"] = _iso(self.entry_time)
        data["exit_time"] = _iso(self.exit_time)
        return data

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AutonomousTrade":
        kwargs = dict(payload)
        for key in ("entry_time", "exit_time"):
            value = kwargs.get(key)
            if isinstance(value, str):
                try:
                    kwargs[key] = datetime.fromisoformat(value)
                except ValueError:
                    kwargs[key] = None
        # Drop unknown keys defensively so future-extended logs don't
        # crash older readers.
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in kwargs.items() if k in known}
        return cls(**kwargs)


class TradeStore:
    """Append-only JSONL persistence for :class:`AutonomousTrade`.

    Thread-safe; tolerates malformed JSONL lines.  Updates are written
    as small delta records ``{"op": "UPDATE", "autonomous_trade_id": ...,
    "fields": {...}}`` so a partial write can never lose previous
    snapshots.
    """

    def __init__(self, path: str = "logs/autonomous_trades.jsonl") -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Path helper (test introspection)
    # ------------------------------------------------------------------
    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def record_trade(self, trade: AutonomousTrade) -> None:
        """Append a full ``OPEN`` snapshot for a freshly opened trade."""
        record = {
            "op": "OPEN",
            "autonomous_trade_id": trade.autonomous_trade_id,
            "snapshot": trade.to_dict(),
            "ts": _iso(_now()),
        }
        self._append(record)

    def update_trade(
        self,
        autonomous_trade_id: str,
        **fields: Any,
    ) -> None:
        """Append a delta update for an existing trade.

        Only the supplied fields are written.  Caller is responsible for
        providing JSON-serialisable values (datetimes are normalised to
        ISO strings here as a convenience).
        """
        if not fields:
            return
        normalised: Dict[str, Any] = {}
        for k, v in fields.items():
            if isinstance(v, datetime):
                normalised[k] = _iso(v)
            else:
                normalised[k] = v
        # Validate status if present.
        if "status" in normalised and normalised["status"] not in VALID_STATUSES:
            raise ValueError(
                f"invalid status {normalised['status']!r}; expected one of {VALID_STATUSES}"
            )
        record = {
            "op": "UPDATE",
            "autonomous_trade_id": autonomous_trade_id,
            "fields": normalised,
            "ts": _iso(_now()),
        }
        self._append(record)

    def _append(self, record: Dict[str, Any]) -> None:
        try:
            with self._lock:
                os.makedirs(self._path.parent, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, default=str, sort_keys=True))
                    fh.write("\n")
        except OSError as exc:  # pragma: no cover - defensive
            logger.error("Failed to write autonomous trade store: %s", exc)

    # ------------------------------------------------------------------
    # Reads (replay)
    # ------------------------------------------------------------------
    def _replay(self) -> Dict[str, Dict[str, Any]]:
        """Replay the JSONL log into ``{trade_id: snapshot_dict}``.

        Malformed JSON lines are skipped (logged at debug level).  This
        guarantees a partial write or a future-extended record can never
        crash callers that just want the current view.
        """
        snapshots: Dict[str, Dict[str, Any]] = {}
        if not self._path.exists():
            return snapshots
        with self._lock:
            try:
                with self._path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except ValueError:
                            logger.debug("trade store: skipping malformed line")
                            continue
                        trade_id = record.get("autonomous_trade_id")
                        if not trade_id:
                            continue
                        op = record.get("op")
                        if op == "OPEN":
                            snap = dict(record.get("snapshot") or {})
                            snap["autonomous_trade_id"] = trade_id
                            snapshots[trade_id] = snap
                        elif op == "UPDATE":
                            existing = snapshots.get(trade_id)
                            if existing is None:
                                # Update arriving before OPEN — start an
                                # empty snapshot so we don't lose data.
                                existing = {"autonomous_trade_id": trade_id}
                                snapshots[trade_id] = existing
                            for k, v in (record.get("fields") or {}).items():
                                existing[k] = v
                        else:
                            # Unknown op — ignore but don't crash.
                            continue
            except OSError as exc:  # pragma: no cover - defensive
                logger.error("Failed to read trade store %s: %s", self._path, exc)
        return snapshots

    def list_all(self) -> List[AutonomousTrade]:
        """Return every trade replayed from the log."""
        out: List[AutonomousTrade] = []
        for snap in self._replay().values():
            try:
                out.append(AutonomousTrade.from_dict(snap))
            except TypeError:
                logger.debug("trade store: dropping incomplete snapshot %r", snap)
                continue
        return out

    def list_open(self) -> List[AutonomousTrade]:
        return [t for t in self.list_all() if t.status == OPEN]

    def list_closed(self) -> List[AutonomousTrade]:
        return [t for t in self.list_all() if t.status == CLOSED]

    def get(self, autonomous_trade_id: str) -> Optional[AutonomousTrade]:
        snap = self._replay().get(autonomous_trade_id)
        if snap is None:
            return None
        try:
            return AutonomousTrade.from_dict(snap)
        except TypeError:
            return None

    def count_open(self) -> int:
        return sum(1 for _ in self.list_open())

    # ------------------------------------------------------------------
    # Bulk helpers (used by API serialisation)
    # ------------------------------------------------------------------
    def serialise(self, trades: Iterable[AutonomousTrade]) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in trades]
