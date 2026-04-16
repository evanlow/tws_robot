"""Smoke tests for ai.client module.

Tests the AI client wrapper, configuration logic, and retry mechanisms.
"""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_ai_state():
    """Reset AI client state before each test."""
    from ai.client import reset_client

    reset_client()
    # Clear environment variables
    env_vars = ["OPENAI_API_KEY", "OPENAI_MODEL", "AI_ENABLED"]
    old_values = {k: os.environ.pop(k, None) for k in env_vars}
    yield
    # Restore original values
    for k, v in old_values.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    reset_client()


# =============================================================================
# is_ai_enabled() tests
# =============================================================================


def test_is_ai_enabled_with_api_key():
    """AI should auto-enable when OPENAI_API_KEY is set."""
    from ai.client import is_ai_enabled

    os.environ["OPENAI_API_KEY"] = "sk-test-key"
    assert is_ai_enabled() is True


def test_is_ai_enabled_without_api_key():
    """AI should be disabled when OPENAI_API_KEY is not set."""
    from ai.client import is_ai_enabled

    assert is_ai_enabled() is False


def test_is_ai_enabled_empty_api_key():
    """AI should be disabled when OPENAI_API_KEY is empty or whitespace."""
    from ai.client import is_ai_enabled

    os.environ["OPENAI_API_KEY"] = "   "
    assert is_ai_enabled() is False


def test_is_ai_enabled_explicit_false_overrides_key():
    """AI_ENABLED=false should disable AI even when API key is set."""
    from ai.client import is_ai_enabled

    os.environ["OPENAI_API_KEY"] = "sk-test-key"
    os.environ["AI_ENABLED"] = "false"
    assert is_ai_enabled() is False


def test_is_ai_enabled_explicit_true():
    """AI_ENABLED=true should enable AI (regardless of key presence)."""
    from ai.client import is_ai_enabled

    os.environ["AI_ENABLED"] = "true"
    assert is_ai_enabled() is True


def test_is_ai_enabled_explicit_true_case_insensitive():
    """AI_ENABLED check should be case-insensitive."""
    from ai.client import is_ai_enabled, reset_client

    os.environ["AI_ENABLED"] = "TRUE"
    assert is_ai_enabled() is True

    reset_client()
    os.environ["AI_ENABLED"] = "True"
    assert is_ai_enabled() is True


def test_is_ai_enabled_caching():
    """is_ai_enabled() should cache result until reset_client() called."""
    from ai.client import is_ai_enabled, reset_client

    os.environ["OPENAI_API_KEY"] = "sk-test-key"
    assert is_ai_enabled() is True

    # Change env var but result should still be cached
    os.environ["OPENAI_API_KEY"] = ""
    assert is_ai_enabled() is True  # Still cached

    # After reset, new env should be picked up
    reset_client()
    assert is_ai_enabled() is False


# =============================================================================
# reset_client() tests
# =============================================================================


def test_reset_client_clears_singleton():
    """reset_client() should clear the client singleton and cache."""
    from ai.client import get_client, reset_client

    os.environ["OPENAI_API_KEY"] = "sk-test-key"

    with patch("openai.OpenAI"):
        client1 = get_client()
        assert client1 is not None

        reset_client()

        client2 = get_client()
        assert client2 is not None
        assert client2 is not client1  # New instance created


# =============================================================================
# get_client() tests
# =============================================================================


def test_get_client_returns_none_when_disabled():
    """get_client() should return None when AI is disabled."""
    from ai.client import get_client

    assert get_client() is None


def test_get_client_returns_instance_when_enabled():
    """get_client() should return AIClient when enabled with valid key."""
    from ai.client import get_client

    os.environ["OPENAI_API_KEY"] = "sk-test-key"
    os.environ["OPENAI_MODEL"] = "gpt-4"

    with patch("openai.OpenAI") as mock_openai:
        client = get_client()
        assert client is not None
        mock_openai.assert_called_once_with(api_key="sk-test-key")


def test_get_client_returns_none_when_enabled_but_no_key():
    """get_client() should return None when AI_ENABLED=true but no API key."""
    from ai.client import get_client

    os.environ["AI_ENABLED"] = "true"
    # No OPENAI_API_KEY set

    client = get_client()
    assert client is None


def test_get_client_singleton_behavior():
    """get_client() should return the same instance on repeated calls."""
    from ai.client import get_client

    os.environ["OPENAI_API_KEY"] = "sk-test-key"

    with patch("openai.OpenAI"):
        client1 = get_client()
        client2 = get_client()
        assert client1 is client2  # Same singleton instance


def test_get_client_uses_default_model():
    """get_client() should use gpt-4o as default model."""
    from ai.client import get_client

    os.environ["OPENAI_API_KEY"] = "sk-test-key"

    with patch("openai.OpenAI"):
        client = get_client()
        assert client._model == "gpt-4o"


def test_get_client_uses_custom_model():
    """get_client() should use OPENAI_MODEL env var when set."""
    from ai.client import get_client

    os.environ["OPENAI_API_KEY"] = "sk-test-key"
    os.environ["OPENAI_MODEL"] = "gpt-3.5-turbo"

    with patch("openai.OpenAI"):
        client = get_client()
        assert client._model == "gpt-3.5-turbo"


# =============================================================================
# AIClient tests
# =============================================================================


def test_ai_client_init_requires_openai_package():
    """AIClient should raise ImportError if openai package not installed."""
    from ai.client import AIClient

    with patch.dict("sys.modules", {"openai": None}):
        with pytest.raises(ImportError, match="openai package is required"):
            AIClient(api_key="sk-test-key")


