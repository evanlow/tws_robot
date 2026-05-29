#!/usr/bin/env python3
"""Refresh the S&P 500 constituents CSV from Wikipedia.

Run this script periodically (e.g. monthly) to keep
``data/sp500_constituents.csv`` up to date with current index membership.

Usage::

    python scripts/refresh_sp500_constituents.py

Requires ``pandas`` and ``lxml`` (both in requirements.txt / pip installable).
Tickers are normalised for yfinance compatibility: dots replaced with hyphens
(e.g. ``BRK.B`` → ``BRK-B``).
"""

import csv
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> int:
    """Fetch the S&P 500 constituent list and write it to data/sp500_constituents.csv."""
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas is required: pip install pandas")
        return 1

    repo_root = Path(__file__).resolve().parent.parent
    output_path = repo_root / "data" / "sp500_constituents.csv"

    logger.info("Fetching S&P 500 constituent table from Wikipedia…")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        tables = pd.read_html(url)
    except Exception as exc:
        logger.error("Failed to fetch Wikipedia table: %s", exc)
        return 1

    df = tables[0][["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]]
    df.columns = ["symbol", "security", "sector", "sub_industry"]

    # Normalise tickers for yfinance compatibility
    df["symbol"] = df["symbol"].str.replace(".", "-", regex=False)

    # Remove duplicates (same symbol appearing twice due to share classes)
    df = df.drop_duplicates(subset=["symbol"])

    df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)
    logger.info("Written %d constituents to %s", len(df), output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
