import json
import unittest

from order_store import ORDER_CANCELLED, ORDER_PAID
from respond import CODE_CONFLICT, CODE_NOT_FOUND
from testutil import decode_data, do_request, error_code, new_test_server


class HiddenCancelOrderTest(unittest.TestCase):
    def test_cancel_order(self):
        cases = [
            {"name": "pending", "id": "ord_000001", "want_code": 200, "want_status": ORDER_CANCELLED},
            {"name": "paid", "id": "ord_000002", "want_code": 409, "want_err": CODE_CONFLICT, "want_status": ORDER_PAID},
            {"name": "missing", "id": "ord_000099", "want_code": 404, "want_err": CODE_NOT_FOUND, "want_msg": "order ord_000099 not found"},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "POST", f"/orders/{c['id']}/cancel")
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_err" in c:
                    err = json.loads(resp.body)["error"]
                    self.assertEqual(err["code"], c["want_err"])
                    if "want_msg" in c:
                        self.assertEqual(err["message"], c["want_msg"])
                else:
                    got = decode_data(resp)
                    self.assertEqual((got["id"], got["status"]), (c["id"], ORDER_CANCELLED))
                if "want_status" in c:
                    self.assertEqual(s.orders.get(c["id"]).status, c["want_status"])

    def test_cancel_twice(self):
        s = new_test_server()
        self.assertEqual(do_request(s, "POST", "/orders/ord_000001/cancel").status, 200)
        resp = do_request(s, "POST", "/orders/ord_000001/cancel")
        self.assertEqual(resp.status, 409, resp.body)
        self.assertEqual(error_code(resp), CODE_CONFLICT)


if __name__ == "__main__":
    unittest.main()
