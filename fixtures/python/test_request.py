import unittest

from request import DEFAULT_LIMIT, BadQuery, PageParams, Request, paginate, parse_page


class ParsePageTest(unittest.TestCase):
    def test_parse_page(self):
        cases = [
            {"name": "defaults", "query": {}, "want": PageParams(DEFAULT_LIMIT, 0)},
            {"name": "both", "query": {"limit": "5", "offset": "10"}, "want": PageParams(5, 10)},
            {"name": "max limit", "query": {"limit": "100"}, "want": PageParams(100, 0)},
            {"name": "limit too big", "query": {"limit": "101"}, "want_err": True},
            {"name": "limit zero", "query": {"limit": "0"}, "want_err": True},
            {"name": "limit not a number", "query": {"limit": "ten"}, "want_err": True},
            {"name": "negative offset", "query": {"offset": "-1"}, "want_err": True},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                req = Request(method="GET", path="/x", query=c["query"])
                if c.get("want_err"):
                    with self.assertRaises(BadQuery):
                        parse_page(req)
                    continue
                self.assertEqual(parse_page(req), c["want"])


class PaginateTest(unittest.TestCase):
    def test_paginate(self):
        items = [1, 2, 3, 4, 5]
        cases = [
            {"name": "first page", "p": PageParams(2, 0), "want": [1, 2]},
            {"name": "last partial", "p": PageParams(2, 4), "want": [5]},
            {"name": "past end", "p": PageParams(2, 9), "want": []},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                got, info = paginate(items, c["p"])
                self.assertEqual(got, c["want"])
                self.assertEqual(info.total, 5)


if __name__ == "__main__":
    unittest.main()
