"""Configuration for the paper-only autonomous runner.

These defaults are deliberately conservative.  The runner is intended
to be invoked manually (one ``run_once`` call at a time) and any
future scheduler must remain opt-in.

Hard rules baked into the defaults:

* ``runner_enabled = False`` — no background loop starts automatically.
* ``paper_only = True`` — runner refuses to act unless connected to
  the IBKR paper account.
* ``buy_shares_only = True`` — only ``BUY_SHARES`` trades are
  eligible for autonomous entry/exit in this MVP.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AutonomousRunnerConfig:
    """Runtime configuration for :class:`AutonomousPaperRunner`."""

    # ---- Safety toggles -----------------------------------------------
    runner_enabled: bool = False
    paper_only: bool = True
    buy_shares_only: bool = True

    # ---- Sizing / concurrency limits ----------------------------------
    max_new_trades_per_run: int = 1
    max_open_autonomous_trades: int = 1
    max_holding_days: int = 5

    # ---- Market-hours guard rails (advisory; runner does not enforce
    # them itself unless ``run_during_market_hours_only`` is True and a
    # market-hours checker is provided to the runner) -------------------
    run_during_market_hours_only: bool = True
    avoid_first_minutes_after_open: int = 15
    avoid_last_minutes_before_close: int = 15

    # ---- Persistence --------------------------------------------------
    trade_store_path: str = "logs/autonomous_trades.jsonl"

    def to_dict(self) -> dict:
        return {
            "runner_enabled": self.runner_enabled,
            "paper_only": self.paper_only,
            "buy_shares_only": self.buy_shares_only,
            "max_new_trades_per_run": self.max_new_trades_per_run,
            "max_open_autonomous_trades": self.max_open_autonomous_trades,
            "max_holding_days": self.max_holding_days,
            "run_during_market_hours_only": self.run_during_market_hours_only,
            "avoid_first_minutes_after_open": self.avoid_first_minutes_after_open,
            "avoid_last_minutes_before_close": self.avoid_last_minutes_before_close,
            "trade_store_path": self.trade_store_path,
        }
