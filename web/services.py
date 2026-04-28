"""Singleton Service Manager for web-layer integration.

Holds shared instances of core services (EventBus, RiskManager,
StrategyRegistry, etc.) so that all Flask routes can access live
system state through ``current_app.config['services']``.

Usage in a route::

    from flask import current_app
    svc = current_app.config['services']
    summary = svc.risk_manager.get_risk_summary()

Usage during app creation::

    from web.services import ServiceManager
    app = create_app()
    app.config['services'] = ServiceManager()
"""

import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.event_bus import Event, EventBus, EventType, get_event_bus

logger = logging.getLogger(__name__)


class ServiceManager:
    """Centralised holder for all live backend services.

    The Flask process owns a *single* instance of this class.  Routes read
    live state from it; background threads (market-data feed, strategy
    orchestrator, …) write into it.

    Thread-safety: individual services already use locks internally.
    The service manager itself is effectively read-only after construction
    (services are replaced only via explicit methods that hold
    ``_lock``).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Core event bus – always available
        self.event_bus: EventBus = get_event_bus()

        # Connection state
        self._connected = False
        self._connection_env: Optional[str] = None  # "paper" | "live"
        self._connection_info: Dict[str, Any] = {}

        # TWS bridge (actual IB API connection)
        self._tws_bridge: Any = None

        # Lazy-initialised services (None ⇒ not started yet)
        self._risk_manager: Any = None
        self._strategy_registry: Any = None
        self._order_executor: Any = None
        self._market_data_feed: Any = None
        self._position_analyzer: Any = None

        # Auto-detected strategies cache
        self._inferred_strategies: List[Dict[str, Any]] = []
        # Dismissed inferred IDs scoped per account: account_id -> set of IDs
        self._dismissed_inferred: Dict[str, set] = {}

        # SSE subscribers — list of queues that receive serialised events
        self._sse_queues: List[Any] = []
        self._sse_lock = threading.Lock()

        # In-memory caches (populated by event listeners)
        self._account_summary: Dict[str, Any] = {}
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._orders: List[Dict[str, Any]] = []
        self._recent_trades: List[Dict[str, Any]] = []
        self._alerts: List[Dict[str, Any]] = []

        # System metadata
        self._start_time = datetime.now()
        self._backtest_runs: Dict[str, Dict[str, Any]] = {}

        logger.info("ServiceManager initialised")

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def connection_env(self) -> Optional[str]:
        return self._connection_env

    @property
    def connection_info(self) -> Dict[str, Any]:
        return dict(self._connection_info)

    @property
    def current_account_id(self) -> str:
        """Return the IBKR account ID for the active connection (empty string if not connected)."""
        with self._lock:
            return self._connection_info.get("account", "")

    def set_connected(self, env: str, info: Dict[str, Any]) -> None:
        with self._lock:
            self._connected = True
            self._connection_env = env
            self._connection_info = dict(info)
            # Invalidate the registry so it is rebuilt with the new account_id
            self._strategy_registry = None
        self.event_bus.publish(Event(
            EventType.CONNECTION_ESTABLISHED,
            data={"environment": env, **info},
            source="ServiceManager",
        ))

    def set_disconnected(self) -> None:
        with self._lock:
            self._connected = False
            self._connection_env = None
            self._connection_info = {}
            # Invalidate the registry — strategies from the previous account
            # must not be visible under a different (or no) account.
            self._strategy_registry = None
        self.event_bus.publish(Event(
            EventType.CONNECTION_LOST,
            data={},
            source="ServiceManager",
        ))

    # ------------------------------------------------------------------
    # TWS bridge helpers (actual IB Gateway connection)
    # ------------------------------------------------------------------

    def connect_tws(self, env: str, config: Dict[str, Any],
                    timeout: int = 10) -> bool:
        """Open a real TWS socket and subscribe to account updates.

        Returns ``True`` if the connection was established within *timeout*.
        On success the service-manager is also marked as *connected*.
        """
        from core.tws_bridge import TWSBridge

        bridge = TWSBridge(self, config)
        if not bridge.connect(timeout=timeout):
            return False

        with self._lock:
            self._tws_bridge = bridge
        info = {
            "host": config["host"],
            "port": config["port"],
            "client_id": config["client_id"],
            "account": config.get("account", ""),
        }
        self.set_connected(env, info)
        return True

    def disconnect_tws(self) -> None:
        """Tear down the TWS bridge and clear cached account data."""
        with self._lock:
            bridge = self._tws_bridge
            self._tws_bridge = None
            # Clear stale account / position caches
            self._positions.clear()
            self._account_summary.clear()
        if bridge is not None:
            bridge.disconnect()
        self.set_disconnected()

    # ------------------------------------------------------------------
    # Lazy service accessors
    # ------------------------------------------------------------------

    @property
    def risk_manager(self):
        """Return the shared RiskManager (created on first access)."""
        if self._risk_manager is None:
            from risk.risk_manager import RiskManager
            self._risk_manager = RiskManager()
        return self._risk_manager

    @property
    def strategy_registry(self):
        """Return the shared StrategyRegistry (created on first access).

        The registry is scoped to the currently connected IBKR account.
        It is invalidated (set to None) on every connect/disconnect so that
        switching accounts always produces a fresh, correctly-scoped registry.
        """
        if self._strategy_registry is None:
            from pathlib import Path
            from strategies.strategy_registry import StrategyRegistry

            # Allow operators to override the path via env var; fall back to a
            # path next to this module so the file ends up in a predictable,
            # writable location regardless of the process working directory.
            _default_db = str(
                Path(os.environ.get(
                    "STRATEGY_DB_PATH",
                    str(Path(__file__).parent.parent / "strategy_lifecycle.db"),
                )).resolve()
            )
            self._strategy_registry = StrategyRegistry(
                self.event_bus,
                db_path=_default_db,
                account_id=self.current_account_id,
            )
            self._register_default_strategies()
            self._strategy_registry.load_persisted_strategies()
        return self._strategy_registry

    def _register_default_strategies(self) -> None:
        """Register built-in strategy classes so they can be instantiated."""
        try:
            from strategies.bollinger_bands import BollingerBandsStrategy
            self._strategy_registry.register_strategy_class(
                "BollingerBands", BollingerBandsStrategy,
            )
        except Exception:  # pragma: no cover
            logger.debug("BollingerBandsStrategy not available for registration")

        try:
            from strategies.inferred_strategies import INFERRED_STRATEGY_CLASSES
            for strategy_type, strategy_class in INFERRED_STRATEGY_CLASSES.items():
                self._strategy_registry.register_strategy_class(
                    strategy_type, strategy_class,
                )
        except ImportError:  # pragma: no cover
            logger.debug(
                "Inferred strategy classes not available for registration",
                exc_info=True,
            )

    @property
    def position_analyzer(self):
        """Return the shared PositionAnalyzer (created on first access)."""
        if self._position_analyzer is None:
            from web.position_analyzer import PositionAnalyzer
            self._position_analyzer = PositionAnalyzer()
        return self._position_analyzer

    def get_inferred_strategies(self) -> List[Dict[str, Any]]:
        """Run position analysis and return inferred strategies.

        Results are cached and refreshed each time this method is called.
        Dismissed inferred IDs (scoped to the current account) are filtered out.
        Strategies that were already adopted (registered as an inferred-type
        strategy with matching symbols) are also suppressed so they do not
        reappear as unadopted inferred cards after an application restart.
        """
        positions = self.get_positions()
        inferred = self.position_analyzer.analyze(positions)
        account_id = self.current_account_id

        # Build set of symbol-sets already covered by adopted inferred strategies
        # so we don't re-surface their inferred cards after a restart.
        # Use the private attribute intentionally to avoid triggering lazy
        # initialization — if the registry hasn't been created yet there are
        # no adopted strategies to filter.
        adopted_symbol_sets = set()
        try:
            from strategies.inferred_strategies import _InferredBase
            reg = self._strategy_registry
            if reg is not None:
                for s in reg.get_all_strategies():
                    if isinstance(s, _InferredBase):
                        adopted_symbol_sets.add(frozenset(s.config.symbols))
        except Exception:
            pass

        with self._lock:
            dismissed = self._dismissed_inferred.get(account_id, set())
            self._inferred_strategies = [
                s.to_dict() for s in inferred
                if s.id not in dismissed
                and frozenset(s.symbols) not in adopted_symbol_sets
            ]
            return list(self._inferred_strategies)

    def dismiss_inferred_strategy(self, inferred_id: str) -> bool:
        """Mark an inferred strategy as dismissed so it's hidden.

        The dismissal is scoped to the current account so switching accounts
        produces a clean slate.

        Returns False if the inferred_id is not in the current set of
        inferred strategies (prevents unbounded growth of the dismissed set).
        """
        account_id = self.current_account_id
        with self._lock:
            valid_ids = {s["id"] for s in self._inferred_strategies}
            if inferred_id not in valid_ids:
                return False
            self._dismissed_inferred.setdefault(account_id, set()).add(inferred_id)
        return True

    def reset_dismissed_inferred(self) -> None:
        """Clear dismissed inferred strategy IDs for the current account."""
        account_id = self.current_account_id
        with self._lock:
            self._dismissed_inferred.pop(account_id, None)

    # ------------------------------------------------------------------
    # Account / positions state (written by event handlers)
    # ------------------------------------------------------------------

    def update_account_summary(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._account_summary.update(data)

    def get_account_summary(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._account_summary)

    def update_position(self, symbol: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._positions[symbol] = data

    def remove_position(self, symbol: str) -> None:
        with self._lock:
            self._positions.pop(symbol, None)

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._positions)

    # ------------------------------------------------------------------
    # Strategy-aware metrics (stock-only equity, options premium)
    # ------------------------------------------------------------------

    def recompute_strategy_metrics(self) -> None:
        """Recompute stock-only equity and short-option premium aggregates.

        Called after each portfolio update so the risk manager always has
        up-to-date strategy-aware figures.

        Stock equity = cash_balance + sum(market_value for long stock/non-option positions)
        Short options tracking = sum of premium_collected and current_liability
        """
        with self._lock:
            positions = dict(self._positions)
            account = dict(self._account_summary)

            # Only proceed when we actually have a cash balance — during
            # initial TWS callbacks portfolio positions may arrive before the
            # cash balance update.  Computing stock_equity without cash and
            # setting the ``_stock_equity_from_positions`` flag would prevent
            # the fallback sync in ``RiskManager.update()`` from ever running.
            if "cash_balance" not in account:
                return

            cash = account["cash_balance"]

            # Accumulate stock-only value (long stocks + any non-option longs)
            stock_value = 0.0
            total_premium_collected = 0.0
            total_current_liability = 0.0

            for pos in positions.values():
                side = pos.get("side", "LONG")
                sec_type = pos.get("sec_type", "")

                if side == "SHORT" and sec_type == "OPT":
                    # Short options — track premium retention separately
                    total_premium_collected += pos.get("premium_collected", 0.0)
                    total_current_liability += pos.get("current_liability", 0.0)
                elif side == "LONG" and sec_type in ("STK", ""):
                    # Only include long stock positions in stock equity
                    stock_value += pos.get("market_value", 0.0)

            stock_equity = cash + stock_value

            rm = self._risk_manager or self.risk_manager
            rm.stock_equity = stock_equity
            rm._stock_equity_from_positions = True
            if stock_equity > rm.peak_stock_equity:
                rm.peak_stock_equity = stock_equity
            rm.short_options_premium_collected = total_premium_collected
            rm.short_options_current_liability = total_current_liability

    # ------------------------------------------------------------------
    # Computed account insights (derived from live state)
    # ------------------------------------------------------------------

    def get_account_insights(self) -> Dict[str, Any]:
        """Return computed dashboard metrics (unrealized P&L, daily P&L $, buying power).

        This is the single source of truth for these derived values — used
        by both the dashboard route and the account-summary API to avoid
        duplicating the calculation logic.
        """
        positions = self.get_positions()
        total_unrealized_pnl = sum(
            pos.get("unrealized_pnl", 0) for pos in positions.values()
        )

        rm = self.risk_manager
        equity = rm.current_equity
        daily_start = rm.daily_start_equity
        daily_pnl_dollar = (equity - daily_start) if daily_start else 0.0

        account = self.get_account_summary()

        return {
            "total_unrealized_pnl": total_unrealized_pnl,
            "daily_pnl_dollar": daily_pnl_dollar,
            "buying_power": account.get("buying_power", 0),
        }

    # ------------------------------------------------------------------
    # Portfolio analysis (concentration, attribution, drawdown)
    # ------------------------------------------------------------------

    def get_portfolio_analysis(self) -> Dict[str, Any]:
        """Return aggregate portfolio analysis for the dashboard.

        Combines data from the CorrelationAnalyzer (concentration / HHI /
        sector exposure) and the RiskManager (drawdown) into a single dict
        that the dashboard template and API can consume directly.

        Returns a dictionary with keys:
            allocation   – per-symbol weight and market value
            concentration – HHI, top-N %, diversification score
            sector_exposure – sector → weight mapping
            drawdown     – current drawdown from peak
            attribution  – P&L by symbol and by strategy (from recent trades)
            suggestions  – actionable diversification suggestions
        """
        from risk.correlation_analyzer import CorrelationAnalyzer, PositionInfo

        positions = self.get_positions()
        rm = self.risk_manager

        # -- Allocation breakdown -----------------------------------------
        # Use gross (absolute) market values so short positions produce
        # valid non-negative weights that sum to ~1.
        total_value = sum(
            abs(pos.get("market_value", 0)) for pos in positions.values()
        )
        allocation: List[Dict[str, Any]] = []
        corr_positions: List["PositionInfo"] = []
        for symbol, pos in positions.items():
            mv = abs(pos.get("market_value", 0))
            weight = mv / total_value if total_value > 0 else 0
            allocation.append({
                "symbol": symbol,
                "market_value": mv,
                "weight": weight,
                "unrealized_pnl": pos.get("unrealized_pnl", 0),
            })
            corr_positions.append(PositionInfo(
                symbol=symbol,
                quantity=int(pos.get("quantity", 0)),
                market_value=mv,
                weight=weight,
                sector=pos.get("sector"),
                industry=pos.get("industry"),
            ))

        # -- Concentration metrics via CorrelationAnalyzer ----------------
        analyzer = CorrelationAnalyzer()
        metrics = analyzer.analyze(corr_positions)
        summary = analyzer.get_metrics_summary(metrics)
        suggestions = analyzer.get_diversification_suggestions(metrics)

        # -- Drawdown from RiskManager ------------------------------------
        peak = rm.peak_equity
        current = rm.current_equity
        has_real_data = rm.equity_initialized
        raw_drawdown_pct = (peak - current) / peak if peak > 0 else 0.0
        if raw_drawdown_pct < 0.0 or raw_drawdown_pct > 1.0:
            logger.warning(
                "Drawdown out of expected range: %.4f (peak=%.2f, current=%.2f)",
                raw_drawdown_pct, peak, current,
            )
        drawdown_pct = max(0.0, min(1.0, raw_drawdown_pct))

        # -- P&L attribution from recent trades ---------------------------
        from strategies.performance_attribution import (
            AttributionMetric,
            PerformanceAttribution,
        )

        pa = PerformanceAttribution()
        trades = self.get_recent_trades()
        for t in trades:
            # Only include closed trades that have the required fields
            if all(k in t for k in ("symbol", "entry_time", "exit_time",
                                     "entry_price", "exit_price",
                                     "quantity", "pnl", "strategy")):
                pa.add_trade(t)

        by_symbol: List[Tuple[str, float]] = []
        by_strategy: List[Tuple[str, float]] = []
        win_rate = 0.0
        total_pnl = 0.0
        if pa.trades:
            by_symbol = pa.get_attribution_by(
                AttributionMetric.SYMBOL,
            ).get_sorted_by_contribution()
            by_strategy = pa.get_attribution_by(
                AttributionMetric.STRATEGY,
            ).get_sorted_by_contribution()
            win_rate = pa.get_win_rate()
            total_pnl = pa.get_total_pnl()

        return {
            "allocation": allocation,
            "total_value": total_value,
            "concentration": summary.get("concentration", {}),
            "diversification": summary.get("diversification", {}),
            "sector_exposure": summary.get("sector_exposure", {}),
            "risk_flags": summary.get("risk_flags", {}),
            "drawdown": {
                "current_pct": drawdown_pct,
                "peak_equity": peak,
                "current_equity": current,
                "has_real_data": has_real_data,
            },
            "attribution": {
                "by_symbol": [
                    {"name": name, "pnl": pnl} for name, pnl in by_symbol
                ],
                "by_strategy": [
                    {"name": name, "pnl": pnl} for name, pnl in by_strategy
                ],
                "win_rate": win_rate,
                "total_pnl": total_pnl,
            },
            "suggestions": suggestions,
        }

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def add_order(self, order: Dict[str, Any]) -> None:
        with self._lock:
            self._orders.append(order)
            # Keep last 500 orders
            if len(self._orders) > 500:
                self._orders = self._orders[-500:]

    def get_orders(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._orders)

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def add_trade(self, trade: Dict[str, Any]) -> None:
        with self._lock:
            self._recent_trades.append(trade)
            if len(self._recent_trades) > 200:
                self._recent_trades = self._recent_trades[-200:]

    def get_recent_trades(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._recent_trades)

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def add_alert(self, alert: Dict[str, Any]) -> None:
        with self._lock:
            self._alerts.append(alert)
            if len(self._alerts) > 200:
                self._alerts = self._alerts[-200:]

    def get_alerts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._alerts)

    def dismiss_alert(self, alert_id: str) -> bool:
        with self._lock:
            before = len(self._alerts)
            self._alerts = [a for a in self._alerts if a.get("id") != alert_id]
            return len(self._alerts) < before

    # ------------------------------------------------------------------
    # Backtest run store
    # ------------------------------------------------------------------

    def store_backtest_run(self, run_id: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._backtest_runs[run_id] = data

    def get_backtest_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._backtest_runs.get(run_id)

    def list_backtest_runs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"run_id": rid, "status": r.get("status", "unknown"),
                 "strategy": r.get("strategy_name", ""),
                 "created": r.get("created", "")}
                for rid, r in self._backtest_runs.items()
            ]

    # ------------------------------------------------------------------
    # SSE helpers
    # ------------------------------------------------------------------

    def register_sse_queue(self, q) -> None:
        with self._sse_lock:
            self._sse_queues.append(q)

    def unregister_sse_queue(self, q) -> None:
        with self._sse_lock:
            try:
                self._sse_queues.remove(q)
            except ValueError:
                pass

    def broadcast_sse(self, event_name: str, data: str) -> None:
        with self._sse_lock:
            dead: List = []
            for q in self._sse_queues:
                try:
                    q.put_nowait((event_name, data))
                except Exception:
                    dead.append(q)
            for q in dead:
                try:
                    self._sse_queues.remove(q)
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    # System health
    # ------------------------------------------------------------------

    def get_system_health(self) -> Dict[str, Any]:
        uptime = (datetime.now() - self._start_time).total_seconds()
        raw_stats = self.event_bus.get_stats()
        # Ensure stats keys are strings for JSON serialization
        event_stats = {
            (k.name if hasattr(k, 'name') else str(k)): v
            for k, v in raw_stats.items()
        }
        return {
            "status": "ok",
            "uptime_seconds": round(uptime, 1),
            "connected": self._connected,
            "environment": self._connection_env,
            "event_bus_stats": event_stats,
            "strategy_count": (
                len(self._strategy_registry) if self._strategy_registry else 0
            ),
            "open_positions": len(self._positions),
            "pending_orders": len([
                o for o in self._orders if o.get("status") == "SUBMITTED"
            ]),
            "sse_clients": len(self._sse_queues),
            "timestamp": datetime.now().isoformat(),
        }


def get_services() -> ServiceManager:
    """Convenience: retrieve the ServiceManager from the current Flask app."""
    from flask import current_app
    return current_app.config["services"]
