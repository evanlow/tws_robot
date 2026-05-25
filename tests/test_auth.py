"""Tests for authentication and CSRF protection.

Validates that:
- Unauthenticated users cannot access protected routes.
- Login with valid credentials grants access.
- Login with invalid credentials is rejected.
- Logout revokes access.
- API routes return 401 JSON for unauthenticated requests.
- CSRF protection rejects POST without token.
"""

from unittest.mock import patch

import pytest

from web import create_app


@pytest.fixture
def app(monkeypatch):
    """Create Flask app with authentication enabled."""
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "LOGIN_DISABLED": False,
        "WTF_CSRF_ENABLED": False,  # Disable CSRF for most auth tests
        "TWS_ADMIN_USERNAME": "admin",
        "TWS_ADMIN_PASSWORD": "testpass123",
    })


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def csrf_app(monkeypatch):
    """Create Flask app with CSRF enabled for CSRF-specific tests."""
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "LOGIN_DISABLED": False,
        "WTF_CSRF_ENABLED": True,
        "TWS_ADMIN_USERNAME": "admin",
        "TWS_ADMIN_PASSWORD": "csrftest",
    })


@pytest.fixture
def csrf_client(csrf_app):
    """Flask test client with CSRF enabled."""
    return csrf_app.test_client()


# ==============================================================================
# Unauthenticated access is blocked
# ==============================================================================


class TestUnauthenticatedAccess:
    """Verify that sensitive routes reject unauthenticated requests."""

    def test_dashboard_redirects_to_login(self, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_api_connection_returns_401(self, client):
        resp = client.post("/api/connection/connect")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "Authentication required"

    def test_api_orders_returns_401(self, client):
        resp = client.post("/api/orders/")
        assert resp.status_code == 401

    def test_api_emergency_returns_401(self, client):
        resp = client.post("/api/emergency/stop")
        assert resp.status_code == 401

    def test_api_strategies_returns_401(self, client):
        resp = client.get("/api/strategies/")
        assert resp.status_code == 401

    def test_get_api_account_returns_401(self, client):
        resp = client.get("/api/account/summary")
        assert resp.status_code == 401

    def test_settings_page_redirects(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


# ==============================================================================
# Login
# ==============================================================================


class TestLogin:
    """Verify login functionality."""

    def test_login_page_accessible(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code == 200
        assert b"TWS Robot Login" in resp.data

    def test_login_with_valid_credentials(self, client):
        resp = client.post("/auth/login", data={
            "username": "admin",
            "password": "testpass123",
        }, follow_redirects=False)
        assert resp.status_code == 302
        # Should redirect to dashboard
        assert "/auth/login" not in resp.headers.get("Location", "")

    def test_login_with_invalid_password(self, client):
        resp = client.post("/auth/login", data={
            "username": "admin",
            "password": "wrongpassword",
        })
        assert resp.status_code == 200
        assert b"Invalid username or password" in resp.data

    def test_login_with_invalid_username(self, client):
        resp = client.post("/auth/login", data={
            "username": "hacker",
            "password": "testpass123",
        })
        assert resp.status_code == 200
        assert b"Invalid username or password" in resp.data

    def test_authenticated_user_can_access_dashboard(self, client):
        # Login first
        client.post("/auth/login", data={
            "username": "admin",
            "password": "testpass123",
        })
        # Access dashboard
        resp = client.get("/")
        assert resp.status_code == 200

    def test_authenticated_user_can_access_api(self, client):
        client.post("/auth/login", data={
            "username": "admin",
            "password": "testpass123",
        })
        resp = client.get("/api/account/summary")
        assert resp.status_code == 200


# ==============================================================================
# Logout
# ==============================================================================


class TestLogout:
    """Verify logout revokes access."""

    def test_logout_revokes_access(self, client):
        # Login
        client.post("/auth/login", data={
            "username": "admin",
            "password": "testpass123",
        })
        # Verify access
        resp = client.get("/")
        assert resp.status_code == 200
        # Logout
        client.post("/auth/logout")
        # Verify no access
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


# ==============================================================================
# CSRF Protection
# ==============================================================================


class TestCSRFProtection:
    """Verify CSRF protection on state-changing requests."""

    def test_post_without_csrf_token_rejected(self, csrf_client):
        # Login first (CSRF is exempted on login for usability — tested separately)
        # Try to POST to an API route without CSRF token
        with csrf_client.session_transaction() as sess:
            pass  # no CSRF token set
        resp = csrf_client.post("/auth/login", data={
            "username": "admin",
            "password": "csrftest",
        })
        # Flask-WTF will reject the POST with a 400 due to missing CSRF
        assert resp.status_code == 400


# ==============================================================================
# LOGIN_DISABLED mode
# ==============================================================================


class TestLoginDisabled:
    """Verify that LOGIN_DISABLED bypasses authentication."""

    def test_routes_accessible_when_login_disabled(self, monkeypatch):
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        app = create_app({
            "TESTING": True,
            "LOGIN_DISABLED": True,
            "WTF_CSRF_ENABLED": False,
        })
        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
