"""Tests for ``execution.autonomous_paper_adapter``."""

from __future__ import annotations

import pytest

from execution.autonomous_paper_adapter import AutonomousPaperAdapter


class _FakeApp:
    def __init__(self):
        self.placed = []

    def placeOrder(self, order_id, contract, order):
        self.placed.append({
            "order_id": order_id,
            "symbol": contract.symbol,
            "secType": contract.secType,
            "action": order.action,
            "quantity": order.totalQuantity,
            "order_type": order.orderType,
            "lmt_price": order.lmtPrice,
            "tif": order.tif,
        })


class _FakeBridge:
    def __init__(self, ready=True, app=None, next_id=1001):
        self.is_connected = ready
        self._app = app or _FakeApp()
        self._next_id = next_id
        self.reserve_calls = 0

    def reserve_order_id(self):
        self.reserve_calls += 1
        oid = self._next_id
        self._next_id += 1
        return oid


class _FakeServiceManager:
    def __init__(self, *, connected=True, env="paper", bridge=None):
        self.connected = connected
        self.connection_env = env
        self._tws_bridge = bridge or _FakeBridge()


class TestReadiness:
    def test_not_connected_is_not_ready(self):
        adapter = AutonomousPaperAdapter(_FakeServiceManager(connected=False))
        assert adapter.is_ready() is False

    def test_live_env_is_not_ready(self):
        adapter = AutonomousPaperAdapter(_FakeServiceManager(env="live"))
        assert adapter.is_ready() is False

    def test_paper_connected_bridge_ready(self):
        adapter = AutonomousPaperAdapter(_FakeServiceManager())
        assert adapter.is_ready() is True

    def test_missing_bridge_is_not_ready(self):
        svc = _FakeServiceManager()
        svc._tws_bridge = None
        adapter = AutonomousPaperAdapter(svc)
        assert adapter.is_ready() is False


class TestBuyPlacesLimitOrder:
    def test_buy_routes_through_bridge_app_with_limit_price(self):
        bridge = _FakeBridge()
        svc = _FakeServiceManager(bridge=bridge)
        adapter = AutonomousPaperAdapter(svc)

        order_id = adapter.buy(
            symbol="AAPL", quantity=10, order_type="LIMIT", limit_price=195.50,
        )
        assert isinstance(order_id, int)
        assert len(bridge._app.placed) == 1
        placed = bridge._app.placed[0]
        assert placed["symbol"] == "AAPL"
        assert placed["action"] == "BUY"
        assert placed["quantity"] == 10
        assert placed["order_type"] == "LMT"  # IB API ticker for LIMIT
        assert placed["lmt_price"] == 195.50
        # Defensive day-only TIF to avoid leaving GTC orders on the book.
        assert placed["tif"] == "DAY"

    def test_sell_routes_through_bridge_app(self):
        bridge = _FakeBridge()
        adapter = AutonomousPaperAdapter(_FakeServiceManager(bridge=bridge))
        adapter.sell(
            symbol="AAPL", quantity=5, order_type="LIMIT", limit_price=200.0,
        )
        assert bridge._app.placed[0]["action"] == "SELL"


class TestSafetyRejections:
    def test_non_limit_order_type_raises(self):
        adapter = AutonomousPaperAdapter(_FakeServiceManager())
        with pytest.raises(RuntimeError, match="LIMIT"):
            adapter.buy(symbol="AAPL", quantity=1, order_type="MARKET",
                        limit_price=None)

    def test_missing_limit_price_raises(self):
        adapter = AutonomousPaperAdapter(_FakeServiceManager())
        with pytest.raises(RuntimeError, match="limit_price"):
            adapter.buy(symbol="AAPL", quantity=1, order_type="LIMIT",
                        limit_price=None)

    def test_zero_quantity_raises(self):
        adapter = AutonomousPaperAdapter(_FakeServiceManager())
        with pytest.raises(RuntimeError, match="quantity"):
            adapter.buy(symbol="AAPL", quantity=0, order_type="LIMIT",
                        limit_price=100.0)

    def test_buy_when_not_ready_raises(self):
        adapter = AutonomousPaperAdapter(
            _FakeServiceManager(connected=False)
        )
        with pytest.raises(RuntimeError, match="not ready"):
            adapter.buy(symbol="AAPL", quantity=1, order_type="LIMIT",
                        limit_price=100.0)

    def test_live_connection_blocks_orders(self):
        adapter = AutonomousPaperAdapter(_FakeServiceManager(env="live"))
        with pytest.raises(RuntimeError, match="not ready"):
            adapter.buy(symbol="AAPL", quantity=1, order_type="LIMIT",
                        limit_price=100.0)


class TestOrderIdReservation:
    """Order IDs must come from TWS via ``reserve_order_id``."""

    def test_buy_uses_bridge_provided_order_id(self):
        bridge = _FakeBridge(next_id=4242)
        adapter = AutonomousPaperAdapter(_FakeServiceManager(bridge=bridge))

        order_id = adapter.buy(
            symbol="AAPL", quantity=1, order_type="LIMIT", limit_price=10.0,
        )
        assert order_id == 4242
        assert bridge.reserve_calls == 1
        assert bridge._app.placed[0]["order_id"] == 4242

    def test_consecutive_orders_get_distinct_ids(self):
        bridge = _FakeBridge(next_id=7000)
        adapter = AutonomousPaperAdapter(_FakeServiceManager(bridge=bridge))

        first = adapter.buy(
            symbol="AAPL", quantity=1, order_type="LIMIT", limit_price=10.0,
        )
        second = adapter.sell(
            symbol="AAPL", quantity=1, order_type="LIMIT", limit_price=11.0,
        )
        assert first == 7000
        assert second == 7001
        assert first != second
        placed_ids = [p["order_id"] for p in bridge._app.placed]
        assert placed_ids == [7000, 7001]

    def test_missing_reserve_order_id_method_raises(self):
        class _BadBridge:
            is_connected = True
            _app = _FakeApp()

        svc = _FakeServiceManager(bridge=_BadBridge())
        adapter = AutonomousPaperAdapter(svc)
        with pytest.raises(RuntimeError, match="reserve_order_id"):
            adapter.buy(symbol="AAPL", quantity=1, order_type="LIMIT",
                        limit_price=10.0)

    def test_bridge_runtime_error_propagates(self):
        class _UnreadyBridge:
            is_connected = True
            _app = _FakeApp()

            def reserve_order_id(self):
                raise RuntimeError("nextValidId handshake not complete")

        adapter = AutonomousPaperAdapter(
            _FakeServiceManager(bridge=_UnreadyBridge())
        )
        with pytest.raises(RuntimeError, match="nextValidId"):
            adapter.buy(symbol="AAPL", quantity=1, order_type="LIMIT",
                        limit_price=10.0)
