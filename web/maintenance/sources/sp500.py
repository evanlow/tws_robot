"""S&P 500 constituent source adapter."""

from __future__ import annotations

from typing import Dict, List

SOURCE_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def fetch_constituents() -> List[Dict[str, str]]:
    """Fetch and normalize S&P 500 constituents for app-compatible CSV output."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required to refresh S&P 500 constituents") from exc

    tables = pd.read_html(SOURCE_URL)
    if not tables:
        raise RuntimeError("No tables found on S&P 500 source page")

    df = tables[0]
    required = ["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise RuntimeError("S&P 500 source table missing columns: " + ", ".join(missing))

    out = df[required].copy()
    out.columns = ["symbol", "security", "sector", "sub_industry"]
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper().str.replace(".", "-", regex=False)
    out["security"] = out["security"].astype(str).str.strip()
    out["sector"] = out["sector"].astype(str).str.strip()
    out["sub_industry"] = out["sub_industry"].astype(str).str.strip()
    out = out.drop_duplicates(subset=["symbol"]).sort_values(by=["symbol"]).reset_index(drop=True)
    return out.to_dict(orient="records")