def test_ai_client_chat_success():
    """AIClient.chat() should return assistant's reply on success."""
    from ai.client import AIClient

    mock_openai = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Hello, world!"))]
    mock_openai.chat.completions.create.return_value = mock_response

    with patch("openai.OpenAI", return_value=mock_openai):
        client = AIClient(api_key="sk-test-key", model="gpt-4")

        messages = [{"role": "user", "content": "Hello"}]
        reply = client.chat(messages)

        assert reply == "Hello, world!"
        mock_openai.chat.completions.create.assert_called_once_with(
            model="gpt-4", messages=messages, temperature=0.3
        )


def test_ai_client_chat_custom_temperature():
    """AIClient.chat() should accept custom temperature parameter."""
    from ai.client import AIClient

    mock_openai = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Test"))]
    mock_openai.chat.completions.create.return_value = mock_response

    with patch("openai.OpenAI", return_value=mock_openai):
        client = AIClient(api_key="sk-test-key")

        client.chat([{"role": "user", "content": "Hi"}], temperature=0.7)

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7


def test_ai_client_chat_custom_model_override():
    """AIClient.chat() should allow per-call model override."""
    from ai.client import AIClient

    mock_openai = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Test"))]
    mock_openai.chat.completions.create.return_value = mock_response

    with patch("openai.OpenAI", return_value=mock_openai):
        client = AIClient(api_key="sk-test-key", model="gpt-4")

        client.chat([{"role": "user", "content": "Hi"}], model="gpt-3.5-turbo")

        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-3.5-turbo"


def test_ai_client_chat_empty_content():
    """AIClient.chat() should handle empty content gracefully."""
    from ai.client import AIClient

    mock_openai = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content=None))]
    mock_openai.chat.completions.create.return_value = mock_response

    with patch("openai.OpenAI", return_value=mock_openai):
        client = AIClient(api_key="sk-test-key")

        reply = client.chat([{"role": "user", "content": "Hi"}])

        assert reply == ""


def test_ai_client_chat_rate_limit_retry():
    """AIClient.chat() should retry on rate limit error."""
    from ai.client import AIClient

    mock_openai = Mock()

    # Create mock exception classes
    rate_limit_error = type("RateLimitError", (Exception,), {})
    api_error = type("APIError", (Exception,), {})

    # First call raises rate limit, second succeeds
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Success after retry"))]
    mock_openai.chat.completions.create.side_effect = [
        rate_limit_error("Rate limited"),
        mock_response,
    ]

    with patch("openai.OpenAI", return_value=mock_openai):
        with patch("time.sleep"):  # Skip actual sleep delay
            client = AIClient(api_key="sk-test-key")
            client._RateLimitError = rate_limit_error
            client._APIError = api_error

            reply = client.chat([{"role": "user", "content": "Hi"}])

            assert reply == "Success after retry"
            assert mock_openai.chat.completions.create.call_count == 2


def test_ai_client_chat_max_retries_exceeded():
    """AIClient.chat() should raise RuntimeError after max retries."""
    from ai.client import AIClient

    mock_openai = Mock()

    # Create mock exception classes
    rate_limit_error = type("RateLimitError", (Exception,), {})
    api_error = type("APIError", (Exception,), {})

    # All calls fail with rate limit
    mock_openai.chat.completions.create.side_effect = rate_limit_error("Rate limited")

    with patch("openai.OpenAI", return_value=mock_openai):
        with patch("time.sleep"):  # Skip actual sleep delay
            client = AIClient(api_key="sk-test-key")
            client._RateLimitError = rate_limit_error
            client._APIError = api_error

            with pytest.raises(RuntimeError, match="failed after 3 attempts"):
                client.chat([{"role": "user", "content": "Hi"}])

            assert mock_openai.chat.completions.create.call_count == 3


def test_ai_client_chat_api_error_no_retry():
    """AIClient.chat() should not retry on API errors."""
    from ai.client import AIClient

    mock_openai = Mock()

    # Create mock exception classes
    rate_limit_error = type("RateLimitError", (Exception,), {})
    api_error = type("APIError", (Exception,), {})

    # First call fails with API error
    mock_openai.chat.completions.create.side_effect = api_error("API error")

    with patch("openai.OpenAI", return_value=mock_openai):
        client = AIClient(api_key="sk-test-key")
        client._RateLimitError = rate_limit_error
        client._APIError = api_error

        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            client.chat([{"role": "user", "content": "Hi"}])

        # Should only try once (no retry on API error)
        assert mock_openai.chat.completions.create.call_count == 1


def test_ai_client_chat_generic_exception_no_retry():
    """AIClient.chat() should not retry on generic exceptions."""
    from ai.client import AIClient

    mock_openai = Mock()

    # Create mock exception classes
    rate_limit_error = type("RateLimitError", (Exception,), {})
    api_error = type("APIError", (Exception,), {})

    # First call fails with generic error
    mock_openai.chat.completions.create.side_effect = ValueError("Generic error")

    with patch("openai.OpenAI", return_value=mock_openai):
        client = AIClient(api_key="sk-test-key")
        client._RateLimitError = rate_limit_error
        client._APIError = api_error

        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            client.chat([{"role": "user", "content": "Hi"}])

        # Should only try once (no retry on generic error)
        assert mock_openai.chat.completions.create.call_count == 1
