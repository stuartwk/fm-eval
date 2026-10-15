import unittest

from respond import CODE_BAD_QUERY
from testutil import decode_data, do_request, error_code, new_test_server


class HiddenListProductsInStockTest(unittest.TestCase):
    def test_filter(self):
        cases = [
            {"name": "all", "query": "", "want_ids": ["prd_000001", "prd_000002", "prd_000003"]},
            {"name": "in stock", "query": "?in_stock=true", "want_ids": ["prd_000001", "prd_000003"]},
            {"name": "out of stock", "query": "?in_stock=false", "want_ids": ["prd_000002"]},
            {"name": "bad value", "query": "?in_stock=yes", "want_code": 400},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "GET", "/products" + c["query"])
                self.assertEqual(resp.status, c.get("want_code", 200), resp.body)
                if resp.status != 200:
                    self.assertEqual(error_code(resp), CODE_BAD_QUERY)
                    continue
                self.assertEqual([p["id"] for p in decode_data(resp)], c["want_ids"])


if __name__ == "__main__":
    unittest.main()
