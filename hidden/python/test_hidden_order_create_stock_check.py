import json
import unittest

from respond import CODE_VALIDATION_FAILED
from testutil import do_request, new_test_server


class HiddenCreateOrderStockCheckTest(unittest.TestCase):
    def test_stock_check(self):
        cases = [
            {"name": "exactly in stock", "body": '{"user_id":"usr_000001","items":[{"product_id":"prd_000003","quantity":3}]}', "want_code": 201},
            {"name": "over stock", "body": '{"user_id":"usr_000001","items":[{"product_id":"prd_000003","quantity":4}]}', "want_code": 422,
             "want_msg": "items[0].quantity: exceeds stock"},
            {"name": "out of stock second item", "body": '{"user_id":"usr_000001","items":[{"product_id":"prd_000001","quantity":1},{"product_id":"prd_000002","quantity":1}]}',
             "want_code": 422, "want_msg": "items[1].quantity: exceeds stock"},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "POST", "/orders", c["body"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_msg" in c:
                    err = json.loads(resp.body)["error"]
                    self.assertEqual((err["code"], err["message"]), (CODE_VALIDATION_FAILED, c["want_msg"]))
                    self.assertEqual(len(s.orders.list()), 2, "an order was stored despite the error")


if __name__ == "__main__":
    unittest.main()
