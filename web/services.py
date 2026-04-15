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
from typing import Any, Dict, List, Optional

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

    def set_connected(self, env: str, info: Dict[str, Any]) -> None:
        with self._lock:
            self._connected = True
            self._connection_env = env
            self._connection_info = dict(info)
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
        self.set_connected(env, {
            "host": config["host"],
            "port": config["port"],
            "client_id": config["client_id"],
            "account": config.get("account", ""),
        })
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
        """Return the shared StrategyRegistry (created on first access)."""
        if self._strategy_registry is None:
            from strategies.strategy_registry import StrategyRegistry
            self._strategy_registry = StrategyRegistry(self.event_bus)
            self._register_default_strategies()
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
