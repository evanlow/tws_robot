"""Production ``SignalProvider`` backed by the S&P 500 screener service.

The autonomous trading engine consumes :class:`CandidateSignal` objects
emitted by some ``SignalProvider``.  The default
:class:`StaticSignalProvider` only returns symbols that were inserted by
hand, which is why a freshly-deployed dashboard reports
``no_candidate`` for every ``/scan`` and ``/propose`` call.

This module wires the autonomous engine to the existing
:mod:`web.sp500_screener_service` so that the same technical analysis
that powers the screener page (Bollinger Bands, oversold momentum
confirmation, fundamentals-based quality score) can be re-used to
produce live ``Strong(100)`` / ``Confirmed Rebound`` candidates.

Mapping rules
-------------

A screener row qualifies as a ``Strong(100) / Confirmed Rebound``
candidate when **both** of the following hold:

* ``momentum_label == "Confirmed Rebound"`` — i.e. the
  ``compute_oversold_momentum_confirmation`` pipeline classified the
  ticker as a confirmed rebound (price above the 5-day SMA with two
  consecutive higher closes).
* ``quality_label == "Strong"`` — i.e. the fundamentals-based quality
  score passed the strong threshold used by the screener.

When both conditions hold the returned :class:`CandidateSignal` carries
``strength_score = 100`` so it satisfies the engine's
``min_signal_strength`` default.  Non-qualifying rows return a
``CandidateSignal`` with ``strength_score = 0`` so the existing
``CandidateRanker`` can record the rejection reason rather than silently
dropping the symbol — operators see *why* the ticker was excluded in
the audit log and dashboard's "rejected candidates" panel.

Failures (missing screener data, exceptions inside the screener
service, missing rows) are converted to ``None`` so the upstream
:class:`CandidateScanner` simply skips the symbol; **the provider must
never raise into the scanner loop**.

Known limitation: support / resistance
--------------------------------------

The S&P 500 screener service does not yet publish explicit support /
resistance price levels, so every signal produced here carries
``support_price = None`` and ``resistance_price = None``.

This is acceptable for the initial paper-trading MVP because:

* ``BUY_SHARES`` planning in :class:`TradePlanner` does not require
  support/resistance — it sizes off ``last_price`` and the configured
  ``max_new_position_pct``.
* :class:`TradePlanner._plan_short_put` deliberately **refuses to plan**
  a cash-secured short put when ``support_price`` is missing or the
  candidate strike is above support, rather than guessing.  The planner
  therefore falls back to ``BUY_SHARES`` (or returns ``None`` when
  share-buying is disabled) — there is no silent unsafe path.

Once the screener exposes support / resistance, ``_row_to_signal``
should be updated to forward those fields so cash-secured short-put
planning can engage automatically.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from autonomous.adr_calculator import ADRResult, calculate_adr
from autonomous.candidate_scanner import CandidateSignal

logger = logging.getLogger(__name__)


# Marker strength score used for qualifying ``Strong(100) / Confirmed
# Rebound`` rows.  Matches ``AutonomousTradingConfig.min_signal_strength``
# default so qualifying candidates clear the hard filter in
# :class:`autonomous.candidate_ranker.CandidateRanker`.
STRONG_REBOUND_STRENGTH_SCORE: int = 100


class TechnicalAnalysisSignalProvider:
    """``SignalProvider`` backed by the existing S&P 500 screener service.

    Parameters
    ----------
    screener_service:
        Object exposing ``get_screener_data(refresh: bool = False)`` and
        returning a dict with a ``"rows"`` list.  Defaults to the
        module-level singleton in :mod:`web.sp500_screener_service`.
    refresh_on_first_call:
        When ``True`` (default) the first :meth:`analyze` call triggers a
        fresh scan via ``get_screener_data(refresh=True)``.  Subsequent
        calls within the same provider instance reuse the cached rows
        (the scanner iterates the whole universe once per ``run_once``,
        so we never want to re-trigger a full scan per symbol).  Tests
        can set this to ``False`` to avoid network I/O.
    rows_loader:
        Optional callable returning ``List[Dict[str, Any]]`` of screener
        rows.  Provided as an explicit injection point for tests that
        prefer not to construct a screener-service stub.
    adr_lookback_days:
        Number of trading days to use for ADR calculation.  Set to 0
        or ``None`` to disable ADR computation during scanning.
    price_history_fetcher:
        Callable ``(symbol: str, period: str, interval: str) → List[Dict]``
        for retrieving daily bars.  Defaults to
        :func:`data.fundamentals.fetch_price_history`.
    """

    def __init__(
        self,
        screener_service: Any = None,
        refresh_on_first_call: bool = True,
        rows_loader: Optional[Callable[[], Any]] = None,
        adr_lookback_days: int = 14,
        price_history_fetcher: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    ) -> None:
        if screener_service is None and rows_loader is None:
            # Import lazily so importing this module does not pull in
            # yfinance / pandas at process start.
            from web.sp500_screener_service import sp500_screener_service
            screener_service = sp500_screener_service
        self._screener_service = screener_service
        self._rows_loader = rows_loader
        self._refresh_on_first_call = refresh_on_first_call
        self._adr_lookback_days = adr_lookback_days or 0
        self._price_history_fetcher = price_history_fetcher

        # Lazily-populated symbol → row index.  ``None`` means "not yet
        # loaded"; an empty dict means "loaded but no rows available".
        self._rows_by_symbol: Optional[Dict[str, Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # Public protocol
    # ------------------------------------------------------------------

    def analyze(self, symbol: str) -> Optional[CandidateSignal]:
        """Return a :class:`CandidateSignal` for *symbol* or ``None``.

        ``None`` is returned when:

        * The screener service raises or returns no rows for the symbol.
        * The row exists but is marked ``insufficient_data``.

        For rows that exist but do not satisfy the strong/rebound rule
        we still return a :class:`CandidateSignal` (with
        ``strength_score=0``) so the engine's ranker records a stable
        rejection reason in the audit log.  This keeps the dashboard's
        "rejected candidates" panel informative even when no symbol
        currently qualifies.
        """
        try:
            row = self._lookup_row(symbol)
        except Exception:  # pragma: no cover - defensive: never raise
            logger.exception(
                "TechnicalAnalysisSignalProvider failed to load row for %s",
                symbol,
            )
            return None
        if not row:
            return None
        if row.get("bollinger_status") == "insufficient_data":
            return None
        try:
            signal = self._row_to_signal(symbol, row)
        except Exception:  # pragma: no cover - defensive: never raise
            logger.exception(
                "TechnicalAnalysisSignalProvider failed mapping row for %s",
                symbol,
            )
            return None

        # Compute ADR during scanning if configured
        if signal is not None and self._adr_lookback_days > 0:
            adr_result = self._compute_adr_for_symbol(symbol, signal.last_price)
            if adr_result is not None:
                signal.extras["adr"] = adr_result.adr
                signal.extras["adr_pct"] = adr_result.adr_pct
                signal.extras["adr_lookback_days_used"] = adr_result.lookback_days_used
                signal.extras["adr_valid"] = adr_result.valid

        return signal

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _lookup_row(self, symbol: str) -> Optional[Dict[str, Any]]:
        if self._rows_by_symbol is None:
            self._rows_by_symbol = self._load_rows()
        return self._rows_by_symbol.get(symbol.upper())

    def _load_rows(self) -> Dict[str, Dict[str, Any]]:
        if self._rows_loader is not None:
            rows = self._rows_loader() or []
        else:
            try:
                payload = self._screener_service.get_screener_data(
                    refresh=self._refresh_on_first_call,
                )
            except Exception:
                logger.exception(
                    "TechnicalAnalysisSignalProvider: screener_service raised"
                )
                return {}
            rows = (payload or {}).get("rows") or []
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                out[sym] = row
        return out

    def _compute_adr_for_symbol(
        self, symbol: str, last_price: float
    ) -> Optional[ADRResult]:
        """Fetch daily bars and compute ADR for *symbol*.

        Returns ``None`` on any failure — the caller treats missing ADR
        as a graceful degradation (fall back to resistance/percent target).
        """
        if last_price <= 0:
            return None
        fetcher = self._price_history_fetcher
        if fetcher is None:
            try:
                from data.fundamentals import fetch_price_history
                fetcher = fetch_price_history
            except ImportError:
                logger.debug("Cannot import fetch_price_history for ADR")
                return None
        try:
            # Request enough days of history to cover the lookback
            # (add margin for weekends/holidays)
            period_days = self._adr_lookback_days * 2
            period = f"{period_days}d" if period_days <= 60 else "3mo"
            bars = fetcher(symbol, period=period, interval="1d")
        except Exception:
            logger.debug("ADR price history fetch failed for %s", symbol)
            return None
        if not bars:
            return None
        result = calculate_adr(
            daily_bars=bars,
            reference_price=last_price,
            lookback_days=self._adr_lookback_days,
        )
        return result if result.valid else None

    @staticmethod
    def _row_to_signal(symbol: str, row: Dict[str, Any]) -> CandidateSignal:
        """Map a screener row to a :class:`CandidateSignal`.

        Qualifying rows (``Strong`` quality + ``Confirmed Rebound``
        momentum) get ``strength_score = 100`` and
        ``signal_label = "Confirmed Rebound"`` so they satisfy the
        engine's default hard filters.  Non-qualifying rows keep
        ``strength_score = 0`` and forward the actual momentum label so
        the ranker records a precise rejection reason.
        """
        momentum_label = row.get("momentum_label") or ""
        quality_label = row.get("quality_label") or ""

        qualifies = (
            momentum_label == "Confirmed Rebound"
            and quality_label == "Strong"
        )
        if qualifies:
            strength_score = STRONG_REBOUND_STRENGTH_SCORE
            signal_label = "Confirmed Rebound"
        else:
            strength_score = 0
            # Surface the *actual* momentum label so the ranker's
            # rejection reason ("signal_label 'X' != required 'Confirmed
            # Rebound'") tells the operator what really happened.
            signal_label = momentum_label or "No Signal"

        reasons = []
        for r in (row.get("momentum_reasons") or []):
            if isinstance(r, str):
                reasons.append(r)
        for r in (row.get("quality_reasons") or []):
            if isinstance(r, str):
                reasons.append(r)
        technical_reason = "; ".join(reasons)

        return CandidateSignal(
            symbol=symbol.upper(),
            strength_score=strength_score,
            signal_label=signal_label,
            company_name=row.get("company") or "",
            sector=row.get("sector") or "",
            last_price=float(row.get("current_price") or 0.0),
            technical_reason=technical_reason,
            # The screener does not currently expose explicit support /
            # resistance levels (see module docstring → "Known
            # limitation: support / resistance").  Leaving these as
            # ``None`` causes ``TradePlanner._plan_short_put`` to
            # decline the candidate and fall back to ``BUY_SHARES`` —
            # the planner never guesses a strike when support is
            # unknown, so the safety boundary is preserved.
            support_price=None,
            resistance_price=None,
            volume_ok=True,
            trend_ok=True,
            earnings_date=None,
            extras={
                "quality_label": quality_label,
                "quality_score": row.get("quality_score"),
                "momentum_label": momentum_label,
                "momentum_confirmation": row.get("momentum_confirmation"),
                "bollinger_status": row.get("bollinger_status"),
                "rsi_14": row.get("rsi_14"),
                "rsi_status": row.get("rsi_status"),
            },
        )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @classmethod
    def try_build(cls, **kwargs: Any) -> Optional["TechnicalAnalysisSignalProvider"]:
        """Best-effort constructor for the production wiring.

        Returns the provider on success or ``None`` if construction
        raised (e.g. screener service import failed).  Callers can use
        this to safely fall back to :class:`StaticSignalProvider` and
        keep the dashboard usable.
        """
        try:
            return cls(**kwargs)
        except Exception:
            logger.exception(
                "TechnicalAnalysisSignalProvider construction failed; "
                "caller should fall back to StaticSignalProvider"
            )
            return None
