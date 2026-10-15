"""In-memory store of users."""

import dataclasses
import threading
from dataclasses import dataclass

from ids import format_id


@dataclass
class User:
    id: str
    email: str
    name: str


class UserStore:
    """In-memory, thread-safe store of users. Methods return copies."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}
        self._seq = 0

    def create(self, user):
        """Assigns the next ID, stores the user, and returns the stored copy."""
        with self._lock:
            self._seq += 1
            user = dataclasses.replace(user, id=format_id("usr", self._seq))
            self._items[user.id] = user
            return dataclasses.replace(user)

    def get(self, id):
        """Returns the user, or None if there is no user with that ID."""
        with self._lock:
            user = self._items.get(id)
            return dataclasses.replace(user) if user else None

    def find_by_email(self, email):
        """Matches case-insensitively. Returns None if no user matches."""
        with self._lock:
            for user in self._items.values():
                if user.email.lower() == email.lower():
                    return dataclasses.replace(user)
            return None

    def list(self):
        """Returns all users sorted by ID."""
        with self._lock:
            return [dataclasses.replace(u) for u in sorted(self._items.values(), key=lambda u: u.id)]

    def delete(self, id):
        """Reports whether the user existed."""
        with self._lock:
            return self._items.pop(id, None) is not None

    def update_name(self, id, name):
        """Sets the user's name and returns the updated user, or None if missing."""
        with self._lock:
            user = self._items.get(id)
            if user is None:
                return None
            user.name = name
            return dataclasses.replace(user)
