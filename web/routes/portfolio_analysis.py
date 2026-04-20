"""Portfolio Analysis page route — enhanced portfolio intelligence UI.

GET /portfolio-analysis  →  Portfolio analysis dashboard with strategy
                            deductions, allocation chart, and deep-dive
                            capability.
"""

from flask import Blueprint, render_template

from web.services import get_services

bp = Blueprint("portfolio_analysis", __name__, url_prefix="/portfolio-analysis")


@bp.route("/")
def index():
    svc = get_services()
    positions = svc.get_positions()
    risk_summary = svc.risk_manager.get_risk_summary()

    context = {
        "title": "Portfolio Insights",
        "active_page": "portfolio_analysis",
        "positions": positions,
        "risk_summary": risk_summary,
        "position_count": len(positions),
    }
    return render_template("portfolio_analysis/index.html", **context)
