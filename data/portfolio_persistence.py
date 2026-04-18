"""Portfolio Persistence — SQLite storage for portfolio snapshots and analysis cache.

Provides functions to:
- Save and retrieve periodic portfolio snapshots
- Cache fundamentals and AI analysis results with TTL
- Store and query stock deep-dive analyses

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

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _get_db():
    """Lazy import of the database singleton."""
    from data.database import get_database
    return get_database()


def _ensure_tables() -> None:
    """Create the portfolio analytics tables if they don't exist.

    Uses raw SQL so it works with both SQLite and PostgreSQL without
    depending on the ORM models (which may not have been imported yet).
    """
    db = _get_db()

    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            total_equity REAL DEFAULT 0.0,
            cash REAL DEFAULT 0.0,
            positions_json TEXT,
            strategy_mix_json TEXT,
            analysis_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS stock_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            analysis_date TEXT NOT NULL,
            fundamentals_json TEXT,
            technical_json TEXT,
            ai_analysis_json TEXT,
            verdict TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fundamentals_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            data_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """,
    ]

    # Index creation (safe to run repeatedly with IF NOT EXISTS)
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_ts ON portfolio_snapshots(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_stock_analyses_symbol ON stock_analyses(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_stock_analyses_date ON stock_analyses(analysis_date)",
        "CREATE INDEX IF NOT EXISTS idx_fundamentals_cache_symbol ON fundamentals_cache(symbol)",
    ]

    with db.engine.connect() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
        for idx in index_statements:
            conn.execute(text(idx))
        conn.commit()


# Module-level flag to ensure tables are created only once per process.
_tables_ensured = False


def _ensure_tables_once() -> None:
    global _tables_ensured
    if not _tables_ensured:
        _ensure_tables()
        _tables_ensured = True


def reset_tables_flag() -> None:
    """Reset the once-per-process table creation flag (for testing)."""
    global _tables_ensured
    _tables_ensured = False


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
    _ensure_tables_once()
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()

    with db.engine.connect() as conn:
        result = conn.execute(
            text(
                "INSERT INTO portfolio_snapshots "
                "(timestamp, total_equity, cash, positions_json, strategy_mix_json, analysis_json) "
                "VALUES (:ts, :equity, :cash, :pos, :mix, :analysis)"
            ),
            {
                "ts": now,
                "equity": total_equity,
                "cash": cash,
                "pos": json.dumps(positions, default=str),
                "mix": json.dumps(strategy_mix, default=str) if strategy_mix else None,
                "analysis": json.dumps(analysis, default=str) if analysis else None,
            },
        )
        conn.commit()
        return result.lastrowid or 0


def get_latest_snapshot() -> Optional[Dict[str, Any]]:
    """Return the most recent portfolio snapshot, or None."""
    _ensure_tables_once()
    db = _get_db()

    with db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 1")
        ).mappings().first()
        if row is None:
            return None
        return _snapshot_row_to_dict(row)


def get_snapshot_history(limit: int = 30) -> List[Dict[str, Any]]:
    """Return the last *limit* portfolio snapshots, newest first."""
    _ensure_tables_once()
    db = _get_db()

    with db.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_snapshot_row_to_dict(r) for r in rows]


def _snapshot_row_to_dict(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "total_equity": row["total_equity"],
        "cash": row["cash"],
        "positions": json.loads(row["positions_json"]) if row["positions_json"] else [],
        "strategy_mix": json.loads(row["strategy_mix_json"]) if row["strategy_mix_json"] else {},
        "analysis": json.loads(row["analysis_json"]) if row["analysis_json"] else None,
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
    _ensure_tables_once()
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()

    with db.engine.connect() as conn:
        result = conn.execute(
            text(
                "INSERT INTO stock_analyses "
                "(symbol, analysis_date, fundamentals_json, technical_json, ai_analysis_json, verdict) "
                "VALUES (:sym, :date, :fund, :tech, :ai, :verdict)"
            ),
            {
                "sym": symbol,
                "date": now,
                "fund": json.dumps(fundamentals, default=str) if fundamentals else None,
                "tech": json.dumps(technical, default=str) if technical else None,
                "ai": json.dumps(ai_analysis, default=str) if ai_analysis else None,
                "verdict": verdict,
            },
        )
        conn.commit()
        return result.lastrowid or 0


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
    _ensure_tables_once()
    db = _get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()

    with db.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT * FROM stock_analyses "
                "WHERE symbol = :sym AND analysis_date > :cutoff "
                "ORDER BY analysis_date DESC LIMIT 1"
            ),
            {"sym": symbol, "cutoff": cutoff},
        ).mappings().first()
        if row is None:
            return None
        return _analysis_row_to_dict(row)


def get_stock_analysis_history(
    symbol: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return historical analyses for *symbol*, newest first."""
    _ensure_tables_once()
    db = _get_db()

    with db.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT * FROM stock_analyses "
                "WHERE symbol = :sym ORDER BY analysis_date DESC LIMIT :lim"
            ),
            {"sym": symbol, "lim": limit},
        ).mappings().all()
        return [_analysis_row_to_dict(r) for r in rows]


def _analysis_row_to_dict(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "analysis_date": row["analysis_date"],
        "fundamentals": json.loads(row["fundamentals_json"]) if row["fundamentals_json"] else None,
        "technical": json.loads(row["technical_json"]) if row["technical_json"] else None,
        "ai_analysis": json.loads(row["ai_analysis_json"]) if row["ai_analysis_json"] else None,
        "verdict": row["verdict"],
    }


# ---------------------------------------------------------------------------
# Fundamentals Cache
# ---------------------------------------------------------------------------

def cache_fundamentals(symbol: str, data: Dict[str, Any]) -> None:
    """Store fundamentals data in the cache table."""
    _ensure_tables_once()
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()

    with db.engine.connect() as conn:
        # Delete old entries for this symbol
        conn.execute(
            text("DELETE FROM fundamentals_cache WHERE symbol = :sym"),
            {"sym": symbol},
        )
        # Insert new data
        conn.execute(
            text(
                "INSERT INTO fundamentals_cache (symbol, data_json, fetched_at) "
                "VALUES (:sym, :data, :ts)"
            ),
            {"sym": symbol, "data": json.dumps(data, default=str), "ts": now},
        )
        conn.commit()


def get_cached_fundamentals(
    symbol: str,
    ttl_seconds: int = 86400,
) -> Optional[Dict[str, Any]]:
    """Retrieve cached fundamentals if available and within TTL.

    Returns None if no cached data exists or if it's stale.
    """
    _ensure_tables_once()
    db = _get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)).isoformat()

    with db.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT data_json FROM fundamentals_cache "
                "WHERE symbol = :sym AND fetched_at > :cutoff "
                "ORDER BY fetched_at DESC LIMIT 1"
            ),
            {"sym": symbol, "cutoff": cutoff},
        ).mappings().first()
        if row is None:
            return None
        return json.loads(row["data_json"])
