"""ORB Phase 2.7 end-of-session review layer (autonomous/orb_session_review.py, #211).

Builds the trader-facing daily session review on top of the read-only
evidence ledger in :mod:`autonomous.orb_evidence`, and lets an operator attach
notes to a session after the fact. This module never places, routes, or
simulates an order — it only reads the existing audit trail and persists
operator notes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from autonomous.orb_evidence import (
    DEFAULT_COMMISSION_PER_SHARE,
    build_evidence_summary,
    build_session_evidence,
    export_evidence,
)

logger = logging.getLogger(__name__)


def session_id(strategy_name: str, session_date: str) -> str:
    """Stable identifier for a session review: ``<strategy_name>:<session_date>``."""
    return f"{strategy_name}:{session_date}"


def parse_session_id(sid: str) -> Optional[tuple]:
    """Split a ``session_id`` back into ``(strategy_name, session_date)``.

    Splits at the *first* colon to match the simple f-string join used by
    :func:`session_id` (``f"{strategy_name}:{session_date}"``).
    """
    if ":" not in sid:
        return None
    strategy_name, _, session_date = sid.partition(":")
    if not strategy_name or not session_date:
        return None
    return strategy_name, session_date


class ORBSessionReviewStore:
    """Persists operator notes for ORB session reviews and builds reviews.

    Notes are persisted to ``<config_dir>/orb_review_notes.json`` so they
    survive app restarts, matching the persistence pattern used by
    :class:`autonomous.orb_session_manager.ORBSessionManager`. Thread-safe.
    """

    def __init__(self, config_dir: str = "config", evidence_dir: str = "logs") -> None:
        self._config_dir = Path(config_dir)
        self._evidence_dir = Path(evidence_dir)
        self._path = self._config_dir / "orb_review_notes.json"
        self._lock = threading.Lock()
        self._notes: Dict[str, str] = {}
        self._load()

    # ---- persistence ---------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            self._notes = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
            logger.error("Failed to load ORB review notes: %s", exc)

    def _save(self) -> None:
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self._notes, indent=2, sort_keys=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError as exc:  # pragma: no cover - defensive
            logger.error("Failed to save ORB review notes: %s", exc)

    # ---- notes -----------------------------------------------------------
    def add_note(self, sid: str, note: str) -> str:
        """Append an operator note to a session review; returns the full note text."""
        with self._lock:
            existing = self._notes.get(sid, "")
            combined = f"{existing}\n{note}".strip() if existing else str(note)
            self._notes[sid] = combined
            self._save()
            return combined

    def get_notes(self, sid: str) -> str:
        with self._lock:
            return self._notes.get(sid, "")

    # ---- review building ---------------------------------------------------
    def get_review(
        self,
        strategy_name: str,
        session_date: str,
        *,
        symbols_watched: Optional[List[str]] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
        commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE,
    ) -> Dict[str, Any]:
        review = build_session_evidence(
            str(self._evidence_dir), strategy_name, session_date,
            symbols_watched=symbols_watched, config_snapshot=config_snapshot,
            commission_per_share=commission_per_share,
        )
        sid = session_id(strategy_name, session_date)
        review["session_id"] = sid
        review["operator_notes"] = self.get_notes(sid)
        return review

    def list_reviews_for_date(
        self,
        session_date: str,
        strategies: List[Dict[str, Any]],
        *,
        commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE,
    ) -> List[Dict[str, Any]]:
        """Build a review for every configured strategy for a given session date.

        ``strategies`` is the list of strategy config records from
        :class:`autonomous.orb_session_manager.ORBSessionManager.list_strategies`
        (or an equivalent dict with ``name``/``symbols``/``parameters``).
        """
        out = []
        for rec in strategies:
            name = rec.get("name")
            if not name:
                continue
            out.append(self.get_review(
                name, session_date,
                symbols_watched=rec.get("symbols"),
                config_snapshot=rec.get("parameters"),
                commission_per_share=commission_per_share,
            ))
        return out

    def evidence_summary(
        self,
        strategy_name: str,
        *,
        commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE,
    ) -> Dict[str, Any]:
        return build_evidence_summary(
            str(self._evidence_dir), strategy_name, commission_per_share=commission_per_share,
        )

    def export(
        self,
        strategy_name: str,
        fmt: str = "json",
        *,
        commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE,
    ) -> str:
        return export_evidence(
            str(self._evidence_dir), strategy_name, fmt, commission_per_share=commission_per_share,
        )
