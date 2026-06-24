"""System Maintenance API.

GET  /api/maintenance/status
POST /api/maintenance/run
GET  /api/maintenance/reports
GET  /api/maintenance/reports/<report_id>
"""

from __future__ import annotations

import logging
from typing import Iterable, List

from flask import Blueprint, jsonify, request

from web.maintenance.runner import MaintenanceRunner
from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_maintenance", __name__, url_prefix="/api/maintenance")


def _runner() -> MaintenanceRunner:
    return MaintenanceRunner()


@bp.route("/status", methods=["GET"])
def status():
    """Return constituent file health and recent report summaries."""
    try:
        return jsonify(_runner().get_status())
    except Exception as exc:
        logger.error("Maintenance status failed: %s", exc, exc_info=True)
        return jsonify({"error": "Maintenance status could not be loaded."}), 500


@bp.route("/run", methods=["POST"])
def run():
    """Run selected maintenance tasks.

    Request JSON:
        tasks: list[str]
        dry_run: bool, default True
        event_symbols: list[str], optional
        days_ahead: int, default 28
        allow_large_change: bool, default False
    """
    payload = request.get_json(silent=True) or {}
    tasks = payload.get("tasks") or None
    if isinstance(tasks, str):
        tasks = [tasks]
    if tasks is not None and not isinstance(tasks, list):
        return jsonify({"error": "tasks must be a string or list of strings"}), 400

    dry_run = bool(payload.get("dry_run", True))
    days_ahead = _bounded_int(payload.get("days_ahead"), default=28, minimum=1, maximum=90)
    event_symbols = _csv_or_list(payload.get("event_symbols"))
    include_portfolio = bool(payload.get("include_portfolio_symbols", True))
    if include_portfolio:
        event_symbols.extend(_portfolio_symbols())

    try:
        report = _runner().run(
            tasks=tasks,
            dry_run=dry_run,
            event_symbols=sorted(set(event_symbols)),
            days_ahead=days_ahead,
            allow_large_change=bool(payload.get("allow_large_change", False)),
        )
        status_code = 200 if report.status != "failed" else 422
        return jsonify(report.to_dict()), status_code
    except Exception as exc:
        logger.error("Maintenance run failed: %s", exc, exc_info=True)
        return jsonify({"error": "Maintenance run could not be completed.", "detail": str(exc)}), 500


@bp.route("/reports", methods=["GET"])
def reports():
    """Return recent maintenance report summaries."""
    limit = _bounded_int(request.args.get("limit"), default=20, minimum=1, maximum=100)
    return jsonify({"reports": _runner().list_reports(limit=limit)})


@bp.route("/reports/<report_id>", methods=["GET"])
def report_detail(report_id: str):
    """Return one maintenance report by id."""
    report = _runner().read_report(report_id)
    if report is None:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(report)


def _bounded_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _csv_or_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items: Iterable[str] = value.split(",")
    elif isinstance(value, list):
        raw_items = (str(item) for item in value)
    else:
        return []
    return [item.strip().upper() for item in raw_items if item and item.strip()]


def _portfolio_symbols() -> List[str]:
    symbols = set()
    try:
        app_svc = get_services()
        for sym in app_svc.get_positions():
            symbols.add(str(sym).upper())
        for strategy in app_svc.strategy_registry.get_all_strategies():
            for sym in (strategy.config.symbols or []):
                symbols.add(str(sym).upper())
    except Exception:
        pass
    return sorted(symbols)
