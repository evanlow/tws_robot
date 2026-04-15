"""Data management API.

POST /api/data/download   — trigger Yahoo Finance download (async)
GET  /api/data/symbols    — list available historical data files
GET  /api/data/status     — data freshness per symbol
"""

import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

bp = Blueprint("api_data", __name__, url_prefix="/api/data")

# Default data directory relative to project root
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "historical"


@bp.route("/symbols", methods=["GET"])
def list_symbols():
    """Return list of symbols with available historical data."""
    data_dir = _DATA_DIR
    if not data_dir.exists():
        return jsonify({"symbols": [], "data_dir": str(data_dir)})

    symbols = []
    for f in sorted(data_dir.glob("*.csv")):
        stat = f.stat()
        symbols.append({
            "symbol": f.stem.upper(),
            "file": f.name,
            "size_bytes": stat.st_size,
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return jsonify({"symbols": symbols, "count": len(symbols), "data_dir": str(data_dir)})


@bp.route("/status", methods=["GET"])
def data_status():
    """Return freshness status per symbol."""
    data_dir = _DATA_DIR
    if not data_dir.exists():
        return jsonify({"files": []})

    files = []
    now = datetime.now()
    for f in sorted(data_dir.glob("*.csv")):
        modified = datetime.fromtimestamp(f.stat().st_mtime)
        age_days = (now - modified).days
        files.append({
            "symbol": f.stem.upper(),
            "last_modified": modified.isoformat(),
            "age_days": age_days,
            "fresh": age_days < 7,
        })

    return jsonify({"files": files})


@bp.route("/download", methods=["POST"])
def download_data():
    """Trigger historical data download in background.

    Body::

        {
            "symbols": ["AAPL", "MSFT"],
            "period": "1y"
        }
    """
    data = request.get_json(silent=True) or {}
    symbols = data.get("symbols", [])
    period = data.get("period", "1y")

    if not symbols:
        return jsonify({"error": "symbols list is required"}), 400

    thread = threading.Thread(
        target=_download_thread,
        args=(symbols, period),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "status": "downloading",
        "symbols": symbols,
        "period": period,
    }), 202


def _download_thread(symbols, period):
    """Download data in background."""
    try:
        from scripts.download_real_data import download_multiple_symbols
        download_multiple_symbols(symbols, period=period)
        logger.info("Data download complete for %s", symbols)
    except ImportError:
        logger.warning("download_real_data module not available")
    except Exception as exc:
        logger.error("Data download failed: %s", exc)
