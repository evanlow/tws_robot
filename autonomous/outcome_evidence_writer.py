"""Append realized outcome records to the autonomous evidence log."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from autonomous.evidence_store import SCHEMA_VERSION

logger = logging.getLogger(__name__)


class OutcomeEvidenceWriter:
    """Small append-only writer for autonomous outcome records."""

    def __init__(self, log_dir: str = "logs") -> None:
        self._log_dir = Path(log_dir)
        self._lock = threading.Lock()

    def _path_for(self, when: datetime) -> Path:
        return self._log_dir / f"autonomous_evidence_{when:%Y%m%d}.jsonl"

    def append_outcome(
        self,
        outcome_record: Dict[str, Any],
        *,
        when: Optional[datetime] = None,
    ) -> Optional[Path]:
        moment = when or datetime.now(timezone.utc)
        record = dict(outcome_record)
        record.setdefault("schema_version", SCHEMA_VERSION)
        record.setdefault("evidence_type", "autonomous_outcome")
        record.setdefault("timestamp", moment.isoformat())
        path = self._path_for(moment)
        try:
            with self._lock:
                os.makedirs(self._log_dir, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, default=str, sort_keys=True) + "\n")
            return path
        except OSError as exc:
            logger.error("Failed to write outcome evidence log: %s", exc)
            return None
