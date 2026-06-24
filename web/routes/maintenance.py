"""System Maintenance page route."""

from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")


@bp.route("")
def index():
    """Render the System Maintenance console."""
    return render_template(
        "maintenance/index.html",
        title="System Maintenance",
        active_page="maintenance",
    )
