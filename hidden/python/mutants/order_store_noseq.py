"""In-memory store of orders."""

import dataclasses
import threading
from dataclasses import dataclass, field

from ids import format_id

ORDER_PENDING = "pending"
ORDER_PAID = "paid"
ORDER_CANCELLED = "cancelled"


@dataclass
class OrderItem:
    product_id: str
    quantity: int


@dataclass
class Order:
    id: str
    user_id: str
    items: list = field(default_factory=list)
    total_cents: int = 0
    status: str = ORDER_PENDING


def _copy(order):
    return dataclasses.replace(order, items=[dataclasses.replace(it) for it in order.items])


class OrderStore:
    """In-memory, thread-safe store of orders. Methods return copies."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}
        self._seq = 0

    def create(self, order):
        """Assigns the next ID, stores the order, and returns the stored copy."""
        with self._lock:
            order = _copy(dataclasses.replace(order, id=format_id("ord", self._seq + 1)))
            self._items[order.id] = order
            return _copy(order)

    def get(self, id):
        """Returns the order, or None if there is no order with that ID."""
        with self._lock:
            order = self._items.get(id)
            return _copy(order) if order else None

    def set_status(self, id, status):
        """Updates the status and returns the updated order, or None if missing."""
        with self._lock:
            order = self._items.get(id)
            if order is None:
                return None
            order.status = status
            return _copy(order)

    def list(self):
        """Returns all orders sorted by ID."""
        with self._lock:
            return [_copy(o) for o in sorted(self._items.values(), key=lambda o: o.id)]
