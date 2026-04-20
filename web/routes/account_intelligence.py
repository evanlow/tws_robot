"""Account Intelligence page route — unified view of account health,
cash management, opportunity detection, and more.

GET /account-intelligence  →  renders templates/account_intelligence/index.html
"""

from flask import Blueprint, render_template

from web.services import get_services

bp = Blueprint("account_intelligence", __name__, url_prefix="/account-intelligence")


@bp.route("/")
def index():
    """Account Intelligence dashboard — pulls summary data server-side,
    delegates detail fetching to client-side JS via the /api/intelligence/* endpoints."""
    svc = get_services()
    risk_summary = svc.risk_manager.get_risk_summary()

    context = {
        "title": "Account Intelligence",
        "active_page": "account_intelligence",
        "connected": svc.connected,
        "risk_summary": risk_summary,
    }
    return render_template("account_intelligence/index.html", **context)
