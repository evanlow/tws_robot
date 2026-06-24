"""State helpers for the user-facing Autonomous Mode control.

The state is intentionally runtime-only.  A new process, reconnect, account
change, verification failure, critical account-read error, or emergency stop
must always fall back to ``OFF`` rather than restoring a prior value.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class AutonomousOperatingState(str, Enum):
    OFF = "OFF"
    ON = "ON"


class AccountMode(str, Enum):
    """Which account type the autonomous runner is targeting."""

    PAPER = "paper"
    LIVE = "live"


class TradingCycle(str, Enum):
    SINGLE_TRADE = "single_trade"
    CONTINUOUS = "continuous"

    @property
    def label(self) -> str:
        return {
            TradingCycle.SINGLE_TRADE: "Single Trade",
            TradingCycle.CONTINUOUS: "Continuous Trading",
        }[self]


class AutonomousDisplayMode(str, Enum):
    """Dashboard-facing display mode for the Autonomous Mode widget.

    Values:
        OFF — mode is inactive.
        PAPER — paper-trading continuous or single-trade mode.
        LIVE_DRY_RUN — live account, dry-run flag set (no orders sent to TWS).
        LIVE_SINGLE — live account, single-trade cycle, real orders enabled.
        LIVE_CONTINUOUS — full live continuous autonomous trading.
    """

    OFF = "OFF"
    PAPER = "PAPER"
    LIVE_DRY_RUN = "LIVE DRY-RUN"
    LIVE_SINGLE = "LIVE SINGLE"
    LIVE_CONTINUOUS = "LIVE CONTINUOUS"


@dataclass
class AutonomousModeState:
    operating_state: AutonomousOperatingState = AutonomousOperatingState.OFF
    trading_cycle: TradingCycle = TradingCycle.SINGLE_TRADE
    account_mode: AccountMode = AccountMode.PAPER
    readiness_status: str = "Not Ready"
    message: Optional[str] = None
    last_status_refresh: Optional[str] = None
    activated_at: Optional[str] = None
    cycles_started: int = 0  # Incremented each time run_once is called in this activation
    dry_run: bool = False  # True when the live runner is operating in dry-run mode
    operator_halted: bool = False  # True after an explicit operator halt; suppresses auto-reactivation

    @property
    def is_on(self) -> bool:
        return self.operating_state == AutonomousOperatingState.ON

    @property
    def display_mode(self) -> AutonomousDisplayMode:
        """Dashboard display label: OFF / PAPER / LIVE DRY-RUN / LIVE SINGLE / LIVE CONTINUOUS."""
        if not self.is_on:
            return AutonomousDisplayMode.OFF
        if self.account_mode == AccountMode.LIVE:
            if self.dry_run:
                return AutonomousDisplayMode.LIVE_DRY_RUN
            if self.trading_cycle == TradingCycle.CONTINUOUS:
                return AutonomousDisplayMode.LIVE_CONTINUOUS
            return AutonomousDisplayMode.LIVE_SINGLE
        return AutonomousDisplayMode.PAPER

    def refresh(self) -> None:
        self.last_status_refresh = datetime.now(timezone.utc).isoformat()

    def turn_off(self, message: Optional[str] = None, status: str = "Not Ready") -> None:
        self.operating_state = AutonomousOperatingState.OFF
        self.readiness_status = status
        self.message = message
        self.activated_at = None
        self.cycles_started = 0
        self.dry_run = False
        self.refresh()

    def turn_on(
        self,
        cycle: TradingCycle,
        account_mode: AccountMode = AccountMode.PAPER,
        dry_run: bool = False,
    ) -> None:
        """Activate autonomous mode for the given cycle and account mode.

        ``account_mode`` defaults to :attr:`AccountMode.PAPER` so that
        existing paper-trading callers that omit the parameter continue to
        work without modification.  Live callers must explicitly pass
        ``AccountMode.LIVE``.

        ``dry_run`` should be set to ``True`` when the live runner is
        operating in dry-run mode (no real orders sent to TWS) so that
        :attr:`display_mode` reflects this accurately on the dashboard.
        """
        self.operating_state = AutonomousOperatingState.ON
        self.trading_cycle = cycle
        self.account_mode = account_mode
        self.dry_run = dry_run
        self.readiness_status = "Ready"
        self.message = None
        self.activated_at = datetime.now(timezone.utc).isoformat()
        self.cycles_started = 0
        self.operator_halted = False
        self.refresh()

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["operating_state"] = self.operating_state.value
        data["trading_cycle"] = self.trading_cycle.value
        data["trading_cycle_label"] = self.trading_cycle.label
        data["account_mode"] = self.account_mode.value
        data["display_mode"] = self.display_mode.value
        data["is_on"] = self.is_on
        return data


def normalise_trading_cycle(value: Any) -> Optional[TradingCycle]:
    if isinstance(value, TradingCycle):
        return value
    if isinstance(value, str):
        cleaned = value.strip().lower().replace("-", "_")
        if cleaned in {"single", "single_trade"}:
            return TradingCycle.SINGLE_TRADE
        if cleaned in {"continuous", "continuous_trading"}:
            return TradingCycle.CONTINUOUS
    return None


def infer_account_type(account: Any) -> Optional[str]:
    """Infer ``paper`` or ``live`` from an IBKR account identifier.

    IBKR paper accounts conventionally start with ``DU``.  Non-empty account
    identifiers that do not use that prefix are treated as live.  Unknown or
    blank values return ``None`` so callers can keep the match status
    ``Unknown`` instead of guessing.
    """

    text = str(account or "").strip().upper()
    if not text:
        return None
    if text.startswith("DU"):
        return "paper"
    return "live"


def mismatch_message(selected: str, actual: str) -> str:
    selected_u = selected.upper()
    actual_u = actual.upper()
    if selected == "live" and actual == "paper":
        return (
            "Connection rejected: TWS Robot was set to LIVE, but the running "
            "TWS session appears to be PAPER. Please choose Paper connection "
            "or restart TWS in Live mode."
        )
    if selected == "paper" and actual == "live":
        return (
            "Connection rejected: TWS Robot was set to PAPER, but the running "
            "TWS session appears to be LIVE. Please choose Live connection or "
            "restart TWS in Paper mode."
        )
    return (
        f"Connection rejected: TWS Robot was set to {selected_u}, but the "
        f"running TWS session appears to be {actual_u}."
    )
