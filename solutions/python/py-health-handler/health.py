"""Health check endpoint."""

from dataclasses import dataclass
from functools import partial

from respond import write_json


def health_routes(s, router):
    router.handle("GET /healthz", partial(handle_health, s))


@dataclass
class HealthResponse:
    status: str
    users: int
    products: int
    orders: int


def handle_health(s, req):
    return write_json(200, HealthResponse(
        status="ok",
        users=len(s.users.list()),
        products=len(s.products.list()),
        orders=len(s.orders.list()),
    ))
