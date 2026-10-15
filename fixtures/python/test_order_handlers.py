import unittest

from order_store import ORDER_PENDING
from respond import CODE_BAD_JSON, CODE_VALIDATION_FAILED
from testutil import decode_data, decode_list, do_request, error_code, new_test_server


class ListOrdersTest(unittest.TestCase):
    def test_list_orders(self):
        s = new_test_server()
        resp = do_request(s, "GET", "/orders?limit=1&offset=1")
        self.assertEqual(resp.status, 200, resp.body)
        orders, page = decode_list(resp)
        self.assertEqual([o["id"] for o in orders], ["ord_000002"])
        self.assertEqual(page["total"], 2)


class CreateOrderTest(unittest.TestCase):
    def test_create_order(self):
        cases = [
            {"name": "ok", "body": '{"user_id":"usr_000002","items":[{"product_id":"prd_000001","quantity":2},{"product_id":"prd_000003","quantity":1}]}',
             "want_code": 201, "want_total": 2 * 4999 + 18999},
            {"name": "bad json", "body": "nope", "want_code": 400, "want_err": CODE_BAD_JSON},
            {"name": "no items", "body": '{"user_id":"usr_000001","items":[]}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "zero quantity", "body": '{"user_id":"usr_000001","items":[{"product_id":"prd_000001","quantity":0}]}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "unknown user", "body": '{"user_id":"usr_000099","items":[{"product_id":"prd_000001","quantity":1}]}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "unknown product", "body": '{"user_id":"usr_000001","items":[{"product_id":"prd_000099","quantity":1}]}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "POST", "/orders", c["body"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_err" in c:
                    self.assertEqual(error_code(resp), c["want_err"])
                    continue
                order = decode_data(resp)
                self.assertEqual((order["id"], order["total_cents"], order["status"]), ("ord_000003", c["want_total"], ORDER_PENDING))


if __name__ == "__main__":
    unittest.main()
