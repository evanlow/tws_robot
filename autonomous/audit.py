"""JSONL audit log for autonomous trading decisions.

Every run of :class:`autonomous.autonomous_engine.AutonomousTradingEngine`
appends exactly one line to ``logs/autonomous_trading_YYYYMMDD.jsonl``,
recording the full decision context regardless of outcome (executed
trades **and** rejections).

The log is deliberately append-only JSONL so it can be consumed by
external tools and rotated by date with no extra machinery.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    """Append-only JSONL writer for autonomous-trading decisions.

    Thread-safe (uses an internal lock around file writes).  Creates the
    target directory if it does not exist; if writing fails for any
    reason the error is logged but never raised — the audit log must
    never break trading.
    """

    def __init__(self, log_dir: str = "logs") -> None:
        self._log_dir = Path(log_dir)
        self._lock = threading.Lock()

    def _path_for(self, when: datetime) -> Path:
        return self._log_dir / f"autonomous_trading_{when:%Y%m%d}.jsonl"

    def count_executions_on(
        self,
        when: Optional[datetime] = None,
        statuses: Optional[tuple] = None,
    ) -> int:
        """Return how many decisions on ``when``'s date have a status in
        ``statuses`` (defaults to the set of execution outcomes).

        Used by :class:`autonomous.autonomous_engine.AutonomousTradingEngine`
        to enforce ``max_trades_per_day`` across process restarts: the
        audit log is the system of record for what has been traded today.
        Missing or unreadable files count as zero (defensive — the
        engine must never crash because the audit log is unavailable).
        """
        moment = when or datetime.now(timezone.utc)
        statuses = statuses or ("paper_executed", "live_executed")
        path = self._path_for(moment)
        if not path.exists():
            return 0
        count = 0
        try:
            with self._lock:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        decision = record.get("decision") or {}
                        if decision.get("status") in statuses:
                            count += 1
        except OSError as exc:  # pragma: no cover - defensive
            logger.error("Failed to read autonomous audit log: %s", exc)
            return 0
        return count

    def log_decision(
        self,
        record: Dict[str, Any],
        when: Optional[datetime] = None,
    ) -> Optional[Path]:
        """Append ``record`` to today's JSONL log.

        Returns the file path written to (useful for tests), or ``None``
        on failure.
        """
        moment = when or datetime.now(timezone.utc)
        record = dict(record)  # don't mutate caller's dict
        record.setdefault("timestamp", moment.isoformat())

        path = self._path_for(moment)
        try:
            with self._lock:
                os.makedirs(self._log_dir, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, default=str, sort_keys=True))
                    fh.write("\n")
            return path
        except OSError as exc:  # pragma: no cover - defensive
            logger.error("Failed to write autonomous audit log: %s", exc)
            return None
