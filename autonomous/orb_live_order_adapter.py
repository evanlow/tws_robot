"""ORB Phase 6 — narrow live broker order adapter interface (#229).

Defines the *only* shape of live order this phase may ever submit: a single
protected long bracket/OCA group (BUY LIMIT entry + SELL STOP + SELL LIMIT
target). There is no generic "place any order" method here and no path to a
raw market order — every concrete adapter implementation can only submit,
confirm, or cancel this one narrow, fully-protected order group.

Safety posture (Prime Directive):
- No generic live-order API. Callers cannot ask this adapter to submit an
  arbitrary order; :class:`ORBLiveBracketOrderRequest` is the only shape it
  understands, and it is always a marketable-limit entry with mandatory stop
  and target legs.
- Fail closed by default. :class:`RefusingLiveOrderAdapter` — used whenever no
  real broker adapter has been explicitly wired in — refuses every submit
  call and never reports protection as broker-visible.
- Tests must use :class:`FakeORBLiveOrderAdapter` (or an equivalent fake).
  This module never calls a real broker itself.
"""

from __future__ import annotations

import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Set

ORDER_TYPE_LIMIT = "LIMIT"
ORDER_TYPE_STOP = "STOP"


@dataclass(frozen=True)
class ORBLiveBracketOrderRequest:
    """The exact protected long bracket/OCA shape this adapter may ever submit.

    Mirrors :class:`autonomous.orb_live_order_rehearsal.ORBAssistedLiveRehearsalPackage`
    1:1. ``entry_order_type`` is always ``LIMIT`` and the stop leg is always a
    ``STOP`` order — a raw market order can never be represented here.
    """

    order_group_id: str
    symbol: str
    account_id: str
    quantity: int
    entry_order_type: str
    entry_limit_price: float
    stop_price: float
    target_price: float
    oca_group: str
    time_in_force: str = "DAY"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ORBLiveBrokerSubmission:
    """Result of submitting a protected long bracket/OCA order group."""

    order_group_id: str
    entry_broker_order_id: str
    stop_broker_order_id: str
    target_broker_order_id: str
    protection_broker_visible: bool
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ORBLiveOrderAdapterError(RuntimeError):
    """Raised when the live broker adapter cannot submit/confirm/cancel."""


class ORBLiveOrderAdapter(ABC):
    """Narrow, mockable interface for the one protected ORB tiny-live order shape.

    Deliberately does *not* expose a generic "place any order" method. Every
    method here operates only on the protected long bracket/OCA package built
    from a Phase 5 rehearsal package; there is no path to a raw market order
    or an arbitrary live order through this interface.
    """

    @abstractmethod
    def submit_protected_long_bracket(
        self, request: ORBLiveBracketOrderRequest
    ) -> ORBLiveBrokerSubmission:
        """Submit the protected long bracket/OCA order group.

        Implementations must never construct anything other than a
        marketable-limit entry with a mandatory stop and target leg.
        """

    @abstractmethod
    def is_protection_broker_visible(self, order_group_id: str) -> bool:
        """Return whether bracket/OCA protection is currently broker-visible."""

    @abstractmethod
    def cancel_if_pending(self, order_group_id: str) -> bool:
        """Cancel the order group if it is still pending.

        Returns ``True`` if a cancel was issued, ``False`` if there was
        nothing pending to cancel (e.g. unknown group or already filled).
        """


class RefusingLiveOrderAdapter(ORBLiveOrderAdapter):
    """Safe-by-default adapter: refuses every call.

    Used whenever no real broker adapter has been explicitly wired in, so
    tiny-live submission can never silently "succeed" without a deliberately
    configured broker adapter. Fails closed.
    """

    def submit_protected_long_bracket(
        self, request: ORBLiveBracketOrderRequest
    ) -> ORBLiveBrokerSubmission:
        raise ORBLiveOrderAdapterError(
            "no live broker adapter is configured; tiny-live order submission "
            "is refused"
        )

    def is_protection_broker_visible(self, order_group_id: str) -> bool:
        return False

    def cancel_if_pending(self, order_group_id: str) -> bool:
        return False


class FakeORBLiveOrderAdapter(ORBLiveOrderAdapter):
    """In-memory fake broker adapter for tests. Never calls a real broker.

    Deterministic ids, thread-safe, and lets tests control whether the
    simulated broker confirms broker-visible protection so the fail-closed
    "protection not broker-visible" path can be exercised without a real
    broker connection.
    """

    def __init__(
        self,
        *,
        protection_broker_visible: bool = True,
        id_prefix: str = "FAKE-LIVE",
        raise_on_submit: Optional[Exception] = None,
    ) -> None:
        self.protection_broker_visible = protection_broker_visible
        self.raise_on_submit = raise_on_submit
        self._prefix = id_prefix
        self._seq = 0
        self._lock = threading.Lock()
        self.submitted: Dict[str, ORBLiveBracketOrderRequest] = {}
        self.cancelled: Set[str] = set()
        self.submit_calls = 0
        self.cancel_calls = 0
        self.protection_check_calls = 0

    def _next_id(self, suffix: str) -> str:
        with self._lock:
            self._seq += 1
            return f"{self._prefix}-{suffix}-{self._seq:06d}-{uuid.uuid4().hex[:8]}"

    def submit_protected_long_bracket(
        self, request: ORBLiveBracketOrderRequest
    ) -> ORBLiveBrokerSubmission:
        with self._lock:
            self.submit_calls += 1
        if self.raise_on_submit is not None:
            raise self.raise_on_submit
        if request.entry_order_type != ORDER_TYPE_LIMIT:
            raise ORBLiveOrderAdapterError(
                "refusing to submit a non-limit entry; raw market orders are "
                "impossible from the ORB tiny-live adapter"
            )
        with self._lock:
            self.submitted[request.order_group_id] = request
        return ORBLiveBrokerSubmission(
            order_group_id=request.order_group_id,
            entry_broker_order_id=self._next_id("ENTRY"),
            stop_broker_order_id=self._next_id("STOP"),
            target_broker_order_id=self._next_id("TARGET"),
            protection_broker_visible=self.protection_broker_visible,
        )

    def is_protection_broker_visible(self, order_group_id: str) -> bool:
        with self._lock:
            self.protection_check_calls += 1
            return order_group_id in self.submitted and self.protection_broker_visible

    def cancel_if_pending(self, order_group_id: str) -> bool:
        with self._lock:
            self.cancel_calls += 1
            if order_group_id in self.submitted and order_group_id not in self.cancelled:
                self.cancelled.add(order_group_id)
                return True
            return False
