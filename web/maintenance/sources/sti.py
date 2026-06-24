"""Straits Times Index constituent source adapter."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

SOURCE_URL = "https://en.wikipedia.org/wiki/Straits_Times_Index"


def _normalise_sgx_symbol(raw: object) -> Optional[tuple[str, str]]:
    text = str(raw or "").strip().upper()
    if not text:
        return None
    # Common source cells may contain "D05", "D05.SI", or extra footnote text.
    match = re.search(r"\b([A-Z0-9]{1,10})(?:\.SI)?\b", text)
    if not match:
        return None
    display = match.group(1)
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

    tables = pd.read_html(SOURCE_URL)
    for df in tables:
        cols = {str(c).strip().lower(): c for c in df.columns}
        symbol_col = _first_col(cols, ("ticker", "symbol", "stock code", "code"))
        name_col = _first_col(cols, ("company", "name", "constituent"))
        sector_col = _first_col(cols, ("sector", "industry"))
        if symbol_col is None or name_col is None:
            continue

        rows: List[Dict[str, str]] = []
        for _, rec in df.iterrows():
            normalised = _normalise_sgx_symbol(rec.get(symbol_col))
            if normalised is None:
                continue
            symbol, display_symbol = normalised
            rows.append({
                "symbol": symbol,
                "display_symbol": display_symbol,
                "security": str(rec.get(name_col) or "").strip(),
                "sector": str(rec.get(sector_col) or "").strip() if sector_col is not None else "",
                "sub_industry": "",
            })
        if rows:
            rows_by_symbol = {row["symbol"]: row for row in rows}
            return [rows_by_symbol[symbol] for symbol in sorted(rows_by_symbol)]

    raise RuntimeError("Could not find expected STI constituents table")


def _first_col(cols: Dict[str, object], candidates: tuple[str, ...]) -> object | None:
    for candidate in candidates:
        if candidate in cols:
            return cols[candidate]
    for name, original in cols.items():
        if any(candidate in name for candidate in candidates):
            return original
    return None
