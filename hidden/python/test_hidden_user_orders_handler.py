import unittest

from order_store import Order, OrderItem
from request import Request
from respond import CODE_BAD_QUERY, CODE_NOT_FOUND
from server import Router
from testutil import decode_list, error_code, new_test_server
from user_orders import user_order_routes


def hidden_user_orders_request(s, path, query=None):
    router = Router()
    user_order_routes(s, router)
    return router.serve(Request(method="GET", path=path, query=query or {}))


class HiddenListUserOrdersTest(unittest.TestCase):
    def test_list(self):
        s = new_test_server()
        s.orders.create(Order("", "usr_000001", items=[OrderItem("prd_000003", 1)], total_cents=18999))
        cases = [
            {"name": "two orders", "path": "/users/usr_000001/orders", "want_ids": ["ord_000001", "ord_000003"],
             "want_page": {"limit": 20, "offset": 0, "total": 2}},
            {"name": "paged", "path": "/users/usr_000001/orders", "query": {"limit": "1", "offset": "1"}, "want_ids": ["ord_000003"],
             "want_page": {"limit": 1, "offset": 1, "total": 2}},
            {"name": "other user", "path": "/users/usr_000002/orders", "want_ids": ["ord_000002"],
             "want_page": {"limit": 20, "offset": 0, "total": 1}},
            {"name": "missing user", "path": "/users/usr_000099/orders", "want_code": 404, "want_err": CODE_NOT_FOUND},
            {"name": "bad query", "path": "/users/usr_000001/orders", "query": {"limit": "0"}, "want_code": 400, "want_err": CODE_BAD_QUERY},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                resp = hidden_user_orders_request(s, c["path"], c.get("query"))
                self.assertEqual(resp.status, c.get("want_code", 200), resp.body)
                if "want_err" in c:
                    self.assertEqual(error_code(resp), c["want_err"])
                    continue
                orders, page = decode_list(resp)
                self.assertEqual(page, c["want_page"])
                self.assertEqual([o["id"] for o in orders], c["want_ids"])


if __name__ == "__main__":
    unittest.main()
