"""Tests for the AI Copilot chat route (web/routes/ai_chat.py).

Validates that the chat endpoint correctly wires live trading data
from the ServiceManager into the LLM context, and that failures in
individual subsystems are gracefully handled.
"""

import json
import os
from collections import deque
from unittest.mock import MagicMock, Mock, patch

import pytest

from web import create_app


@pytest.fixture(autouse=True)
def _reset_ai_state():
    """Reset the AI client singleton between tests."""
    from ai.client import reset_client
    reset_client()
    old = {k: os.environ.pop(k, None) for k in ("OPENAI_API_KEY", "AI_ENABLED", "OPENAI_MODEL")}
    yield
    for k, v in old.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    reset_client()


@pytest.fixture()
def app():
    """Create a Flask test app with a ServiceManager that has test data."""
    os.environ["OPENAI_API_KEY"] = "sk-test-key"
    os.environ["AI_ENABLED"] = "true"
    application = create_app({"TESTING": True})
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _clear_chat_history():
    """Clear the module-level chat history between tests."""
    from web.routes.ai_chat import _history
    _history.clear()
    yield
    _history.clear()


# =========================================================================
# _gather_live_context tests
# =========================================================================


def test_gather_live_context_includes_positions(app):
    """Context should include open positions from the ServiceManager."""
    svc = app.config["services"]
    svc.update_position("AAPL", {
        "quantity": 100,
        "entry_price": 150.0,
        "current_price": 155.0,
        "market_value": 15500.0,
        "unrealized_pnl": 500.0,
        "side": "LONG",
        "sec_type": "STK",
    })

    with app.app_context():
        from web.routes.ai_chat import _gather_live_context
        ctx = json.loads(_gather_live_context())

    assert len(ctx["open_positions"]) == 1
    pos = ctx["open_positions"][0]
    assert pos["symbol"] == "AAPL"
    assert pos["quantity"] == 100
    assert pos["unrealized_pnl"] == 500.0


def test_gather_live_context_includes_equity(app):
    """Context should include equity from the risk manager."""
    svc = app.config["services"]
    svc.risk_manager.current_equity = 100_000.0
    svc.risk_manager.peak_equity = 105_000.0

    with app.app_context():
        from web.routes.ai_chat import _gather_live_context
        ctx = json.loads(_gather_live_context())

    assert ctx["portfolio"]["equity"] == 100_000.0


def test_gather_live_context_includes_alerts(app):
    """Context should include recent alerts."""
    svc = app.config["services"]
    svc.add_alert({"level": "WARNING", "message": "Drawdown approaching limit"})
    svc.add_alert({"level": "INFO", "message": "Strategy started"})

    with app.app_context():
        from web.routes.ai_chat import _gather_live_context
        ctx = json.loads(_gather_live_context())

    assert len(ctx["recent_alerts"]) == 2
    assert ctx["recent_alerts"][0]["level"] == "WARNING"


def test_gather_live_context_empty_when_no_data(app):
    """Context should still be valid JSON when no live data is present."""
    with app.app_context():
        from web.routes.ai_chat import _gather_live_context
        ctx = json.loads(_gather_live_context())

    assert ctx["open_positions"] == []
    assert ctx["recent_alerts"] == []
    assert "timestamp" in ctx


def test_gather_live_context_caps_positions(app):
    """Only the top _MAX_CONTEXT_POSITIONS by market value should be included."""
    from web.routes.ai_chat import _MAX_CONTEXT_POSITIONS

    svc = app.config["services"]
    for i in range(_MAX_CONTEXT_POSITIONS + 5):
        svc.update_position(f"SYM{i}", {
            "quantity": 10,
            "market_value": float(i * 1000),
            "unrealized_pnl": 0,
        })

    with app.app_context():
        from web.routes.ai_chat import _gather_live_context
        ctx = json.loads(_gather_live_context())

    assert len(ctx["open_positions"]) == _MAX_CONTEXT_POSITIONS
    # Highest market-value position should come first
    assert ctx["open_positions"][0]["symbol"] == f"SYM{_MAX_CONTEXT_POSITIONS + 4}"


def test_gather_live_context_survives_risk_manager_error(app):
    """Context should be returned even if the risk manager raises."""
    svc = app.config["services"]

    with app.app_context():
        with patch.object(svc.risk_manager, "get_risk_summary", side_effect=RuntimeError("boom")):
            from web.routes.ai_chat import _gather_live_context
            ctx = json.loads(_gather_live_context())

    # Still valid — equity falls back to None
    assert ctx["portfolio"]["equity"] is None


# =========================================================================
# POST /ai/chat integration tests
# =========================================================================


def test_chat_returns_503_when_ai_disabled(app):
    """Chat should return 503 when AI is not enabled."""
    os.environ["AI_ENABLED"] = "false"
    from ai.client import reset_client
    reset_client()

    with app.test_client() as c:
        resp = c.post("/ai/chat", json={"message": "Hello"})
    assert resp.status_code == 503


def test_chat_returns_400_when_message_empty(client):
    """Chat should return 400 when message is missing or empty."""
    with patch("web.routes.ai_chat.get_client", return_value=MagicMock()):
        resp = client.post("/ai/chat", json={"message": ""})
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"]


def test_chat_sends_context_to_llm(app):
    """Chat should include live trading context in the system prompt."""
    svc = app.config["services"]
    svc.update_position("GOOG", {
        "quantity": 50,
        "entry_price": 170.0,
        "current_price": 175.0,
        "market_value": 8750.0,
        "unrealized_pnl": 250.0,
        "side": "LONG",
        "sec_type": "STK",
    })

    mock_client = MagicMock()
    mock_client.chat.return_value = "GOOG is looking good!"

    with app.test_client() as c:
        with patch("web.routes.ai_chat.get_client", return_value=mock_client):
            resp = c.post("/ai/chat", json={"message": "How is GOOG?"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reply"] == "GOOG is looking good!"

    # Verify the system prompt sent to the LLM includes position data
    call_args = mock_client.chat.call_args[0][0]
    system_msg = call_args[0]["content"]
    assert "GOOG" in system_msg
    assert "175.0" in system_msg or "175" in system_msg


def test_chat_returns_reply_and_timestamp(app):
    """Chat should return reply and context_timestamp."""
    mock_client = MagicMock()
    mock_client.chat.return_value = "Hello from AI"

    with app.test_client() as c:
        with patch("web.routes.ai_chat.get_client", return_value=mock_client):
            resp = c.post("/ai/chat", json={"message": "Hi"})

    data = resp.get_json()
    assert data["reply"] == "Hello from AI"
    assert "context_timestamp" in data


def test_chat_persists_history(app):
    """Chat should persist user and assistant messages in history."""
    mock_client = MagicMock()
    mock_client.chat.return_value = "Hi there!"

    with app.test_client() as c:
        with patch("web.routes.ai_chat.get_client", return_value=mock_client):
            c.post("/ai/chat", json={"message": "Hello"})
            resp = c.get("/ai/chat/history")

    history = resp.get_json()["history"]
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_chat_handles_ai_failure(app):
    """Chat should return 502 when the AI call fails."""
    mock_client = MagicMock()
    mock_client.chat.side_effect = RuntimeError("API error")

    with app.test_client() as c:
        with patch("web.routes.ai_chat.get_client", return_value=mock_client):
            resp = c.post("/ai/chat", json={"message": "Hello"})

    assert resp.status_code == 502
