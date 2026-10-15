import json
import unittest

from respond import CODE_NOT_FOUND
from testutil import decode_data, do_request, new_test_server


class HiddenGetOrderTest(unittest.TestCase):
    def test_get_order(self):
        cases = [
            {"name": "found pending", "id": "ord_000001", "want_code": 200},
            {"name": "found paid", "id": "ord_000002", "want_code": 200},
            {"name": "missing", "id": "ord_000099", "want_code": 404, "want_msg": "order ord_000099 not found"},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "GET", "/orders/" + c["id"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_msg" in c:
                    err = json.loads(resp.body)["error"]
                    self.assertEqual((err["code"], err["message"]), (CODE_NOT_FOUND, c["want_msg"]))
                    continue
                got, want = decode_data(resp), s.orders.get(c["id"])
                self.assertEqual((got["id"], got["user_id"], got["total_cents"], got["status"], len(got["items"])),
                                 (want.id, want.user_id, want.total_cents, want.status, len(want.items)))


if __name__ == "__main__":
    unittest.main()
