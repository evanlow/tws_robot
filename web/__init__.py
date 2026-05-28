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
    if not (config_override or {}).get("TESTING"):
        from dotenv import load_dotenv
        load_dotenv()

    # Default configuration
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

    api_blueprints = [
        api_connection_bp, api_disclaimer_bp, api_account_bp, api_emergency_bp,
        api_strategies_bp, api_orders_bp, api_events_bp,
        api_system_bp, api_backtest_bp, api_data_bp, api_market_bp,
        api_portfolio_analysis_bp, api_account_intelligence_bp,
        api_market_events_bp,
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
