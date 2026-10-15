import unittest

from respond import CODE_BAD_QUERY
from testutil import decode_list, do_request, error_code, new_test_server


class HiddenListProductsPaginatedTest(unittest.TestCase):
    def test_paginated(self):
        cases = [
            {"name": "default", "query": "", "want_ids": ["prd_000001", "prd_000002", "prd_000003"], "want_page": {"limit": 20, "offset": 0, "total": 3}},
            {"name": "limit", "query": "?limit=2", "want_ids": ["prd_000001", "prd_000002"], "want_page": {"limit": 2, "offset": 0, "total": 3}},
            {"name": "offset", "query": "?limit=2&offset=2", "want_ids": ["prd_000003"], "want_page": {"limit": 2, "offset": 2, "total": 3}},
            {"name": "past end", "query": "?offset=10", "want_ids": [], "want_page": {"limit": 20, "offset": 10, "total": 3}},
            {"name": "bad limit", "query": "?limit=500", "want_code": 400},
            {"name": "bad offset", "query": "?offset=-2", "want_code": 400},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "GET", "/products" + c["query"])
                self.assertEqual(resp.status, c.get("want_code", 200), resp.body)
                if resp.status != 200:
                    self.assertEqual(error_code(resp), CODE_BAD_QUERY)
                    continue
                products, page = decode_list(resp)
                self.assertEqual(page, c["want_page"])
                self.assertEqual([p["id"] for p in products], c["want_ids"])


if __name__ == "__main__":
    unittest.main()
