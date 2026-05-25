"""Authentication module for TWS Robot web UI.

Provides:
- Flask-Login integration for session-based authentication.
- A simple single-user model (suitable for a personal trading dashboard).
- Login/logout routes.
- A ``login_required`` guard applied globally via ``before_request``.

Configuration (via environment variables or Flask config):
    TWS_ADMIN_USERNAME  – admin username (default: "admin")
    TWS_ADMIN_PASSWORD  – admin password (required unless TESTING/DEBUG or
                          ALLOW_DEFAULT_PASSWORD is enabled)
    LOGIN_DISABLED      – set to "1" or "true" to bypass auth (local dev only)
"""

import logging
import os

from flask import Blueprint, current_app, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# User model (single-user, in-memory)
# ---------------------------------------------------------------------------


class AdminUser(UserMixin):
    """Represents the single admin user."""

    def __init__(self, username: str):
        self.id = username


# ---------------------------------------------------------------------------
# Login manager setup
# ---------------------------------------------------------------------------

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"
logger = logging.getLogger(__name__)


@login_manager.user_loader
def load_user(user_id: str):
    """Load user by ID (username)."""
    expected = current_app.config.get("TWS_ADMIN_USERNAME", "admin")
    if user_id == expected:
        return AdminUser(user_id)
    return None


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Login page and form handler."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        expected_username = current_app.config.get("TWS_ADMIN_USERNAME", "admin")
        password_hash = current_app.config.get("TWS_ADMIN_PASSWORD_HASH", "")

        if username == expected_username and password_hash and check_password_hash(password_hash, password):
            user = AdminUser(username)
            login_user(user)
            return redirect(url_for("dashboard.index"))
        else:
            error = "Invalid username or password."

    return render_template("login.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    """Log out the current user."""
    logout_user()
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Global auth enforcement
# ---------------------------------------------------------------------------


def init_auth(app):
    """Initialize authentication on the Flask app.

    Call this in the application factory after config is loaded.
    """
    # Resolve admin credentials
    username = app.config.get("TWS_ADMIN_USERNAME") or os.environ.get("TWS_ADMIN_USERNAME", "admin")
    app.config["TWS_ADMIN_USERNAME"] = username

    # Password: check for pre-hashed value first, then plain-text to hash
    password_hash = app.config.get("TWS_ADMIN_PASSWORD_HASH") or os.environ.get("TWS_ADMIN_PASSWORD_HASH", "")
    if not password_hash:
        plain = app.config.get("TWS_ADMIN_PASSWORD") or os.environ.get("TWS_ADMIN_PASSWORD", "")
        if plain:
            password_hash = generate_password_hash(plain)
        else:
            allow_default_password = app.config.get("ALLOW_DEFAULT_PASSWORD")
            if allow_default_password is None:
                allow_default_password = os.environ.get("ALLOW_DEFAULT_PASSWORD", "").lower() in ("1", "true", "yes")

            if not (app.config.get("TESTING") or app.config.get("DEBUG") or allow_default_password):
                raise RuntimeError(
                    "Authentication requires TWS_ADMIN_PASSWORD_HASH or "
                    "TWS_ADMIN_PASSWORD; set ALLOW_DEFAULT_PASSWORD=true only "
                    "to opt in to the insecure default password."
                )

            logger.warning(
                "Using insecure default admin password because TESTING/DEBUG "
                "or ALLOW_DEFAULT_PASSWORD enabled; set TWS_ADMIN_PASSWORD or "
                "TWS_ADMIN_PASSWORD_HASH for real deployments."
            )
            password_hash = generate_password_hash("changeme")
    app.config["TWS_ADMIN_PASSWORD_HASH"] = password_hash

    # Determine if login is disabled (local dev mode)
    login_disabled = app.config.get("LOGIN_DISABLED")
    if login_disabled is None:
        env_val = os.environ.get("LOGIN_DISABLED", "").lower()
        login_disabled = env_val in ("1", "true", "yes")
    app.config["LOGIN_DISABLED"] = login_disabled

    # Initialize Flask-Login
    login_manager.init_app(app)

    # Register auth blueprint
    app.register_blueprint(bp)

    # Global before_request guard
    @app.before_request
    def require_login():
        """Enforce authentication on all routes except auth and static."""
        if app.config.get("LOGIN_DISABLED"):
            return None

        # Allow access to auth routes and static files
        if request.endpoint and (
            request.endpoint.startswith("auth.")
            or request.endpoint == "static"
        ):
            return None

        if not current_user.is_authenticated:
            if request.is_json or request.path.startswith("/api/"):
                from flask import jsonify
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login"))

        return None
