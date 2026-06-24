"""Hang Seng Index constituent source adapter."""

from __future__ import annotations

import re
from io import StringIO
from typing import Dict, List, Optional, Tuple

SOURCE_URL = "https://en.wikipedia.org/wiki/Hang_Seng_Index"


def normalise_hk_ticker(raw: object) -> Optional[Tuple[str, str]]:
    """Convert a source ticker cell into (symbol, display_symbol)."""
    text = str(raw or "").strip().upper()
    if not text:
        return None
    match = re.search(r"(\d{1,5})", text)
    if not match:
        return None
    code = match.group(1).zfill(4)
    return f"{code}.HK", code


def fetch_constituents() -> List[Dict[str, str]]:
    """Fetch and normalize HSI constituents for app-compatible CSV output."""
    try:
        import pandas as pd
        import requests
    except ImportError as exc:
        raise RuntimeError("pandas and requests are required to refresh HSI constituents") from exc

    resp = requests.get(SOURCE_URL, headers={"User-Agent": "tws_robot/1.0"}, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))

    source_df = None
    for df in tables:
        cols = {str(c).strip().lower(): c for c in df.columns}
        if "ticker" in cols and "name" in cols:
            source_df = df
            break
    if source_df is None:
        raise RuntimeError("Could not find expected HSI constituents table with Ticker/Name columns")

    cols = {str(c).strip().lower(): c for c in source_df.columns}
    ticker_col = cols["ticker"]
    name_col = cols["name"]
    sub_index_col = cols.get("sub-index")

    rows: List[Dict[str, str]] = []
    for _, rec in source_df.iterrows():
        normalised = normalise_hk_ticker(rec.get(ticker_col))
        if normalised is None:
            continue
        symbol, display_symbol = normalised
        rows.append({
            "symbol": symbol,
            "display_symbol": display_symbol,
            "security": str(rec.get(name_col) or "").strip(),
            "sector": str(rec.get(sub_index_col) or "").strip() if sub_index_col is not None else "",
            "sub_industry": "",
        })

    rows_by_symbol = {row["symbol"]: row for row in rows}
    return [rows_by_symbol[symbol] for symbol in sorted(rows_by_symbol)]
