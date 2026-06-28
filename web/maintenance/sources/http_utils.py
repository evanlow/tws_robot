"""HTTP helpers for metadata source fetches used by maintenance adapters."""

from __future__ import annotations

import time
from typing import Dict, Optional, Sequence, Tuple

import requests


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.6

# Use browser-like headers to reduce anti-bot 403 responses from public pages.
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_html_with_retries(
    urls: Sequence[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """Fetch HTML from candidate URLs with retry/backoff and fallback URLs.

    Returns a tuple of ``(html_text, url_used)``.
    """
    if not urls:
        raise RuntimeError("No source URLs configured")

    merged_headers = dict(DEFAULT_HEADERS)
    if headers:
        merged_headers.update(headers)

    failures = []

    for url in urls:
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.get(url, headers=merged_headers, timeout=timeout)
                resp.raise_for_status()
                return resp.text, url
            except requests.HTTPError as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                failures.append(f"{url} -> HTTP {status_code or 'unknown'}")
                if not _is_retryable_status(status_code):
                    break
            except requests.RequestException as exc:
                failures.append(f"{url} -> {exc}")

            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)

    raise RuntimeError("All source URLs failed: " + "; ".join(failures[-8:]))


def _is_retryable_status(status_code: Optional[int]) -> bool:
    if status_code is None:
        return True
    return status_code in {403, 408, 425, 429} or 500 <= status_code <= 599
