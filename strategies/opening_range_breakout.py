"""Runtime Opening Range Breakout (ORB) strategy plugin.

This bridges the deterministic, backtest-first ORB state machine in
:mod:`autonomous.opening_range` into the live strategy infrastructure
(:class:`strategies.base_strategy.BaseStrategy` /
:class:`strategies.strategy_registry.StrategyRegistry`).

Safety posture (Prime Directive):
- This strategy never submits orders. It only emits structured proposals /
  ``Signal`` objects for a downstream proposal / sizing / paper layer.
- Long-only for the MVP. Bearish breakouts and Model C are diagnostic-only.
- Consumes only *closed* 1-minute OHLCV candles from the runtime candle layer.
- Stop and target are always populated for executable proposals/signals.

It maintains one :class:`OpeningRangeSession` per symbol per session date and
advances it deterministically as closed 1m candles arrive. Exactly one
proposal/signal is emitted per symbol/session for a valid long Model A/B setup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from strategies.base_strategy import BaseStrategy, StrategyConfig
from strategies.signal import Signal, SignalStrength, SignalType
from autonomous.opening_range import (
    Candle,
    ORBSetup,
    OpeningRangeConfig,
    OpeningRangeSession,
    OpeningRangeState,
    _session_minutes,
)
logger = logging.getLogger(__name__)

# A duplicate, out-of-order, or single dropped 1m bar within a forming 5m bucket
# would corrupt the session's internal 5m aggregation. Step counts the minutes
# between consecutive closed 1m bars: <= 0 is duplicate/out-of-order, 2..5 is a
# missing bar within a bucket. Larger gaps are treated as a new (sparse) window.
_MAX_BUCKET_GAP = 5


def _bad_one_minute_step(prev: Candle, nxt: Candle) -> bool:
    step = _session_minutes(nxt.start) - _session_minutes(prev.start)
    return step <= 0 or 2 <= step <= _MAX_BUCKET_GAP

# Fixed nominal confidence for ORB proposals. ORB setups are gated by the
# deterministic state machine (range/confirmation/model rules) rather than a
# probabilistic score, so a single moderate value is used; downstream sizing
# and the proposal engine apply their own risk gating.
ORB_SIGNAL_CONFIDENCE = 0.7


class ORBRuntimeState(str, Enum):
    """Per-symbol runtime state exposed for dashboard / API consumption."""

    WAITING_FOR_SESSION = "WAITING_FOR_SESSION"
    BUILDING_RANGE = "BUILDING_RANGE"
    RANGE_READY = "RANGE_READY"
    BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
    PROPOSAL_READY = "PROPOSAL_READY"
    IN_TRADE = "IN_TRADE"
    DONE_FOR_SESSION = "DONE_FOR_SESSION"
    INVALIDATED = "INVALIDATED"
    DATA_DEGRADED = "DATA_DEGRADED"


# Map ORB state-machine states to runtime states. ENTRY_ARMED and IN_TRADE both
# collapse to PROPOSAL_READY here because this proposal-only phase emits a
# proposal/signal rather than entering a real position; the session moves to
# IN_TRADE immediately after producing a setup. A true IN_TRADE runtime state is
# owned later by the paper execution / trade lifecycle work (#209/#210).
_STATE_MAP = {
    OpeningRangeState.WAITING_FOR_SESSION: ORBRuntimeState.WAITING_FOR_SESSION,
    OpeningRangeState.BUILDING_RANGE: ORBRuntimeState.BUILDING_RANGE,
    OpeningRangeState.RANGE_READY: ORBRuntimeState.RANGE_READY,
    OpeningRangeState.BREAKOUT_CONFIRMED: ORBRuntimeState.BREAKOUT_CONFIRMED,
    OpeningRangeState.ENTRY_ARMED: ORBRuntimeState.PROPOSAL_READY,
    OpeningRangeState.IN_TRADE: ORBRuntimeState.PROPOSAL_READY,
    OpeningRangeState.DONE_FOR_SESSION: ORBRuntimeState.DONE_FOR_SESSION,
    OpeningRangeState.INVALIDATED: ORBRuntimeState.INVALIDATED,
}


@dataclass
class ORBTradeProposal:
    """Structured, broker-free ORB setup proposal for the dashboard/proposal engine."""

    symbol: str
    session_date: str
    direction: str
    model: str
    entry_price: float
    stop_price: float
    target_price: float
    risk_per_share: float
    reward_per_share: float
    rr_ratio: float
    range_high: float
    range_low: float
    range_width_pct: float
    detected_at: str
    confirmation_at: str
    quantity: Optional[int] = None
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_setup(cls, setup: ORBSetup, session_date: str) -> "ORBTradeProposal":
        rng = setup.opening_range
        return cls(
            symbol=setup.symbol,
            session_date=session_date,
            direction=setup.direction.value,
            model=setup.model.value,
            entry_price=setup.entry_price,
            stop_price=setup.stop_price,
            target_price=setup.target_price,
            risk_per_share=setup.risk_per_share,
            reward_per_share=setup.reward_per_share,
            rr_ratio=setup.rr_ratio,
            range_high=rng.high,
            range_low=rng.low,
            range_width_pct=rng.width_pct,
            detected_at=setup.detected_at.isoformat(),
            confirmation_at=setup.confirmation.confirmed_at.isoformat(),
            reason=(
                f"ORB {setup.model.value} long: entry {setup.entry_price} "
                f"stop {setup.stop_price} target {setup.target_price} "
                f"range[{rng.low},{rng.high}]"
            ),
            evidence=dict(setup.evidence),
        )

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _orb_config_from_parameters(symbols: List[str], params: Dict[str, Any]) -> OpeningRangeConfig:
    """Build an OpeningRangeConfig from persisted StrategyConfig parameters."""
    valid = {f.name for f in fields(OpeningRangeConfig)}
    kwargs = {k: v for k, v in (params or {}).items() if k in valid}
    kwargs.setdefault("symbols", list(symbols))
    return OpeningRangeConfig(**kwargs)


class OpeningRangeBreakoutStrategy(BaseStrategy):
    """Runtime long-only ORB strategy wrapping :class:`OpeningRangeSession`.

    Consumes closed 1-minute candles via :meth:`on_bar`, maintains one
    ``OpeningRangeSession`` per symbol/session, and emits exactly one long
    Model A/B proposal/``Signal`` per symbol/session. It does not place orders.
    """

    def __init__(self, config: StrategyConfig, event_bus=None):
        params = config.parameters or {}
        self.orb_config = _orb_config_from_parameters(config.symbols, params)
        super().__init__(config=config, event_bus=event_bus)

        # Per-symbol, per-session sessions keyed by (symbol, session_date).
        self._sessions: Dict[tuple, OpeningRangeSession] = {}
        # Closed 1m candles seen per (symbol, session_date) for quality checks.
        self._one_min: Dict[tuple, List[Candle]] = {}
        # Symbols flagged degraded (invalid candle input) per session.
        self._degraded: Dict[tuple, bool] = {}
        # Prevent duplicate proposals/signals per (symbol, session_date).
        self._emitted: set = set()
        self.proposals: List[ORBTradeProposal] = []
        self.signals_to_emit: List[Signal] = []

    # ------------------------------------------------------------------
    def _session_date(self, candle: Candle) -> str:
        ts = candle.start
        tz = self.orb_config.tzinfo()
        if ts.tzinfo is not None:
            ts = ts.astimezone(tz)
        return ts.strftime("%Y-%m-%d")

    def _get_session(self, symbol: str, session_date: str) -> OpeningRangeSession:
        key = (symbol, session_date)
        sess = self._sessions.get(key)
        if sess is None:
            sess = OpeningRangeSession(symbol, session_date, self.orb_config)
            self._sessions[key] = sess
        return sess

    def on_bar(self, symbol: str, bar_data: dict) -> Optional[Signal]:
        """Process a closed 1m OHLCV bar; emit a proposal/signal when armed."""
        if symbol not in self.config.symbols:
            return None
        candle = self._to_candle(symbol, bar_data)
        if candle is None:
            return None
        session_date = self._session_date(candle)
        key = (symbol, session_date)

        # Degradation is terminal for a symbol/session: once flagged, do not feed
        # any further bars to the state machine or emit a proposal/signal, even if
        # a later sparse window would otherwise produce a setup (#218).
        if self._degraded.get(key):
            return None

        # Only closed 1m candles advance the ORB state machine.
        if candle.timeframe != "1m" or not candle.is_closed:
            return None
        if not candle.is_valid():
            self._degraded[key] = True
            return None

        # Guard the session's internal 5m aggregation against duplicate, missing,
        # or out-of-order 1m data (the protection added in #218). Compare against
        # the last accepted closed bar: a duplicate/earlier minute, or a small gap
        # within a forming 5m bucket, would corrupt the aggregate, so degrade and
        # skip. Large intentional gaps (next session window) are not flagged.
        recent = self._one_min.setdefault(key, [])
        if recent and _bad_one_minute_step(recent[-1], candle):
            self._degraded[key] = True
            logger.warning(
                "ORB: degraded 1m sequence for %s %s; skipping bar at %s",
                symbol,
                session_date,
                candle.start.isoformat(),
            )
            return None
        recent.append(candle)

        sess = self._get_session(symbol, session_date)
        setup = sess.on_closed_1m(candle)
        if setup is None or key in self._emitted:
            return None

        self._emitted.add(key)
        proposal = ORBTradeProposal.from_setup(setup, session_date)
        self.proposals.append(proposal)
        return self._emit_signal(setup, proposal)

    def _to_candle(self, symbol: str, bar: dict) -> Optional[Candle]:
        if isinstance(bar, Candle):
            return bar
        ts = bar.get("timestamp") or bar.get("start")
        if ts is None:
            return None
        try:
            start = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
            end = bar.get("end") or bar.get("end_time")
            end_dt = end if isinstance(end, datetime) else start + timedelta(minutes=1)
            return Candle(
                symbol=symbol,
                timeframe=bar.get("timeframe", "1m"),
                start=start,
                end=end_dt,
                open=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
                volume=float(bar.get("volume", 0.0)),
                is_closed=bool(bar.get("is_closed", True)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("ORB: skipping malformed bar for %s: %s", symbol, exc)
            return None

    def _emit_signal(self, setup: ORBSetup, proposal: ORBTradeProposal) -> Signal:
        signal = Signal(
            symbol=setup.symbol,
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=setup.detected_at,
            target_price=setup.entry_price,
            stop_loss=setup.stop_price,
            take_profit=setup.target_price,
            quantity=None,
            reason=proposal.reason,
            indicators={
                "entry_model": setup.model.value,
                "range_high": proposal.range_high,
                "range_low": proposal.range_low,
                "range_width_pct": proposal.range_width_pct,
                "rr_ratio": setup.rr_ratio,
                "risk_per_share": setup.risk_per_share,
                "reward_per_share": setup.reward_per_share,
                "confirmation_at": proposal.confirmation_at,
                "evidence": proposal.evidence,
            },
            strategy_name=self.config.name,
            confidence=ORB_SIGNAL_CONFIDENCE,
        )
        self.signals_to_emit.append(signal)
        self.generate_signal(signal)
        return signal

    def validate_signal(self, signal: Signal) -> bool:
        """Long-only with mandatory stop and target."""
        if signal.signal_type != SignalType.BUY:
            return False
        if signal.target_price is None or signal.target_price <= 0:
            return False
        if signal.stop_loss is None or signal.take_profit is None:
            return False
        return signal.validate()

    def runtime_state(self, symbol: str, session_date: Optional[str] = None) -> ORBRuntimeState:
        """Return the dashboard/API runtime state for a symbol/session."""
        if session_date is None:
            keys = [k for k in self._sessions if k[0] == symbol]
            if not keys:
                if any(k[0] == symbol for k in self._degraded):
                    return ORBRuntimeState.DATA_DEGRADED
                return ORBRuntimeState.WAITING_FOR_SESSION
            session_date = sorted(keys)[-1][1]
        key = (symbol, session_date)
        if self._degraded.get(key):
            return ORBRuntimeState.DATA_DEGRADED
        sess = self._sessions.get(key)
        if sess is None:
            return ORBRuntimeState.WAITING_FOR_SESSION
        return _STATE_MAP.get(sess.state, ORBRuntimeState.WAITING_FOR_SESSION)

    def status(self) -> Dict[str, Any]:
        return {
            f"{sym}:{date}": {**sess.status(), "runtime_state": self.runtime_state(sym, date).value}
            for (sym, date), sess in self._sessions.items()
        }
