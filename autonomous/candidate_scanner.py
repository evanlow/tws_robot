"""S&P 500 candidate scanner.

Iterates an S&P 500 universe (loaded from ``data/sp500_constituents.csv``)
and asks a :class:`SignalProvider` to evaluate each symbol.  Returns the
resulting :class:`CandidateSignal` objects unfiltered; ranking and trade
filtering live in :mod:`autonomous.candidate_ranker` and
:mod:`autonomous.autonomous_engine`.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CandidateSignal
# ---------------------------------------------------------------------------

@dataclass
class CandidateSignal:
    """A single analysed S&P 500 symbol.

    Only ``symbol`` and ``strength_score`` are mandatory; everything else
    has a sensible default so simple providers / fixtures can construct
    minimal objects.  ``signal_label`` should normally match the
    canonical label set used by ``web/technical_analysis.py`` (e.g.
    ``"Confirmed Rebound"``).
    """

    symbol: str
    strength_score: int = 0
    signal_label: str = ""

    company_name: str = ""
    last_price: float = 0.0
    technical_reason: str = ""
    support_price: Optional[float] = None
    resistance_price: Optional[float] = None
    volume_ok: bool = True
    trend_ok: bool = True
    earnings_date: Optional[date] = None
    sector: str = ""

    # Free-form metadata that providers may use to attach extra context
    # (e.g. RSI value, ATR, bid/ask, option-chain hints).  Audit log will
    # serialise this verbatim, so values must be JSON-serialisable.
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "sector": self.sector,
            "last_price": self.last_price,
            "strength_score": self.strength_score,
            "signal_label": self.signal_label,
            "technical_reason": self.technical_reason,
            "support_price": self.support_price,
            "resistance_price": self.resistance_price,
            "volume_ok": self.volume_ok,
            "trend_ok": self.trend_ok,
            "earnings_date": (
                self.earnings_date.isoformat() if self.earnings_date else None
            ),
            "extras": dict(self.extras),
        }


# ---------------------------------------------------------------------------
# Universe loader
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SP500_CSV = _REPO_ROOT / "data" / "sp500_constituents.csv"


def load_sp500_symbols(
    csv_path: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """Load S&P 500 constituents from CSV.

    Returns a list of dicts with at least ``symbol``, ``security`` (company
    name) and ``sector`` keys.  Missing CSV files raise ``FileNotFoundError``
    rather than silently returning an empty list — an empty universe almost
    always indicates misconfiguration.
    """
    path = Path(csv_path) if csv_path else _DEFAULT_SP500_CSV
    if not path.exists():
        raise FileNotFoundError(f"S&P 500 universe CSV not found: {path}")

    rows: List[Dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            rows.append({
                "symbol": symbol,
                "security": (row.get("security") or "").strip(),
                "sector": (row.get("sector") or "").strip(),
                "sub_industry": (row.get("sub_industry") or "").strip(),
            })
    return rows


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class CandidateScanner:
    """Iterate an S&P 500 universe and ask a SignalProvider to analyse each
    symbol.

    The scanner is intentionally dumb: it does not filter, it does not rank,
    it does not call any broker API.  It exists so engine tests can swap
    in fixtures trivially.
    """

    def __init__(
        self,
        signal_provider,
        symbols: Optional[Sequence[Dict[str, str]]] = None,
        csv_path: Optional[Path] = None,
    ) -> None:
        self._signal_provider = signal_provider
        if symbols is not None:
            self._symbols: List[Dict[str, str]] = list(symbols)
        else:
            self._symbols = load_sp500_symbols(csv_path)

    def universe_size(self) -> int:
        return len(self._symbols)

    def scan(
        self,
        max_symbols: Optional[int] = None,
        symbol_whitelist: Optional[Iterable[str]] = None,
        symbol_blacklist: Optional[Iterable[str]] = None,
    ) -> List[CandidateSignal]:
        """Run the signal provider over every symbol in the configured
        universe and return the resulting :class:`CandidateSignal` objects.

        Symbols for which the provider returns ``None`` (no signal) or
        raises an exception are skipped; exceptions are logged but never
        propagated, so a single misbehaving symbol cannot poison the
        whole scan.
        """
        whitelist = (
            {s.upper() for s in symbol_whitelist}
            if symbol_whitelist is not None
            else None
        )
        blacklist = {s.upper() for s in (symbol_blacklist or [])}

        results: List[CandidateSignal] = []
        considered = 0
        for row in self._symbols:
            if max_symbols is not None and considered >= max_symbols:
                break
            symbol = row["symbol"]
            if whitelist is not None and symbol not in whitelist:
                continue
            if symbol in blacklist:
                continue
            considered += 1
            try:
                sig = self._signal_provider.analyze(symbol)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "SignalProvider raised for symbol=%s: %s", symbol, exc
                )
                continue
            if sig is None:
                continue
            # Backfill company / sector metadata when the provider didn't
            # supply it — keeps audit log entries readable.
            if not sig.company_name:
                sig.company_name = row.get("security", "")
            if not sig.sector:
                sig.sector = row.get("sector", "")
            results.append(sig)
        return results
