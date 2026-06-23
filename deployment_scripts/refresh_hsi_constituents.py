#!/usr/bin/env python3
"""Refresh the HSI constituents CSV from Wikipedia.

Run this script periodically (e.g. monthly) to keep
``data/hsi_constituents.csv`` up to date with current index membership.

Usage::

    python deployment_scripts/refresh_hsi_constituents.py

Requires ``pandas`` and ``requests`` (both listed in requirements.txt).
The script extracts the "Constituents of Hang Seng Index" table and writes
the standard screener columns used by the app:

* ``symbol``: yfinance-compatible HK ticker (e.g. ``0700.HK``)
* ``display_symbol``: zero-padded HK code for UI display (e.g. ``0700``)
* ``security``: company name
* ``sector``: sub-index bucket from source table (best available grouping)
* ``sub_industry``: left blank when not available in source
"""

import csv
import logging
import re
import sys
from io import StringIO
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _normalise_hk_ticker(raw: str) -> tuple[str, str] | None:
    """Convert a source ticker cell into ``(symbol, display_symbol)``.

    Examples:
    * "700" -> ("0700.HK", "0700")
    * "0700" -> ("0700.HK", "0700")
    * "0700.HK" -> ("0700.HK", "0700")
    """
    text = str(raw).strip().upper()
    if not text:
        return None

    # Keep only the leading numeric code if extra text appears in cell.
    m = re.search(r"(\d{1,5})", text)
    if not m:
        return None

    code = m.group(1).zfill(4)
    return f"{code}.HK", code


def _load_source_table() -> "object":
    """Load the HSI constituents table from Wikipedia into a DataFrame."""
    try:
        import pandas as pd
        import requests
    except ImportError as exc:
        raise RuntimeError("pandas and requests are required: pip install pandas requests") from exc

    url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
    logger.info("Fetching HSI constituent table from Wikipedia: %s", url)

    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()

    tables = pd.read_html(StringIO(resp.text))
    for df in tables:
        cols = {str(c).strip().lower(): c for c in df.columns}
        if "ticker" in cols and "name" in cols:
            ticker_col = cols["ticker"]
            name_col = cols["name"]
            sub_index_col = cols.get("sub-index")

            out = pd.DataFrame()
            out["raw_ticker"] = df[ticker_col]
            out["security"] = df[name_col]
            out["sector"] = df[sub_index_col] if sub_index_col is not None else ""
            return out

    raise RuntimeError("Could not find expected HSI constituents table (Ticker/Name columns)")


def main() -> int:
    """Fetch HSI constituents and write data/hsi_constituents.csv."""
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas is required: pip install pandas")
        return 1

    repo_root = Path(__file__).resolve().parent.parent
    output_path = repo_root / "data" / "hsi_constituents.csv"

    try:
        source_df = _load_source_table()
    except Exception as exc:
        logger.error("Failed to fetch HSI constituents: %s", exc)
        return 1

    rows = []
    for _, rec in source_df.iterrows():
        normalised = _normalise_hk_ticker(rec.get("raw_ticker"))
        if normalised is None:
            continue
        symbol, display_symbol = normalised
        security = str(rec.get("security") or "").strip()
        sector = str(rec.get("sector") or "").strip()
        rows.append(
            {
                "symbol": symbol,
                "display_symbol": display_symbol,
                "security": security,
                "sector": sector,
                "sub_industry": "",
            }
        )

    if not rows:
        logger.error("No constituents parsed from source table")
        return 1

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["symbol"]).sort_values(by=["display_symbol"]).reset_index(drop=True)
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)

    logger.info("Written %d HSI constituents to %s", len(df), output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
