"""Shared test helpers.

new_test_server() returns a server seeded with a fixed dataset:

    usr_000001 Ada Lovelace  ada@example.com
    usr_000002 Grace Hopper  grace@example.com
    prd_000001 Keyboard      4999 cents, stock 10
    prd_000002 Mouse         1999 cents, stock 0
    prd_000003 Monitor      18999 cents, stock 3
    ord_000001 usr_000001    2 x prd_000001, pending
    ord_000002 usr_000002    1 x prd_000003, paid
"""

import json
from urllib.parse import parse_qsl, urlsplit

from order_store import ORDER_PAID, ORDER_PENDING, Order, OrderItem
from product_store import Product
from request import Request
from server import Server
from user_store import User


def new_test_server():
    s = Server()
    s.users.create(User(id="", email="ada@example.com", name="Ada Lovelace"))
    s.users.create(User(id="", email="grace@example.com", name="Grace Hopper"))
    s.products.create(Product(id="", name="Keyboard", price_cents=4999, stock=10))
    s.products.create(Product(id="", name="Mouse", price_cents=1999, stock=0))
    s.products.create(Product(id="", name="Monitor", price_cents=18999, stock=3))
    s.orders.create(Order(id="", user_id="usr_000001", items=[OrderItem("prd_000001", 2)], total_cents=9998, status=ORDER_PENDING))
    s.orders.create(Order(id="", user_id="usr_000002", items=[OrderItem("prd_000003", 1)], total_cents=18999, status=ORDER_PAID))
    return s


def do_request(s, method, path, body=""):
    """Sends a request through the server's full router."""
    url = urlsplit(path)
    req = Request(method=method, path=url.path, query=dict(parse_qsl(url.query, keep_blank_values=True)), body=body)
    return s.routes().serve(req)


def decode_data(resp):
    """Returns the "data" value of a success response."""
    return json.loads(resp.body)["data"]


def decode_list(resp):
    """Returns (data, page) from a list response."""
    payload = json.loads(resp.body)
    return payload["data"], payload["page"]


def error_code(resp):
    """Returns error.code from an error response."""
    return json.loads(resp.body)["error"]["code"]
