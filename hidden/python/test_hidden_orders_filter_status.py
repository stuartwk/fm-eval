import unittest

from respond import CODE_BAD_QUERY
from testutil import decode_list, do_request, error_code, new_test_server


class HiddenListOrdersByStatusTest(unittest.TestCase):
    def test_filter(self):
        cases = [
            {"name": "all", "query": "", "want_ids": ["ord_000001", "ord_000002"], "want_total": 2},
            {"name": "paid", "query": "?status=paid", "want_ids": ["ord_000002"], "want_total": 1},
            {"name": "pending", "query": "?status=pending", "want_ids": ["ord_000001"], "want_total": 1},
            {"name": "cancelled none", "query": "?status=cancelled", "want_ids": [], "want_total": 0},
            {"name": "with paging", "query": "?status=paid&limit=1&offset=1", "want_ids": [], "want_total": 1},
            {"name": "bad status", "query": "?status=shipped", "want_code": 400},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "GET", "/orders" + c["query"])
                self.assertEqual(resp.status, c.get("want_code", 200), resp.body)
                if resp.status != 200:
                    self.assertEqual(error_code(resp), CODE_BAD_QUERY)
                    continue
                orders, page = decode_list(resp)
                self.assertEqual(page["total"], c["want_total"])
                self.assertEqual([o["id"] for o in orders], c["want_ids"])


if __name__ == "__main__":
    unittest.main()
