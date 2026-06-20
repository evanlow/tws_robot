"""Durable evidence store for autonomous trading intelligence.

Audit logs answer "what happened" for operational traceability.  Evidence
records answer "what can we learn from it" for future edge estimation, basket
construction, Kelly/fractional-Kelly sizing, and strategy promotion decisions.

The store is append-only JSONL by date.  It records every autonomous engine
outcome, including no-trade and rejected decisions, because non-trades are part
of the strategy's evidence base.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _safe_get(mapping: Dict[str, Any] | None, *keys: str) -> Any:
    value: Any = mapping or {}
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _strategy_bucket(decision: Dict[str, Any]) -> Dict[str, Any]:
    selected = decision.get("selected") or {}
    candidate = selected.get("candidate") or {}
    extras = candidate.get("extras") or {}
    market_gate = decision.get("market_gate") or {}
    vix = market_gate.get("vix") or {}
    return {
        "signal_label": candidate.get("signal_label"),
        "strength_score": candidate.get("strength_score"),
        "quality_label": extras.get("quality_label"),
        "momentum_label": extras.get("momentum_label"),
        "sector": candidate.get("sector"),
        "market_classification": market_gate.get("classification"),
        "spy_bullish": market_gate.get("bullish"),
        "vix_level_regime": vix.get("level_regime"),
        "vix_direction_regime": vix.get("direction_regime"),
    }


def _planned_risk(decision: Dict[str, Any]) -> Dict[str, Any]:
    plan = decision.get("trade_plan") or {}
    entry = plan.get("limit_price")
    target = plan.get("target_price")
    stop = plan.get("stop_price")
    quantity = plan.get("quantity") or 0
    out: Dict[str, Any] = {
        "entry_price": entry,
        "target_price": target,
        "stop_price": stop,
        "quantity": quantity,
        "required_cash": plan.get("required_cash"),
        "target_mode": plan.get("target_mode"),
    }
    try:
        entry_f = float(entry)
        stop_f = float(stop)
        qty_f = float(quantity)
        if entry_f > 0 and stop_f > 0 and entry_f > stop_f:
            risk_per_share = entry_f - stop_f
            out["risk_per_share"] = round(risk_per_share, 4)
            out["planned_dollar_risk"] = round(risk_per_share * qty_f, 2)
            if target is not None:
                target_f = float(target)
                if target_f > entry_f:
                    reward_per_share = target_f - entry_f
                    out["reward_per_share"] = round(reward_per_share, 4)
                    out["planned_r_multiple"] = round(reward_per_share / risk_per_share, 4)
    except (TypeError, ValueError):
        pass
    return out


class TradeEvidenceStore:
    """Append-only JSONL store for autonomous evidence records."""

    def __init__(self, log_dir: str = "logs") -> None:
        self._log_dir = Path(log_dir)
        self._lock = threading.Lock()

    def _path_for(self, when: datetime) -> Path:
        return self._log_dir / f"autonomous_evidence_{when:%Y%m%d}.jsonl"

    def build_decision_record(
        self,
        audit_record: Dict[str, Any],
        *,
        when: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Build a schema-versioned evidence record from an audit record."""

        moment = when or datetime.now(timezone.utc)
        decision = dict(audit_record.get("decision") or {})
        config = dict(audit_record.get("config") or {})
        selected = decision.get("selected") or {}
        candidate = selected.get("candidate") or {}
        trade_plan = decision.get("trade_plan") or {}

        return {
            "schema_version": SCHEMA_VERSION,
            "evidence_type": "autonomous_decision",
            "timestamp": moment.isoformat(),
            "engine": audit_record.get("engine", "AutonomousTradingEngine"),
            "status": decision.get("status"),
            "mode": decision.get("mode"),
            "rejection_reason": decision.get("rejection_reason"),
            "symbol": candidate.get("symbol") or trade_plan.get("symbol"),
            "strategy_bucket": _strategy_bucket(decision),
            "market_gate": decision.get("market_gate"),
            "cash_snapshot": decision.get("cash_snapshot") or {},
            "deployable_cash": decision.get("deployable_cash"),
            "selected": selected,
            "trade_plan": trade_plan,
            "planned_risk": _planned_risk(decision),
            "risk_check": decision.get("risk_check"),
            "order": {
                "order_id": decision.get("order_id"),
                "status": decision.get("status"),
            },
            "candidate_counts": {
                "shortlist": len(decision.get("shortlist") or []),
                "rejected": len(decision.get("rejected_candidates") or []),
            },
            "shortlist": decision.get("shortlist") or [],
            "rejected_candidates": decision.get("rejected_candidates") or [],
            "notes": decision.get("notes") or [],
            "config_snapshot": config,
            "outcome": {
                "realized": False,
                "exit_price": None,
                "realized_pnl": None,
                "realized_r_multiple": None,
                "exit_reason": None,
            },
        }

    def log_decision(
        self,
        audit_record: Dict[str, Any],
        *,
        when: Optional[datetime] = None,
    ) -> Optional[Path]:
        """Append an evidence record for one autonomous decision."""

        moment = when or datetime.now(timezone.utc)
        record = self.build_decision_record(audit_record, when=moment)
        path = self._path_for(moment)
        try:
            with self._lock:
                os.makedirs(self._log_dir, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, default=str, sort_keys=True))
                    fh.write("\n")
            return path
        except OSError as exc:  # pragma: no cover - defensive
            logger.error("Failed to write autonomous evidence log: %s", exc)
            return None

    def recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent evidence records, newest first.

        Reads date-rotated JSONL files in reverse filename order.  Malformed
        lines are skipped defensively.
        """

        limit = max(1, min(int(limit or 100), 1000))
        if not self._log_dir.exists():
            return []

        records: List[Dict[str, Any]] = []
        paths = sorted(
            self._log_dir.glob("autonomous_evidence_*.jsonl"),
            reverse=True,
        )
        for path in paths:
            try:
                with self._lock:
                    lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(records) >= limit:
                    return records
        return records
