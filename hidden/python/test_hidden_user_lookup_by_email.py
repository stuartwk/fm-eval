import json
import unittest

from respond import CODE_BAD_QUERY, CODE_NOT_FOUND
from testutil import decode_data, do_request, new_test_server


class HiddenLookupUserByEmailTest(unittest.TestCase):
    def test_lookup(self):
        cases = [
            {"name": "found", "query": "?email=grace@example.com", "want_code": 200, "want_id": "usr_000002"},
            {"name": "case insensitive", "query": "?email=ADA@example.com", "want_code": 200, "want_id": "usr_000001"},
            {"name": "missing param", "query": "", "want_code": 400, "want_err": CODE_BAD_QUERY},
            {"name": "not found", "query": "?email=nobody@example.com", "want_code": 404, "want_err": CODE_NOT_FOUND,
             "want_msg": "user nobody@example.com not found"},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "GET", "/users/lookup" + c["query"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_err" in c:
                    err = json.loads(resp.body)["error"]
                    self.assertEqual(err["code"], c["want_err"])
                    if "want_msg" in c:
                        self.assertEqual(err["message"], c["want_msg"])
                    continue
                self.assertEqual(decode_data(resp)["id"], c["want_id"])


if __name__ == "__main__":
    unittest.main()
