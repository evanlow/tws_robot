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

    # Default configuration
    app.config.setdefault("SECRET_KEY", "dev-secret-change-in-production")
    app.config.setdefault("DEBUG", False)
    if config_override:
        app.config.update(config_override)

    # Register blueprints (one per menu section)
    from web.routes.dashboard import bp as dashboard_bp
    from web.routes.strategies import bp as strategies_bp
    from web.routes.backtest import bp as backtest_bp
    from web.routes.positions import bp as positions_bp
    from web.routes.risk import bp as risk_bp
    from web.routes.logs import bp as logs_bp
    from web.routes.settings import bp as settings_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(strategies_bp)
    app.register_blueprint(backtest_bp)
    app.register_blueprint(positions_bp)
    app.register_blueprint(risk_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(settings_bp)

    return app
