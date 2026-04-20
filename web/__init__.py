"""Flask web UI package for TWS Robot.

Factory function ``create_app`` builds the application, registers blueprints
for each menu section, and returns a configured Flask instance.

Usage (development)::

    flask --app web.app run --debug

Or via ``scripts/run_web.py``.
"""

from flask import Flask  # noqa: F401 – imported by callers via ``from web import create_app``


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
    app.config.setdefault("SECRET_KEY", "dev-secret-change-in-production")
    app.config.setdefault("DEBUG", False)
    if config_override:
        app.config.update(config_override)

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

    # ---- JSON API blueprints ----
    from web.routes.api_connection import bp as api_connection_bp
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

    app.register_blueprint(api_connection_bp)
    app.register_blueprint(api_account_bp)
    app.register_blueprint(api_emergency_bp)
    app.register_blueprint(api_strategies_bp)
    app.register_blueprint(api_orders_bp)
    app.register_blueprint(api_events_bp)
    app.register_blueprint(api_system_bp)
    app.register_blueprint(api_backtest_bp)
    app.register_blueprint(api_data_bp)
    app.register_blueprint(api_market_bp)
    app.register_blueprint(api_portfolio_analysis_bp)
    app.register_blueprint(portfolio_analysis_bp)
    app.register_blueprint(api_account_intelligence_bp)

    return app
