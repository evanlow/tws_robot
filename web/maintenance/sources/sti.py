"""Straits Times Index constituent source adapter."""

from __future__ import annotations

import re
from io import StringIO
from typing import Dict, List, Optional

from web.maintenance.sources.http_utils import fetch_html_with_retries

SOURCE_URL = "https://en.wikipedia.org/wiki/Straits_Times_Index"
FALLBACK_SOURCE_URL = "https://en.m.wikipedia.org/wiki/Straits_Times_Index"

# The STI has ~30 constituents.  Require a plausible number of parsed rows so a
# stray table (e.g. one that merely mentions "SGX") cannot be mistaken for the
# constituents table and silently truncate the metadata.
_MIN_PLAUSIBLE_ROWS = 20


def _normalise_sgx_symbol(raw: object) -> Optional[tuple[str, str]]:
    text = str(raw or "").strip().upper()
    if not text:
        return None
    # Source cells are formatted like "SGX: A17U", "SGX:9CI", "D05", or "D05.SI".
    # Drop any exchange prefix (text before a colon) before extracting the code.
    if ":" in text:
        text = text.rsplit(":", 1)[-1].strip()
    # SGX board-lot codes are 2-5 alphanumeric chars and may start with a digit
    # (e.g. "9CI").  Require at least one letter so stray footnote numbers and
    # the bare "SGX" exchange token are not treated as constituents.
    match = re.search(r"\b([A-Z0-9]{2,5})(?:\.SI)?\b", text)
    if not match:
        return None
    display = match.group(1)
    if not any(ch.isalpha() for ch in display) or display == "SGX":
        return None
    return f"{display}.SI", display


def fetch_constituents() -> List[Dict[str, str]]:
    """Fetch and normalize STI constituents for app-compatible CSV output.

    Wikipedia table layouts change from time to time, so this adapter searches
    for the first table with recognizable symbol and company/name columns.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required to refresh STI constituents") from exc

    html, _ = fetch_html_with_retries([SOURCE_URL, FALLBACK_SOURCE_URL])
    tables = pd.read_html(StringIO(html))
    best_rows: List[Dict[str, str]] = []
    for df in tables:
        cols = {str(c).strip().lower(): c for c in df.columns}
        symbol_col = _first_col(cols, ("ticker", "symbol", "stock code", "code"))
        name_col = _first_col(cols, ("company", "name", "constituent"))
        sector_col = _first_col(cols, ("sector", "industry"))
        if symbol_col is None or name_col is None:
            continue

        rows_by_symbol: Dict[str, Dict[str, str]] = {}
        for _, rec in df.iterrows():
            normalised = _normalise_sgx_symbol(rec.get(symbol_col))
            if normalised is None:
                continue
            symbol, display_symbol = normalised
            rows_by_symbol.setdefault(symbol, {
                "symbol": symbol,
                "display_symbol": display_symbol,
                "security": str(rec.get(name_col) or "").strip(),
                "sector": str(rec.get(sector_col) or "").strip() if sector_col is not None else "",
                "sub_industry": "",
            })
        # Prefer the table that yields the most distinct constituents; a stray
        # table referencing a single SGX code must not win over the real list.
        if len(rows_by_symbol) > len(best_rows):
            best_rows = [rows_by_symbol[symbol] for symbol in sorted(rows_by_symbol)]

    if len(best_rows) >= _MIN_PLAUSIBLE_ROWS:
        return best_rows

    raise RuntimeError(
        "Could not find expected STI constituents table "
        f"(best candidate had {len(best_rows)} distinct symbols, need >= {_MIN_PLAUSIBLE_ROWS})"
    )


def _first_col(cols: Dict[str, object], candidates: tuple[str, ...]) -> object | None:
    for candidate in candidates:
        if candidate in cols:
            return cols[candidate]
    for name, original in cols.items():
        if any(candidate in name for candidate in candidates):
            return original
    return None
