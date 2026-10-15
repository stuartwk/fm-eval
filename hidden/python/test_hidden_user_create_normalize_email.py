import unittest

from testutil import decode_data, do_request, new_test_server


class HiddenCreateUserNormalizesEmailTest(unittest.TestCase):
    def test_normalize(self):
        cases = [
            {"name": "lowercased and trimmed", "body": '{"email":"  Linus@Example.COM ","name":"Linus"}', "want_code": 201, "want_email": "linus@example.com"},
            {"name": "duplicate after trim", "body": '{"email":" ADA@example.com ","name":"Ada"}', "want_code": 409},
            {"name": "blank after trim", "body": '{"email":"   ","name":"Linus"}', "want_code": 422},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "POST", "/users", c["body"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_email" in c:
                    got = decode_data(resp)
                    self.assertEqual(got["email"], c["want_email"])
                    self.assertEqual(s.users.get(got["id"]).email, c["want_email"])


if __name__ == "__main__":
    unittest.main()
