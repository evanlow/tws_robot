"""Portfolio Persistence — storage for portfolio snapshots and analysis cache.

Provides functions to:
- Save and retrieve periodic portfolio snapshots
- Cache fundamentals and AI analysis results with TTL
- Store and query stock deep-dive analyses

Uses SQLAlchemy ORM models so the persistence layer works with any
database backend supported by the project (SQLite, PostgreSQL, etc.).

All functions use the existing :mod:`data.database` singleton to get a
database session.

Usage::

    from data.portfolio_persistence import (
        save_portfolio_snapshot,
        get_latest_snapshot,
        cache_fundamentals,
        get_cached_fundamentals,
    )
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from data.models import PortfolioSnapshot, StockAnalysis, FundamentalsCache

logger = logging.getLogger(__name__)


def _get_db():
    """Lazy import of the database singleton."""
    from data.database import get_database
    return get_database()


# ---------------------------------------------------------------------------
# Portfolio Snapshots
# ---------------------------------------------------------------------------

def save_portfolio_snapshot(
    total_equity: float,
    cash: float,
    positions: List[Dict[str, Any]],
    strategy_mix: Optional[Dict[str, float]] = None,
    analysis: Optional[Dict[str, Any]] = None,
) -> int:
    """Persist a point-in-time portfolio snapshot.

    Returns the row ID of the inserted snapshot.
    """
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()

    snapshot = PortfolioSnapshot(
        timestamp=now,
        total_equity=total_equity,
        cash=cash,
        positions_json=json.dumps(positions, default=str),
        strategy_mix_json=json.dumps(strategy_mix, default=str) if strategy_mix else None,
        analysis_json=json.dumps(analysis, default=str) if analysis else None,
    )

    with db.session_scope() as session:
        session.add(snapshot)
        session.flush()
        return snapshot.id


def get_latest_snapshot() -> Optional[Dict[str, Any]]:
    """Return the most recent portfolio snapshot, or None."""
    db = _get_db()

    with db.session_scope() as session:
        row = (
            session.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .first()
        )
        if row is None:
            return None
        return _snapshot_to_dict(row)


def get_snapshot_history(limit: int = 30) -> List[Dict[str, Any]]:
    """Return the last *limit* portfolio snapshots, newest first."""
    db = _get_db()

    with db.session_scope() as session:
        rows = (
            session.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [_snapshot_to_dict(r) for r in rows]


def _snapshot_to_dict(row: PortfolioSnapshot) -> Dict[str, Any]:
    return {
        "id": row.id,
        "timestamp": row.timestamp,
        "total_equity": row.total_equity,
        "cash": row.cash,
        "positions": json.loads(row.positions_json) if row.positions_json else [],
        "strategy_mix": json.loads(row.strategy_mix_json) if row.strategy_mix_json else {},
        "analysis": json.loads(row.analysis_json) if row.analysis_json else None,
    }


# ---------------------------------------------------------------------------
# Stock Analysis Persistence
# ---------------------------------------------------------------------------

def save_stock_analysis(
    symbol: str,
    fundamentals: Optional[Dict[str, Any]] = None,
    technical: Optional[Dict[str, Any]] = None,
    ai_analysis: Optional[Dict[str, Any]] = None,
    verdict: Optional[str] = None,
) -> int:
    """Persist a stock deep-dive analysis. Returns the row ID."""
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()

    record = StockAnalysis(
        symbol=symbol,
        analysis_date=now,
        fundamentals_json=json.dumps(fundamentals, default=str) if fundamentals else None,
        technical_json=json.dumps(technical, default=str) if technical else None,
        ai_analysis_json=json.dumps(ai_analysis, default=str) if ai_analysis else None,
        verdict=verdict,
    )

    with db.session_scope() as session:
        session.add(record)
        session.flush()
        return record.id


def get_latest_stock_analysis(
    symbol: str,
    max_age_seconds: int = 14400,
) -> Optional[Dict[str, Any]]:
    """Return the most recent analysis for *symbol* if within TTL.

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    max_age_seconds : int
        Maximum age in seconds (default 4 hours).

    Returns
    -------
    dict or None
    """
    db = _get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()

    with db.session_scope() as session:
        row = (
            session.query(StockAnalysis)
            .filter(StockAnalysis.symbol == symbol, StockAnalysis.analysis_date > cutoff)
            .order_by(StockAnalysis.analysis_date.desc())
            .first()
        )
        if row is None:
            return None
        return _analysis_to_dict(row)


def get_stock_analysis_history(
    symbol: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return historical analyses for *symbol*, newest first."""
    db = _get_db()

    with db.session_scope() as session:
        rows = (
            session.query(StockAnalysis)
            .filter(StockAnalysis.symbol == symbol)
            .order_by(StockAnalysis.analysis_date.desc())
            .limit(limit)
            .all()
        )
        return [_analysis_to_dict(r) for r in rows]


def _analysis_to_dict(row: StockAnalysis) -> Dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "analysis_date": row.analysis_date,
        "fundamentals": json.loads(row.fundamentals_json) if row.fundamentals_json else None,
        "technical": json.loads(row.technical_json) if row.technical_json else None,
        "ai_analysis": json.loads(row.ai_analysis_json) if row.ai_analysis_json else None,
        "verdict": row.verdict,
    }


# ---------------------------------------------------------------------------
# Fundamentals Cache
# ---------------------------------------------------------------------------

def cache_fundamentals(symbol: str, data: Dict[str, Any]) -> None:
    """Store fundamentals data in the cache table."""
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()

    with db.session_scope() as session:
        # Delete old entries for this symbol
        session.query(FundamentalsCache).filter(
            FundamentalsCache.symbol == symbol
        ).delete()
        # Insert new data
        session.add(FundamentalsCache(
            symbol=symbol,
            data_json=json.dumps(data, default=str),
            fetched_at=now,
        ))


def get_cached_fundamentals(
    symbol: str,
    ttl_seconds: int = 86400,
) -> Optional[Dict[str, Any]]:
    """Retrieve cached fundamentals if available and within TTL.

    Returns None if no cached data exists or if it's stale.
    """
    db = _get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)).isoformat()

    with db.session_scope() as session:
        row = (
            session.query(FundamentalsCache)
            .filter(FundamentalsCache.symbol == symbol, FundamentalsCache.fetched_at > cutoff)
            .order_by(FundamentalsCache.fetched_at.desc())
            .first()
        )
        if row is None:
            return None
        return json.loads(row.data_json)
