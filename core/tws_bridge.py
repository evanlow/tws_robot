"""Bridge between the TWS/IB Gateway API and the web ServiceManager.

When the user clicks *Connect* on the dashboard, this module opens a real
TCP socket to TWS, subscribes to account updates, and forwards every
callback into the ``ServiceManager`` so the dashboard can display live
account data (equity, positions, P&L, market prices).

Usage (from the connection API route)::

    from core.tws_bridge import TWSBridge
    bridge = TWSBridge(service_manager, config)
    bridge.connect()   # blocks until ready or timeout
    ...
    bridge.disconnect()
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.order import Order as IBOrder
from ibapi.wrapper import EWrapper

from backtest.data_models import Position
from core.event_bus import Event, EventType
from execution.paper_adapter import LIVE_PORTS

logger = logging.getLogger(__name__)


_IBKR_MARKET_DATA_TYPE_BY_CODE = {
    1: "LIVE",
    2: "FROZEN",
    3: "DELAYED",
    4: "DELAYED_FROZEN",
}

_MARKET_DATA_ERROR_CODES = frozenset({
    200,    # no security definition / contract issue
    354,    # requested market data is not subscribed
    10090,  # part of requested market data is not subscribed
    10167,  # delayed market data is available
    10168,  # requested market data is not subscribed
})


# ---------------------------------------------------------------------------
# Lightweight EWrapper/EClient that forwards data into ServiceManager
# ---------------------------------------------------------------------------

class _BridgeApp(EWrapper, EClient):
    """IB API app whose sole job is to push data into *ServiceManager*."""

    def __init__(self, svc: Any, account: str) -> None:
        EClient.__init__(self, self)
        self._svc = svc
        self._account = account

        # Connection handshake flags
        self._connected = False
        self._ready = False  # set after nextValidId

        # Latest order ID supplied by TWS via ``nextValidId``.  IBKR
        # requires every order to use an ID >= the most recent value
        # reported by the broker; starting from a hardcoded value (e.g.
        # ``1``) risks duplicate/rejected orders when the TWS session
        # has already issued IDs.  Protected by ``_order_id_lock``.
        self._next_valid_order_id: Optional[int] = None
        self._order_id_lock = threading.Lock()

        # Order IDs the broker has rejected since the last drain (TWS
        # error codes 110/200/201/202/203/321/388/434).  Consumed by
        # AutonomousLiveRunner to mark the matching trade-store entries
        # as FAILED so a rejected order doesn't burn a daily/open slot.
        self._rejected_order_ids: set[int] = set()
        self._rejected_order_ids_lock = threading.Lock()

        # Order IDs the broker has reported fully filled since the last
        # drain.  Consumed by AutonomousLiveRunner so a bracket child
        # fill (target or stop) flips the matching trade-store entry
        # from OPEN/EXIT_PENDING to CLOSED — letting Continuous mode
        # start the next cycle.
        self._filled_order_ids: set[int] = set()
        self._filled_order_ids_lock = threading.Lock()

        # Rich broker execution snapshots keyed by execution ID.  Commission
        # reports can arrive after execDetails, so snapshots are retained and
        # a dirty-ID set controls what pop_broker_fill_events drains.
        self._broker_fill_events: Dict[str, Dict[str, Any]] = {}
        self._broker_fill_event_dirty_ids: set[str] = set()
        self._broker_fill_events_lock = threading.Lock()

        # Latest broker-visible open-order snapshots keyed by order ID.
        # Consumed by AutonomousLiveRunner to verify that live positions have
        # confirmed protective stop/bracket children before new entries.
        self._open_order_snapshots: Dict[int, Dict[str, Any]] = {}
        self._open_order_snapshots_lock = threading.Lock()

        # Latest level-I market-data snapshots keyed by symbol.  These are
        # populated by reqMktData callbacks and consumed by the autonomous
        # live market-data provider.  This state is passive: it never submits
        # or alters orders.
        self._market_data_quotes: Dict[str, Dict[str, Any]] = {}
        self._market_data_req_id_to_symbol: Dict[int, str] = {}
        self._market_data_symbol_to_req_id: Dict[str, int] = {}
        self._market_data_next_req_id = 700000
        self._market_data_last_type = "UNKNOWN"
        self._market_data_last_error: Optional[Dict[str, Any]] = None
        self._market_data_lock = threading.Lock()

    # -- connection lifecycle -----------------------------------------------

    def connectAck(self) -> None:
        self._connected = True
        logger.info("TWS connection acknowledged")

    def nextValidId(self, orderId: int) -> None:
        # TWS calls ``nextValidId`` once on connect and again whenever
        # ``reqIds`` is invoked.  Always advance to the broker-supplied
        # value so we never reuse an ID the broker has already handed out.
        with self._order_id_lock:
            if (
                self._next_valid_order_id is None
                or orderId > self._next_valid_order_id
            ):
                self._next_valid_order_id = orderId
            current_order_id = self._next_valid_order_id
        self._ready = True
        logger.info("TWS ready — next valid order ID: %s", current_order_id)

    def connectionClosed(self) -> None:
        self._connected = False
        self._ready = False
        logger.warning("TWS connection closed")
        self._svc.event_bus.publish(Event(
            EventType.CONNECTION_LOST,
            data={},
            source="TWSBridge",
        ))

    # -- account data -------------------------------------------------------

    # Broker account-value keys that map to per-currency cash balances.
    # These are forwarded regardless of the ``currency`` parameter so that
    # multi-currency accounts can report each currency's cash separately.
    _PER_CURRENCY_KEYS = frozenset({"CashBalance", "TotalCashBalance"})

    # Broker account-value keys (BASE currency) that are stored directly into
    # the account summary with a fixed internal name.
    _BASE_CURRENCY_MAP = {
        "TotalCashBalance": "cash_balance",
        "AvailableFunds": "available_funds",
        "FullAvailableFunds": "full_available_funds",
        "BuyingPower": "buying_power",
        "ExcessLiquidity": "excess_liquidity",
        "FullExcessLiquidity": "full_excess_liquidity",
        "InitMarginReq": "init_margin_req",
        "FullInitMarginReq": "full_init_margin_req",
        "MaintMarginReq": "maint_margin_req",
        "FullMaintMarginReq": "full_maint_margin_req",
        "LookAheadAvailableFunds": "lookahead_available_funds",
        "LookAheadExcessLiquidity": "lookahead_excess_liquidity",
        "SettledCash": "settled_cash",
    }

    def updateAccountValue(self, key: str, val: str, currency: str,
                           accountName: str) -> None:
        self._svc.update_connected_account(accountName)
        # -- Per-currency cash balances (all currencies, not only BASE) -----
        if key in self._PER_CURRENCY_KEYS and currency and currency != "BASE":
            with self._svc._lock:
                by_ccy = self._svc._account_summary.setdefault(
                    "cash_by_currency", {}
                )
                by_ccy[currency] = _to_float(val)

        if currency != "BASE":
            # Publish event but skip BASE-only field handling below
            self._svc.event_bus.publish(Event(
                EventType.ACCOUNT_UPDATE,
                data={"key": key, "value": val, "currency": currency},
                source="TWSBridge",
            ))
            return

        # -- BASE currency fields ------------------------------------------
        if key == "TotalCashBalance":
            self._svc.update_account_summary({"cash_balance": _to_float(val)})
        elif key == "NetLiquidationByCurrency":
            equity = _to_float(val)
            self._svc.update_account_summary({"equity": equity})
            # Keep the risk-manager equity in sync (hold lock for atomicity)
            rm = self._svc.risk_manager
            with self._svc._lock:
                rm.current_equity = equity
                # On first real equity update, reset peak and daily start
                # to actual values instead of the default initial_capital.
                if not rm._equity_initialized:
                    rm.peak_equity = equity
                    rm.daily_start_equity = equity
                    rm._equity_initialized = True
                elif equity > rm.peak_equity:
                    rm.peak_equity = equity
        elif key in self._BASE_CURRENCY_MAP:
            internal_key = self._BASE_CURRENCY_MAP[key]
            self._svc.update_account_summary({internal_key: _to_float(val)})

        self._svc.event_bus.publish(Event(
            EventType.ACCOUNT_UPDATE,
            data={"key": key, "value": val, "currency": currency},
            source="TWSBridge",
        ))

    def updatePortfolio(self, contract: Contract, position, marketPrice: float,
                        marketValue: float, averageCost: float,
                        unrealizedPNL: float, realizedPNL: float,
                        accountName: str) -> None:
        symbol = contract.localSymbol or contract.symbol
        pos_float = float(position)
        sec_type = contract.secType or ""
        is_short_option = (pos_float < 0 and sec_type == "OPT")

        if pos_float == 0:
            self._svc.remove_position(symbol)
        else:
            entry_price = averageCost
            current_price = marketPrice
            pnl_pct = (
                (current_price - entry_price) / abs(entry_price)
                if entry_price else 0.0
            )
            pos_data = {
                "quantity": pos_float,
                "entry_price": entry_price,
                "current_price": current_price,
                "market_value": marketValue,
                "unrealized_pnl": unrealizedPNL,
                "unrealized_pnl_pct": pnl_pct,
                "realized_pnl": realizedPNL,
                "side": "LONG" if pos_float > 0 else "SHORT",
                "sec_type": sec_type,
                "exchange": contract.primaryExchange or contract.exchange or "",
                "currency": contract.currency or "",
            }
            # For short options, store premium collected (entry cost) for
            # retention tracking.  averageCost from TWS is the per-unit cost
            # the seller received (positive value).  pos_float is negative
            # for short positions and marketValue is negative for shorts,
            # so abs() normalises both to positive dollar amounts.
            if is_short_option:
                pos_data["premium_collected"] = abs(pos_float) * abs(entry_price)
                pos_data["current_liability"] = abs(marketValue)
            self._svc.update_position(symbol, pos_data)

        # Strategy metrics are recomputed once at accountDownloadEnd() to
        # avoid O(N²) work during burst position updates.

        self._svc.event_bus.publish(Event(
            EventType.PORTFOLIO_UPDATE,
            data={"symbol": symbol, "position": pos_float},
            source="TWSBridge",
        ))

    def accountDownloadEnd(self, accountName: str) -> None:
        logger.info("Account download complete for %s", accountName)
        self._svc.update_connected_account(accountName)
        # Recompute strategy metrics once after the full position snapshot
        # has been received, rather than after every individual position
        # callback, to avoid O(N²) work during burst updates.
        self._svc.recompute_strategy_metrics()

    # -- market data (tick prices) ------------------------------------------

    def tickPrice(self, reqId, tickType, price: float, attrib) -> None:
        with self._market_data_lock:
            symbol = self._market_data_req_id_to_symbol.get(int(reqId))
            if not symbol:
                return
            quote = self._market_data_quotes.setdefault(
                symbol,
                self._new_market_data_quote(symbol),
            )
            now = datetime.now(timezone.utc).isoformat()
            price_f = _positive_float(price)
            if int(tickType) in {1, 66}:  # bid / delayed bid
                quote["bid"] = price_f
                quote["bid_timestamp"] = now
            elif int(tickType) in {2, 67}:  # ask / delayed ask
                quote["ask"] = price_f
                quote["ask_timestamp"] = now
            elif int(tickType) in {4, 68}:  # last / delayed last
                quote["last"] = price_f
                quote["last_timestamp"] = now
            elif int(tickType) in {9, 75}:  # close / delayed close
                quote["close"] = price_f
                quote["previous_close"] = price_f
            elif int(tickType) in {14, 76}:  # open / delayed open
                quote["open"] = price_f
            else:
                return
            quote["timestamp"] = now
            quote["quote_timestamp"] = now
            quote["updated_at"] = now
            quote["feed_healthy"] = True
            quote["market_data_feed_healthy"] = True

    def tickSize(self, reqId, tickType, size: int) -> None:
        with self._market_data_lock:
            symbol = self._market_data_req_id_to_symbol.get(int(reqId))
            if not symbol:
                return
            quote = self._market_data_quotes.setdefault(
                symbol,
                self._new_market_data_quote(symbol),
            )
            now = datetime.now(timezone.utc).isoformat()
            size_f = _positive_float(size)
            if int(tickType) in {0, 69}:  # bid size / delayed bid size
                quote["bid_size"] = size_f
            elif int(tickType) in {3, 70}:  # ask size / delayed ask size
                quote["ask_size"] = size_f
            elif int(tickType) in {5, 71}:  # last size / delayed last size
                quote["last_size"] = size_f
            else:
                return
            quote["updated_at"] = now

    def marketDataType(self, reqId: int, marketDataType: int) -> None:
        data_type = _IBKR_MARKET_DATA_TYPE_BY_CODE.get(
            int(marketDataType),
            "UNKNOWN",
        )
        with self._market_data_lock:
            self._market_data_last_type = data_type
            symbol = self._market_data_req_id_to_symbol.get(int(reqId))
            if symbol:
                quote = self._market_data_quotes.setdefault(
                    symbol,
                    self._new_market_data_quote(symbol),
                )
                quote["market_data_type"] = data_type
                quote["market_data_type_code"] = int(marketDataType)
                quote["updated_at"] = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _new_market_data_quote(symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "bid": None,
            "ask": None,
            "last": None,
            "open": None,
            "close": None,
            "previous_close": None,
            "bid_size": None,
            "ask_size": None,
            "last_size": None,
            "timestamp": None,
            "quote_timestamp": None,
            "bid_timestamp": None,
            "ask_timestamp": None,
            "last_timestamp": None,
            "source": "IBKR",
            "market_data_source": "IBKR",
            "market_data_type": "UNKNOWN",
            "market_data_type_code": None,
            "feed_healthy": None,
            "market_data_feed_healthy": None,
            "error_code": None,
            "error_message": None,
        }

    # -- error handling -----------------------------------------------------

    # Order-level rejection codes from IBKR.  These mean the order did NOT
    # enter the book and will not fill — they must surface as ERROR, not
    # buried as a generic warning, because the order ID returned by
    # placeOrder() looks successful otherwise.
    #   103 — duplicate order ID
    #   110 — price/qty violates exchange rules
    #   200 — no security definition has been found
    #   201 — order rejected (generic; see message for cause)
    #   202 — order cancelled (by exchange / risk)
    #   203 — security is not available for trading
    #   321 — server validation failed (e.g. API in Read-Only mode)
    #   388 — order size too small
    #   434 — order size cannot be zero
    _ORDER_REJECT_CODES = frozenset({103, 110, 200, 201, 202, 203, 321, 388, 434})

    # Known root causes keyed by errorCode — surfaced so the operator
    # gets an actionable hint rather than just the raw IBKR string.
    _ORDER_REJECT_HINTS = {
        321: (
            "TWS API is in Read-Only mode. Open TWS → File → Global "
            "Configuration → API → Settings and uncheck 'Read-Only API', "
            "then restart the API session."
        ),
    }

    def error(self, reqId, _errorTime, errorCode: int, errorString: str,
              advancedOrderRejectJson="") -> None:
        # Informational messages (data-farm connections)
        if errorCode in (2104, 2106, 2158):
            logger.debug("TWS info %s: %s", errorCode, errorString)
            return
        # Critical connection errors
        if errorCode in (502, 503, 504, 1100, 2110):
            logger.error("TWS connection error %s: %s", errorCode, errorString)
            self._connected = False
            self._record_market_data_error(reqId, errorCode, errorString)
            return
        if errorCode in _MARKET_DATA_ERROR_CODES and self._is_market_data_req_id(reqId):
            self._record_market_data_error(reqId, errorCode, errorString)
            logger.warning(
                "TWS market-data error %s (reqId %s): %s",
                errorCode,
                reqId,
                errorString,
            )
            return
        # Order-level rejections — the order did NOT enter the book.
        if errorCode in self._ORDER_REJECT_CODES:
            hint = self._ORDER_REJECT_HINTS.get(errorCode, "")
            logger.error(
                "ORDER REJECTED by TWS — code %s, orderId %s: %s%s",
                errorCode, reqId, errorString,
                f" [fix: {hint}]" if hint else "",
            )
            # Record the rejected order ID so AutonomousLiveRunner can
            # mark the corresponding trade-store entry as FAILED on the
            # next cycle (otherwise the rejected order keeps burning a
            # slot against max_open_live_trades / live_trades_today).
            if isinstance(reqId, int) and reqId > 0:
                with self._rejected_order_ids_lock:
                    self._rejected_order_ids.add(reqId)
                # Emit a local REJECTED order snapshot so paper/live
                # reconciliation logic can detect terminal non-fill
                # outcomes and unwind stale EXIT_PENDING entries.
                self._svc.add_order({
                    "id": str(reqId),
                    "order_id": int(reqId),
                    "broker_order_id": int(reqId),
                    "status": "REJECTED",
                    "error_code": int(errorCode),
                    "error_message": str(errorString or ""),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "tws_error_rejected",
                })
            return
        logger.warning("TWS error %s (reqId %s): %s", errorCode, reqId,
                       errorString)

    def _is_market_data_req_id(self, reqId: Any) -> bool:
        if not isinstance(reqId, int) or reqId <= 0:
            return False
        with self._market_data_lock:
            return reqId in self._market_data_req_id_to_symbol

    def _record_market_data_error(
        self,
        reqId: Any,
        errorCode: int,
        errorString: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        symbol = None
        with self._market_data_lock:
            if isinstance(reqId, int):
                symbol = self._market_data_req_id_to_symbol.get(reqId)
            payload = {
                "req_id": reqId,
                "symbol": symbol,
                "error_code": int(errorCode),
                "error_message": str(errorString or ""),
                "timestamp": now,
            }
            self._market_data_last_error = payload
            if symbol:
                quote = self._market_data_quotes.setdefault(
                    symbol,
                    self._new_market_data_quote(symbol),
                )
                quote["error_code"] = int(errorCode)
                quote["error_message"] = str(errorString or "")
                quote["feed_healthy"] = False
                quote["market_data_feed_healthy"] = False
                quote["updated_at"] = now

    # ------------------------------------------------------------------
    # Order status — tracks fills for bracket reconciliation
    # ------------------------------------------------------------------
    def openOrder(self, orderId: int, contract, order, orderState) -> None:
        payload = {
            "id": str(orderId),
            "order_id": int(orderId),
            "broker_order_id": int(orderId),
            "symbol": str(getattr(contract, "symbol", "") or ""),
            "sec_type": str(getattr(contract, "secType", "") or ""),
            "exchange": str(getattr(contract, "exchange", "") or ""),
            "currency": str(getattr(contract, "currency", "") or ""),
            "action": str(getattr(order, "action", "") or "").upper(),
            "order_type": str(getattr(order, "orderType", "") or "").upper(),
            "quantity": float(getattr(order, "totalQuantity", 0) or 0.0),
            "remaining": None,
            "status": str(getattr(orderState, "status", "") or "Submitted"),
            "parent_id": int(getattr(order, "parentId", 0) or 0),
            "oca_group": str(getattr(order, "ocaGroup", "") or ""),
            "limit_price": float(getattr(order, "lmtPrice", 0) or 0.0),
            "stop_price": float(getattr(order, "auxPrice", 0) or 0.0),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "tws_open_order",
        }
        with self._open_order_snapshots_lock:
            self._open_order_snapshots[int(orderId)] = payload
        self._svc.add_order(payload)

    def orderStatus(self, orderId: int, status: str, filled: float,
                    remaining: float, avgFillPrice: float, permId: int,
                    parentId: int, lastFillPrice: float, clientId: int,
                    whyHeld: str, mktCapPrice: float) -> None:
        payload = {
            "id": str(orderId),
            "order_id": int(orderId),
            "broker_order_id": int(orderId),
            "status": str(status or "").strip().replace(" ", "_").upper(),
            "filled": float(filled or 0.0),
            "remaining": float(remaining or 0.0),
            "avg_fill_price": float(avgFillPrice or 0.0),
            "last_fill_price": float(lastFillPrice or 0.0),
            "perm_id": int(permId or 0),
            "parent_id": int(parentId or 0),
            "client_id": int(clientId or 0),
            "why_held": whyHeld,
            "market_cap_price": float(mktCapPrice or 0.0),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "tws_order_status",
        }
        self._svc.add_order(payload)
        terminal = {"FILLED", "CANCELLED", "REJECTED", "INACTIVE"}
        with self._open_order_snapshots_lock:
            existing = self._open_order_snapshots.get(int(orderId), {})
            existing.update(payload)
            existing["remaining"] = payload["remaining"]
            existing["status"] = status
            existing["parent_id"] = payload["parent_id"]
            if payload["status"] in terminal:
                self._open_order_snapshots.pop(int(orderId), None)
            else:
                self._open_order_snapshots[int(orderId)] = existing

        # Record fully-filled orders so the live runner can reconcile
        # bracket children (target / stop) into CLOSED trade-store
        # entries.  We do NOT distinguish parent vs child here; the
        # reconciler matches against entry/target/stop order IDs.
        if payload["status"] == "FILLED" and payload["remaining"] == 0:
            if isinstance(orderId, int) and orderId > 0:
                with self._filled_order_ids_lock:
                    self._filled_order_ids.add(orderId)
                logger.info(
                    "TWSBridge: order %s fully filled (avg=%.4f, last=%.4f)",
                    orderId, avgFillPrice, lastFillPrice,
                )
            self._svc.event_bus.publish(Event(
                EventType.ORDER_FILLED,
                data=payload,
                source="TWSBridge",
            ))

    def execDetails(self, reqId: int, contract, execution) -> None:
        exec_id = str(getattr(execution, "execId", "") or "").strip()
        if not exec_id:
            order_id = int(getattr(execution, "orderId", 0) or 0)
            exec_id = f"order:{order_id}:{getattr(execution, 'time', '')}"
        payload = {
            "execution_id": exec_id,
            "order_id": int(getattr(execution, "orderId", 0) or 0),
            "broker_order_id": int(getattr(execution, "orderId", 0) or 0),
            "symbol": str(getattr(contract, "symbol", "") or ""),
            "sec_type": str(getattr(contract, "secType", "") or ""),
            "exchange": str(getattr(execution, "exchange", "") or ""),
            "side": str(getattr(execution, "side", "") or "").upper(),
            "quantity": float(getattr(execution, "shares", 0) or 0.0),
            "price": float(getattr(execution, "price", 0) or 0.0),
            "timestamp": str(getattr(execution, "time", "") or ""),
            "liquidity": getattr(execution, "lastLiquidity", None),
            "commission": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "tws_exec_details",
        }
        with self._broker_fill_events_lock:
            existing = self._broker_fill_events.get(exec_id, {})
            if existing.get("commission") is not None:
                payload["commission"] = existing["commission"]
            existing.update(payload)
            self._broker_fill_events[exec_id] = existing
            self._broker_fill_event_dirty_ids.add(exec_id)
        logger.info(
            "TWSBridge: execution %s order=%s qty=%.4f price=%.4f",
            exec_id,
            payload["order_id"],
            payload["quantity"],
            payload["price"],
        )

    def commissionReport(self, commissionReport) -> None:
        exec_id = str(getattr(commissionReport, "execId", "") or "").strip()
        if not exec_id:
            return
        payload = {
            "execution_id": exec_id,
            "commission": float(getattr(commissionReport, "commission", 0) or 0.0),
            "realized_pnl": float(getattr(commissionReport, "realizedPNL", 0) or 0.0),
            "currency": str(getattr(commissionReport, "currency", "") or ""),
            "yield": float(getattr(commissionReport, "yield_", 0) or 0.0),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "commission_source": "tws_commission_report",
        }
        with self._broker_fill_events_lock:
            existing = self._broker_fill_events.get(exec_id, {"execution_id": exec_id})
            existing.update(payload)
            self._broker_fill_events[exec_id] = existing
            self._broker_fill_event_dirty_ids.add(exec_id)
        logger.info(
            "TWSBridge: commission report %s commission=%.4f",
            exec_id,
            payload["commission"],
        )


# ---------------------------------------------------------------------------
# Public bridge class
# ---------------------------------------------------------------------------

class TWSBridge:
    """Manage a TWS API connection on behalf of the web layer.

    Parameters
    ----------
    svc : ServiceManager
        The shared service manager that owns positions / account state.
    config : dict
        Must contain ``host``, ``port``, ``client_id``, ``account``.
    """

    def __init__(self, svc: Any, config: Dict[str, Any]) -> None:
        self._svc = svc
        self._config = config
        self._app: Optional[_BridgeApp] = None
        self._thread: Optional[threading.Thread] = None

    # -- public API ---------------------------------------------------------

    def connect(self, timeout: int = 10) -> bool:
        """Open the socket to TWS, start the reader thread, and subscribe
        to account updates.  Returns ``True`` when ready.
        """
        host = self._config["host"]
        port = self._config["port"]
        client_id = self._config["client_id"]
        account = self._config.get("account", "")

        logger.info("TWSBridge: connecting to %s:%s (client %s)", host, port,
                     client_id)

        self._app = _BridgeApp(self._svc, account)
        self._app.connect(host, port, client_id)

        self._thread = threading.Thread(target=self._app.run, daemon=True,
                                        name="tws-bridge-reader")
        self._thread.start()

        # Wait for the handshake (connectAck + nextValidId)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._app._connected and self._app._ready:
                break
            time.sleep(0.1)

        if not (self._app._connected and self._app._ready):
            logger.error("TWSBridge: connection timed out after %ss", timeout)
            self.disconnect()
            return False

        logger.info("TWSBridge: connected — requesting account updates")

        # Configure delayed market data (will auto-upgrade to live if
        # the user has subscriptions).
        try:
            self._app.reqMarketDataType(3)
        except Exception:
            pass

        # Subscribe to real-time account + portfolio updates
        self._app.reqAccountUpdates(True, account)
        return True

    def disconnect(self) -> None:
        """Cancel subscriptions and tear down the socket."""
        if self._app is None:
            return
        try:
            if self._app.isConnected():
                for req_id in self._market_data_req_ids():
                    try:
                        self._app.cancelMktData(req_id)
                    except Exception:
                        logger.debug(
                            "TWSBridge: cancelMktData failed for req_id=%s",
                            req_id,
                            exc_info=True,
                        )
                account = self._config.get("account", "")
                self._app.reqAccountUpdates(False, account)
                self._app.disconnect()
        except Exception as exc:
            logger.debug("TWSBridge: disconnect error (benign): %s", exc)
        finally:
            self._app = None
            self._thread = None

    @property
    def is_connected(self) -> bool:
        return (self._app is not None
                and self._app._connected
                and self._app._ready)

    def reserve_order_id(self) -> int:
        """Atomically reserve the next IBKR-provided order ID.

        Returns the most recent ``nextValidId(orderId)`` supplied by TWS
        and increments the cached cursor so subsequent reservations
        cannot reuse the same value.  Concurrent callers (e.g. multiple
        dashboard requests racing each other) are serialised through
        the bridge app's order-ID lock.

        Raises
        ------
        RuntimeError
            If the bridge is not connected or TWS has not yet delivered
            a ``nextValidId`` value (the handshake is incomplete).
        """
        if self._app is None or not self._app._connected:
            raise RuntimeError("TWSBridge: not connected to TWS")
        with self._app._order_id_lock:
            current = self._app._next_valid_order_id
            if current is None:
                raise RuntimeError(
                    "TWSBridge: nextValidId handshake not complete; "
                    "no broker-issued order ID is available yet"
                )
            self._app._next_valid_order_id = current + 1
            return current

    def pop_rejected_order_ids(self) -> set[int]:
        """Drain and return broker order IDs TWS has rejected.

        Returns a snapshot of every ID seen via an order-level error
        callback (codes 110/200/201/202/203/321/388/434) since the last
        drain, then clears the internal set.  Consumed by
        :class:`AutonomousLiveRunner` to reconcile the trade store:
        any ``OPEN`` trade whose ``entry_order_id`` is in this set is
        marked ``FAILED`` so it no longer counts against
        ``max_open_live_trades`` or ``max_live_trades_per_day``.

        Safe to call when not connected — returns an empty set.
        """
        if self._app is None:
            return set()
        with self._app._rejected_order_ids_lock:
            drained = set(self._app._rejected_order_ids)
            self._app._rejected_order_ids.clear()
        return drained

    def pop_filled_order_ids(self) -> set[int]:
        """Drain and return broker order IDs TWS has reported fully filled.

        Consumed by :class:`AutonomousLiveRunner` to flip trade-store
        entries to ``CLOSED`` when a bracket child (target or stop) fills.
        Safe to call when not connected — returns an empty set.
        """
        if self._app is None:
            return set()
        with self._app._filled_order_ids_lock:
            drained = set(self._app._filled_order_ids)
            self._app._filled_order_ids.clear()
        return drained

    def pop_broker_fill_events(self) -> list[Dict[str, Any]]:
        """Drain rich broker execution/commission snapshots.

        Unlike ``pop_filled_order_ids()``, this returns execution-level
        records with execution ID, order ID, symbol, side, quantity, price,
        timestamp, exchange/liquidity, and commission when available.  The
        bridge retains snapshots internally so a later commission report can
        re-emit an enriched version of the same execution for idempotent
        ingestion.
        """
        if self._app is None:
            return []
        with self._app._broker_fill_events_lock:
            dirty = set(self._app._broker_fill_event_dirty_ids)
            self._app._broker_fill_event_dirty_ids.clear()
            return [
                dict(self._app._broker_fill_events[exec_id])
                for exec_id in sorted(dirty)
                if exec_id in self._app._broker_fill_events
            ]

    def get_open_order_snapshots(self) -> list[Dict[str, Any]]:
        """Return current broker-visible open order snapshots.

        The list is a read-only snapshot of the latest ``openOrder`` /
        ``orderStatus`` callback state.  It is used by autonomous protection
        verification to prove a protective stop/bracket child is active.
        """
        if self._app is None:
            return []
        with self._app._open_order_snapshots_lock:
            return [dict(order) for order in self._app._open_order_snapshots.values()]

    def subscribe_market_data(self, symbols: Iterable[str]) -> None:
        """Subscribe to IBKR level-I streaming market data for symbols.

        This is a passive quote subscription used by autonomous readiness and
        planning.  It does not submit orders and it does not enable live
        trading.
        """
        if not self.is_connected:
            raise RuntimeError("TWSBridge: not connected to TWS")
        for symbol in _normalise_symbols(symbols):
            with self._app._market_data_lock:
                if symbol in self._app._market_data_symbol_to_req_id:
                    continue
                req_id = self._app._market_data_next_req_id
                self._app._market_data_next_req_id += 1
                self._app._market_data_symbol_to_req_id[symbol] = req_id
                self._app._market_data_req_id_to_symbol[req_id] = symbol
                self._app._market_data_quotes.setdefault(
                    symbol,
                    self._app._new_market_data_quote(symbol),
                )

            contract = Contract()
            contract.symbol = symbol
            contract.secType = "STK"
            contract.exchange = "SMART"
            contract.currency = "USD"
            try:
                # Autonomous live planning requires true real-time data.  If
                # IBKR returns delayed/frozen data anyway, the quote-health
                # guard will reject it before any live order can be submitted.
                self._app.reqMarketDataType(1)
            except Exception:
                logger.debug(
                    "TWSBridge: reqMarketDataType(LIVE) failed before %s subscription",
                    symbol,
                    exc_info=True,
                )
            self._app.reqMktData(
                req_id,
                contract,
                "",
                False,
                False,
                [],
            )
            logger.info(
                "TWSBridge: subscribed market data for %s (req_id=%s)",
                symbol,
                req_id,
            )

    def unsubscribe_market_data(self, symbols: Iterable[str]) -> None:
        """Cancel IBKR market-data subscriptions for symbols."""
        if self._app is None:
            return
        for symbol in _normalise_symbols(symbols):
            with self._app._market_data_lock:
                req_id = self._app._market_data_symbol_to_req_id.pop(symbol, None)
                if req_id is not None:
                    self._app._market_data_req_id_to_symbol.pop(req_id, None)
            if req_id is None:
                continue
            try:
                self._app.cancelMktData(req_id)
                logger.info(
                    "TWSBridge: unsubscribed market data for %s (req_id=%s)",
                    symbol,
                    req_id,
                )
            except Exception:
                logger.exception(
                    "TWSBridge: failed to unsubscribe market data for %s",
                    symbol,
                )

    def get_latest_market_data_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return the latest IBKR quote snapshot for ``symbol``."""
        if self._app is None:
            return None
        key = str(symbol or "").strip().upper()
        if not key:
            return None
        with self._app._market_data_lock:
            quote = self._app._market_data_quotes.get(key)
            return dict(quote) if quote else None

    def get_market_data_status(self) -> Dict[str, Any]:
        """Return provider-level IBKR market-data status."""
        if self._app is None:
            return {
                "provider": "IBKR",
                "connected": False,
                "healthy": False,
                "subscribed_symbols": [],
                "market_data_type": "UNKNOWN",
                "last_error": None,
                "quotes": {},
                "reason": "TWS bridge is not connected",
            }
        with self._app._market_data_lock:
            quotes = {
                symbol: dict(quote)
                for symbol, quote in self._app._market_data_quotes.items()
            }
            subscribed = sorted(self._app._market_data_symbol_to_req_id)
            subscribed_set = set(subscribed)
            active_quotes = {
                symbol: quote
                for symbol, quote in quotes.items()
                if symbol in subscribed_set
            }
            last_error = (
                dict(self._app._market_data_last_error)
                if self._app._market_data_last_error
                else None
            )
            # Symbol-level errors from previously unsubscribed symbols should
            # not keep provider health red forever.
            if isinstance(last_error, dict):
                err_symbol = str(last_error.get("symbol") or "").strip().upper()
                if err_symbol and err_symbol not in subscribed_set:
                    last_error = None
            any_unhealthy_quote = any(
                quote.get("feed_healthy") is False for quote in active_quotes.values()
            )
            healthy = (
                self.is_connected
                and last_error is None
                and not any_unhealthy_quote
            )
            reason = (
                "IBKR market-data stream healthy"
                if healthy
                else "IBKR market-data stream unavailable or degraded"
            )
            return {
                "provider": "IBKR",
                "connected": self.is_connected,
                "healthy": healthy,
                "subscribed_symbols": subscribed,
                "market_data_type": self._app._market_data_last_type,
                "last_error": last_error,
                "quotes": quotes,
                "reason": reason,
            }

    def _market_data_req_ids(self) -> list[int]:
        if self._app is None:
            return []
        lock = getattr(self._app, "_market_data_lock", None)
        reqs = getattr(self._app, "_market_data_req_id_to_symbol", None)
        if lock is None or not isinstance(reqs, dict):
            return []
        with lock:
            return list(reqs)

    def cancel_order(self, broker_order_id: int) -> None:
        """Send a cancellation request to TWS for the given order ID.

        Raises ``RuntimeError`` if the bridge is not currently connected.
        """
        if not self.is_connected:
            raise RuntimeError("TWSBridge: not connected to TWS")
        from ibapi.order_cancel import OrderCancel
        self._app.cancelOrder(broker_order_id, OrderCancel())
        logger.info(
            "TWSBridge: cancel request sent for broker order %s",
            broker_order_id,
        )

    # -- OrderExecutor adapter surface -------------------------------------
    #
    # These attributes and methods let :class:`execution.order_executor.\
    # OrderExecutor` use the bridge directly as its ``tws_adapter``,
    # avoiding the need to open a second EClient socket for live trading
    # (which previously caused mid-cycle disconnects and the cryptic
    # ``'<=' not supported between 'int' and 'NoneType'`` rejection).
    #
    # The bridge exposes exactly the subset of ``TwsTradingAdapter`` that
    # OrderExecutor depends on:
    #   * ``environment`` / ``port`` — for the live confirmation check
    #   * ``ready`` — for the readiness guard
    #   * ``buy`` / ``sell`` / ``close_position`` — order placement
    #   * ``get_all_positions`` — portfolio reconciliation

    @property
    def environment(self) -> str:
        """Return ``"live"`` or ``"paper"`` based on the configured port.

        Custom/unknown ports default to ``"paper"`` to fail-closed for the
        live confirmation check; OrderExecutor will then reject the order
        with a clear port-mismatch message instead of submitting it.
        """
        port = int(self._config.get("port") or 0)
        if port in LIVE_PORTS:
            return "live"
        return "paper"

    @property
    def port(self) -> int:
        """Configured TWS port. Stable across reconnects (unlike
        ``EClient.port`` on the underlying app, which is nulled by
        ``EClient.reset()`` on every socket close)."""
        return int(self._config.get("port") or 0)

    @property
    def ready(self) -> bool:
        """OrderExecutor-compatible readiness flag."""
        return self.is_connected

    def buy(
        self,
        symbol: str,
        quantity: int,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> int:
        """Submit a BUY order through the persistent bridge connection."""
        return self._place_order(
            symbol, "BUY", quantity, order_type, limit_price, stop_price
        )

    def sell(
        self,
        symbol: str,
        quantity: int,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> int:
        """Submit a SELL order through the persistent bridge connection."""
        return self._place_order(
            symbol, "SELL", quantity, order_type, limit_price, stop_price
        )

    def close_position(
        self, symbol: str, order_type: str = "MARKET"
    ) -> Optional[int]:
        """Close an existing stock position via an opposite-side order.

        Returns the broker order ID, or ``None`` if no position is held.
        Raises ``ValueError`` if ``order_type`` is ``"LIMIT"`` (use
        ``buy``/``sell`` with an explicit ``limit_price`` instead).
        """
        if order_type.upper() == "LIMIT":
            raise ValueError(
                "LIMIT order type is not supported for close_position; "
                "use buy/sell with an explicit limit_price instead"
            )
        positions = self.get_all_positions()
        position = positions.get(symbol)
        if position is None or position.quantity == 0:
            return None
        qty = int(abs(position.quantity))
        if position.quantity > 0:
            return self.sell(symbol, qty, order_type)
        return self.buy(symbol, qty, order_type)

    def get_all_positions(self) -> Dict[str, Position]:
        """Return current stock positions in OrderExecutor-compatible form.

        Reads from the ServiceManager's position cache (populated by
        ``_BridgeApp.updatePortfolio``). Only stock (``STK``) positions are
        returned — option positions use a different symbol format and are
        not subject to share-quantity reconciliation by OrderExecutor.
        """
        try:
            raw = self._svc.get_positions()
        except Exception:
            logger.exception("TWSBridge: failed to read positions from ServiceManager")
            return {}

        result: Dict[str, Position] = {}
        for symbol, data in raw.items():
            if (data.get("sec_type") or "STK") != "STK":
                continue
            try:
                qty = int(float(data.get("quantity") or 0))
            except (TypeError, ValueError):
                continue
            if qty == 0:
                continue
            result[symbol] = Position(
                symbol=symbol,
                quantity=qty,
                average_cost=float(data.get("entry_price") or 0.0),
                current_price=float(data.get("current_price") or 0.0),
                realized_pnl=float(data.get("realized_pnl") or 0.0),
            )
        return result

    def _place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str,
        limit_price: Optional[float],
        stop_price: Optional[float],
    ) -> int:
        """Build the IB contract + order objects and submit via the
        persistent ``_BridgeApp`` connection.

        Reserves the next broker-issued order ID atomically via
        :meth:`reserve_order_id` to avoid colliding with concurrent
        requests (e.g. dashboard manual cancels racing autonomous orders).
        """
        if not self.is_connected:
            raise RuntimeError("TWSBridge: not connected to TWS")

        order_id = self.reserve_order_id()

        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        ib_order = IBOrder()
        ib_order.action = action
        ib_order.totalQuantity = quantity
        ib_order.orderType = order_type
        if order_type == "LIMIT" and limit_price is not None:
            ib_order.lmtPrice = float(limit_price)
        elif order_type == "STOP" and stop_price is not None:
            ib_order.auxPrice = float(stop_price)
        elif order_type == "STOP_LIMIT" and limit_price is not None and stop_price is not None:
            ib_order.lmtPrice = float(limit_price)
            ib_order.auxPrice = float(stop_price)

        self._app.placeOrder(order_id, contract, ib_order)
        logger.info(
            "TWSBridge: placed %s order %s for %s x%s (%s)",
            action, order_id, symbol, quantity, order_type,
        )
        return order_id

    # ------------------------------------------------------------------
    # Bracket orders (parent BUY LMT + child target SELL LMT + child stop)
    # ------------------------------------------------------------------
    def place_bracket_buy(
        self,
        symbol: str,
        quantity: int,
        limit_price: float,
        target_price: float,
        stop_price: float,
    ) -> Dict[str, int]:
        """Submit a 3-leg bracket (parent BUY LMT + child SELL LMT target
        + child SELL STP stop) atomically.

        All three orders are submitted in sequence with ``transmit`` set
        to ``False`` on the parent and target legs and ``True`` on the
        stop leg so TWS only activates the bracket after the final
        ``placeOrder`` call.  TWS attaches the children to the parent
        via ``parentId`` and treats them as a one-cancels-the-other
        group: when the parent fills, the children become live; when
        either child fills, the other is cancelled by TWS.

        Returns ``{"parent_id": int, "target_id": int, "stop_id": int}``.
        Raises :class:`RuntimeError` if the bridge is not connected.
        Raises :class:`ValueError` for invalid prices/quantity.
        """
        if not self.is_connected:
            raise RuntimeError("TWSBridge: not connected to TWS")
        if quantity <= 0:
            raise ValueError(f"quantity must be > 0; got {quantity!r}")
        if limit_price <= 0 or target_price <= 0 or stop_price <= 0:
            raise ValueError(
                f"bracket prices must be > 0; got limit={limit_price} "
                f"target={target_price} stop={stop_price}"
            )
        if target_price <= limit_price:
            raise ValueError(
                f"bracket target ({target_price}) must be > entry limit "
                f"({limit_price}) for a long bracket"
            )
        if stop_price >= limit_price:
            raise ValueError(
                f"bracket stop ({stop_price}) must be < entry limit "
                f"({limit_price}) for a long bracket"
            )

        parent_id = self.reserve_order_id()
        target_id = self.reserve_order_id()
        stop_id = self.reserve_order_id()

        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        parent = IBOrder()
        parent.orderId = parent_id
        parent.action = "BUY"
        parent.totalQuantity = quantity
        parent.orderType = "LMT"
        parent.lmtPrice = float(limit_price)
        parent.transmit = False

        target = IBOrder()
        target.orderId = target_id
        target.action = "SELL"
        target.totalQuantity = quantity
        target.orderType = "LMT"
        target.lmtPrice = float(target_price)
        target.parentId = parent_id
        target.transmit = False

        stop = IBOrder()
        stop.orderId = stop_id
        stop.action = "SELL"
        stop.totalQuantity = quantity
        stop.orderType = "STP"
        stop.auxPrice = float(stop_price)
        stop.parentId = parent_id
        stop.transmit = True  # transmits the whole bracket

        self._app.placeOrder(parent_id, contract, parent)
        self._app.placeOrder(target_id, contract, target)
        self._app.placeOrder(stop_id, contract, stop)
        logger.info(
            "TWSBridge: placed BRACKET BUY %s x%s @ limit=%.2f "
            "target=%.2f stop=%.2f (parent=%s, target=%s, stop=%s)",
            symbol, quantity, limit_price, target_price, stop_price,
            parent_id, target_id, stop_id,
        )
        return {"parent_id": parent_id, "target_id": target_id, "stop_id": stop_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(val: Any) -> float:
    """Safely convert a string or number to float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _positive_float(val: Any) -> Optional[float]:
    """Return a positive float or ``None`` for missing/invalid prices."""
    try:
        out = float(val)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _normalise_symbols(symbols: Iterable[str]) -> list[str]:
    out = []
    seen = set()
    for raw in symbols or []:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    return out
