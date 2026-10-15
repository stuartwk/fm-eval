"""In-memory store of reviews."""

import dataclasses
import threading
from dataclasses import dataclass

from ids import format_id


@dataclass
class Review:
    """Ratings are whole stars from 1 to 5."""

    id: str
    product_id: str
    user_id: str
    rating: int
    body: str = ""


class ReviewStore:
    """In-memory, thread-safe store of reviews. Methods return copies."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}
        self._seq = 0

    def create(self, review):
        """Assigns the next ID, stores the review, and returns the stored copy."""
        with self._lock:
            review = dataclasses.replace(review, id=format_id("rev", self._seq + 1))
            self._items[review.id] = review
            return dataclasses.replace(review)

    def get(self, id):
        """Returns the review, or None if there is no review with that ID."""
        with self._lock:
            review = self._items.get(id)
            return dataclasses.replace(review) if review else None

    def list_by_product(self, product_id):
        """Returns the product's reviews sorted by ID."""
        with self._lock:
            matches = [r for r in self._items.values() if r.product_id == product_id]
            return [dataclasses.replace(r) for r in sorted(matches, key=lambda r: r.id)]
