"""AI client — thin OpenAI wrapper with retry logic.

Reads configuration from environment variables:
- OPENAI_API_KEY   — required when AI_ENABLED=true
- OPENAI_MODEL     — model name, default "gpt-4o"
- AI_ENABLED       — "true"/"false", default "false"

Usage::

    from ai.client import get_client

    client = get_client()          # returns None when AI disabled
    if client:
        reply = client.chat([{"role": "user", "content": "Hello"}])
"""

import logging
import os
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

# Feature flag — set AI_ENABLED=true in the environment to activate.
_AI_ENABLED: Optional[bool] = None
_DEFAULT_MODEL = "gpt-4o"
_MAX_RETRIES = 3
_RETRY_BASE_SECONDS = 2


def _ai_enabled() -> bool:
    """Return True when AI integration is configured and enabled."""
    global _AI_ENABLED
    if _AI_ENABLED is None:
        _AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
    return _AI_ENABLED


class AIClient:
    """Thin wrapper around openai.OpenAI with exponential-back-off retries."""

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        try:
            from openai import OpenAI, RateLimitError, APIError  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "openai package is required. Run: pip install openai>=1.0"
            ) from exc

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._RateLimitError = RateLimitError
        self._APIError = APIError

    def chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        """Send a chat completion request.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            model:    Override the default model for this call.
            temperature: Sampling temperature (0 = deterministic).

        Returns:
            The assistant's reply as a plain string.

        Raises:
            RuntimeError: When the API call fails after all retries.
        """
        chosen_model = model or self._model
        last_error: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=chosen_model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                )
            except self._RateLimitError as exc:
                wait = _RETRY_BASE_SECONDS ** (attempt + 1)
                logger.warning(
                    "OpenAI rate-limit hit (attempt %d/%d). Retrying in %ss.",
                    attempt + 1,
                    _MAX_RETRIES,
                    wait,
                )
                last_error = exc
                time.sleep(wait)
                continue
            except self._APIError as exc:
                logger.error("OpenAI API error: %s", exc)
                last_error = exc
                break
            except Exception as exc:
                logger.error("OpenAI client error: %s", exc)
                last_error = exc
                break

            return response.choices[0].message.content or ""

        raise RuntimeError(
            f"OpenAI request failed after {_MAX_RETRIES} attempts: {last_error}"
        )


# Module-level singleton — lazy-initialised on first call.
_client_instance: Optional[AIClient] = None


def reset_client() -> None:
    """Reset the module-level singleton and feature-flag cache.

    Call this after changing ``OPENAI_API_KEY``, ``OPENAI_MODEL``, or
    ``AI_ENABLED`` environment variables so that subsequent calls to
    ``get_client()`` pick up the new values.
    """
    global _client_instance, _AI_ENABLED
    _client_instance = None
    _AI_ENABLED = None


def get_client() -> Optional[AIClient]:
    """Return the shared AIClient, or None when AI is disabled/unconfigured.

    First call initialises the singleton from environment variables.
    """
    global _client_instance

    if not _ai_enabled():
        return None

    if _client_instance is None:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning(
                "AI_ENABLED=true but OPENAI_API_KEY is not set. AI features disabled."
            )
            return None
        model = os.getenv("OPENAI_MODEL", _DEFAULT_MODEL)
        _client_instance = AIClient(api_key=api_key, model=model)
        logger.info("AI client initialised (model=%s).", model)

    return _client_instance
