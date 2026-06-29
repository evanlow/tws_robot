"""Flask web UI package for TWS Robot.

Factory function ``create_app`` builds the application, registers blueprints
for each menu section, and returns a configured Flask instance.

Usage (development)::

    flask --app web.app run --debug

Or via ``scripts/run_web.py``.
"""

import os

from flask import Flask  # noqa: F401 – imported by callers via ``from web import create_app``

_DEFAULT_SECRET = "dev-secret-change-in-production"


def create_app(config_override: dict | None = None) -> "Flask":
    """Application factory.

    Args:
        config_override: Optional dict of Flask config values (useful in tests).

    Returns:
        Configured Flask application instance.
    """
    from flask import Flask

    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Load .env so OPENAI_API_KEY and other secrets are available early.
    # Skip during tests to avoid non-deterministic behaviour from local .env files.
    # Use override=True so .env values always win over stale shell env vars
    # (e.g. env vars blanked out by a prior test run in the same terminal).
    if not (config_override or {}).get("TESTING"):
        from dotenv import load_dotenv
        load_dotenv(override=True)
    secret_from_env = os.environ.get("SECRET_KEY")
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = secret_from_env or _DEFAULT_SECRET
    app.config.setdefault("DEBUG", False)
    if config_override:
        app.config.update(config_override)

    # Enforce secure SECRET_KEY in production
    _enforce_secret_key(app)

    # ---- CSRF protection (Flask-WTF) ----
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)

    # ---- Authentication ----
    from web.auth import init_auth
    init_auth(app)

    # ---- Runtime safety guards ----
    # The live dry-run path intentionally avoids attaching a live TWS adapter;
    # install a reconciliation guard so rehearsal remains order-free but does
    # not fail before returning a DRY_RUN result.
    from execution.live_dry_run_guard import install_live_dry_run_reconciliation_guard
    install_live_dry_run_reconciliation_guard()

    # Singleton service manager — shared across all routes
    from web.services import ServiceManager
    if "services" not in app.config:
        app.config["services"] = ServiceManager()

    # Context processor: inject status bar data into every template
    @app.context_processor
    def inject_status_bar():
        svc = app.config["services"]
        return {
            "connected": svc.connected,
            "environment": svc.connection_env or "disconnected",
            "account_data_ready": svc.account_data_ready,
            "risk_summary": svc.risk_manager.get_risk_summary(),
        }

    # ---- Page blueprints (server-rendered HTML) ----
    from web.routes.dashboard import bp as dashboard_bp
    from web.routes.strategies import bp as strategies_bp
    from web.routes.backtest import bp as backtest_bp
    from web.routes.positions import bp as positions_bp
    from web.routes.risk import bp as risk_bp
    from web.routes.logs import bp as logs_bp
    from web.routes.settings import bp as settings_bp
    from web.routes.ai_chat import bp as ai_chat_bp
    from web.routes.ai_strategy import bp as ai_strategy_bp
    from web.routes.account_intelligence import bp as account_intelligence_bp
    from web.routes.fx_research import bp as fx_research_bp
    from web.routes.stock_analysis import bp as stock_analysis_bp
    from web.routes.sp500_screener import bp as sp500_screener_bp
    from web.routes.sti_screener import bp as sti_screener_bp
    from web.routes.hsi_screener import bp as hsi_screener_bp
    from web.routes.autonomous_trading import bp as autonomous_trading_bp
    from web.routes.maintenance import bp as maintenance_bp
    from web.routes.api_opening_range import page_bp as opening_range_page_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(strategies_bp)
    app.register_blueprint(backtest_bp)
    app.register_blueprint(positions_bp)
    app.register_blueprint(risk_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(ai_chat_bp)
    app.register_blueprint(ai_strategy_bp)
    app.register_blueprint(account_intelligence_bp)
    app.register_blueprint(fx_research_bp)
    app.register_blueprint(stock_analysis_bp)
    app.register_blueprint(sp500_screener_bp)
    app.register_blueprint(sti_screener_bp)
    app.register_blueprint(hsi_screener_bp)
    app.register_blueprint(autonomous_trading_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(opening_range_page_bp)

    # ---- JSON API blueprints ----
    # Session-authenticated API requests remain CSRF-protected and the web
    # client sends the token via the X-CSRFToken header for state-changing
    # requests.
    from web.routes.api_connection import bp as api_connection_bp
    from web.routes.api_disclaimer import bp as api_disclaimer_bp
    from web.routes.api_account import bp as api_account_bp
    from web.routes.api_emergency import bp as api_emergency_bp
    from web.routes.api_strategies import bp as api_strategies_bp
    from web.routes.api_orders import bp as api_orders_bp
    from web.routes.api_events import bp as api_events_bp
    from web.routes.api_system import bp as api_system_bp
    from web.routes.api_backtest import bp as api_backtest_bp
    from web.routes.api_data import bp as api_data_bp
    from web.routes.api_market import bp as api_market_bp
    from web.routes.api_portfolio_analysis import bp as api_portfolio_analysis_bp
    from web.routes.portfolio_analysis import bp as portfolio_analysis_bp
    from web.routes.api_account_intelligence import bp as api_account_intelligence_bp
    from web.routes.api_market_events import bp as api_market_events_bp
    from web.routes.api_stock_analysis import bp as api_stock_analysis_bp
    from web.routes.api_sp500_screener import bp as api_sp500_screener_bp
    from web.routes.api_sti_screener import bp as api_sti_screener_bp
    from web.routes.api_hsi_screener import bp as api_hsi_screener_bp
    from web.routes.api_autonomous import bp as api_autonomous_bp
    from web.routes.api_trading_readiness import bp as api_trading_readiness_bp
    from web.routes.api_autonomous_evidence import bp as api_autonomous_evidence_bp
    from web.routes.api_maintenance import bp as api_maintenance_bp
    from web.routes.api_opening_range import bp as api_opening_range_bp
    from web.routes.api_opening_range import orb_bp as api_orb_bp

    # Patch the default autonomous market provider so the existing SPY gate
    # receives VIX values as an additional regime/sizing safeguard. Operator
    # overrides via app.config['autonomous_spy_price_provider'] still win.
    from web.vix_market_data import install_spy_vix_provider
    install_spy_vix_provider()

    api_blueprints = [
        api_connection_bp, api_disclaimer_bp, api_account_bp, api_emergency_bp,
        api_strategies_bp, api_orders_bp, api_events_bp,
        api_system_bp, api_backtest_bp, api_data_bp, api_market_bp,
        api_portfolio_analysis_bp, api_account_intelligence_bp,
        api_market_events_bp, api_stock_analysis_bp, api_sp500_screener_bp,
        api_sti_screener_bp, api_hsi_screener_bp, api_autonomous_bp,
        api_trading_readiness_bp, api_autonomous_evidence_bp,
        api_maintenance_bp, api_opening_range_bp, api_orb_bp,
    ]
    for api_bp in api_blueprints:
        app.register_blueprint(api_bp)

    app.register_blueprint(portfolio_analysis_bp)

    return app


def _is_production() -> bool:
    """Return True if ENVIRONMENT is set to 'production'."""
    return os.environ.get("ENVIRONMENT", "").lower() == "production"


def _enforce_secret_key(app) -> None:
    """Fail fast if production is running with an insecure SECRET_KEY."""
    if app.config.get("TESTING"):
        return

    if not _is_production():
        return

    secret_key = app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY must be set in production. "
            "Set the SECRET_KEY environment variable to a secure random value."
        )

    if secret_key == _DEFAULT_SECRET:
        raise RuntimeError(
            "Default SECRET_KEY cannot be used in production. "
            "Set the SECRET_KEY environment variable to a secure random value."
        )
