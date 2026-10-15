"""In-memory store of products."""

import dataclasses
import threading
from dataclasses import dataclass

from ids import format_id


@dataclass
class Product:
    """Prices are always integer cents, never floats."""

    id: str
    name: str
    price_cents: int
    stock: int


class ProductStore:
    """In-memory, thread-safe store of products. Methods return copies."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}
        self._seq = 0

    def create(self, product):
        """Assigns the next ID, stores the product, and returns the stored copy."""
        with self._lock:
            self._seq += 1
            product = dataclasses.replace(product, id=format_id("prd", self._seq))
            self._items[product.id] = product
            return dataclasses.replace(product)

    def get(self, id):
        """Returns the product, or None if there is no product with that ID."""
        with self._lock:
            product = self._items.get(id)
            return dataclasses.replace(product) if product else None

    def list(self):
        """Returns all products sorted by ID."""
        with self._lock:
            return [dataclasses.replace(p) for p in sorted(self._items.values(), key=lambda p: p.id)]
