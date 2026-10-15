import unittest

from respond import CODE_BAD_JSON, CODE_CONFLICT, CODE_NOT_FOUND, CODE_VALIDATION_FAILED
from testutil import decode_data, decode_list, do_request, error_code, new_test_server


class GetUserTest(unittest.TestCase):
    def test_get_user(self):
        cases = [
            {"name": "found", "id": "usr_000001", "want_code": 200},
            {"name": "missing", "id": "usr_000099", "want_code": 404, "want_err": CODE_NOT_FOUND},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "GET", "/users/" + c["id"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_err" in c:
                    self.assertEqual(error_code(resp), c["want_err"])
                    continue
                user = decode_data(resp)
                self.assertEqual(user["id"], c["id"])
                self.assertEqual(user["name"], "Ada Lovelace")


class ListUsersTest(unittest.TestCase):
    def test_list_users(self):
        cases = [
            {"name": "default", "query": "", "want_ids": ["usr_000001", "usr_000002"]},
            {"name": "limit", "query": "?limit=1", "want_ids": ["usr_000001"]},
            {"name": "offset", "query": "?offset=1", "want_ids": ["usr_000002"]},
            {"name": "past end", "query": "?offset=5", "want_ids": []},
            {"name": "bad limit", "query": "?limit=0", "want_code": 400},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "GET", "/users" + c["query"])
                self.assertEqual(resp.status, c.get("want_code", 200), resp.body)
                if resp.status != 200:
                    continue
                users, page = decode_list(resp)
                self.assertEqual([u["id"] for u in users], c["want_ids"])
                self.assertEqual(page["total"], 2)


class CreateUserTest(unittest.TestCase):
    def test_create_user(self):
        cases = [
            {"name": "ok", "body": '{"email":"linus@example.com","name":"Linus"}', "want_code": 201},
            {"name": "bad json", "body": '{"email":', "want_code": 400, "want_err": CODE_BAD_JSON},
            {"name": "unknown field", "body": '{"email":"a@b.c","name":"A","age":3}', "want_code": 400, "want_err": CODE_BAD_JSON},
            {"name": "missing email", "body": '{"name":"Linus"}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "email without at", "body": '{"email":"linus","name":"Linus"}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "duplicate email", "body": '{"email":"ADA@example.com","name":"Ada"}', "want_code": 409, "want_err": CODE_CONFLICT},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "POST", "/users", c["body"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_err" in c:
                    self.assertEqual(error_code(resp), c["want_err"])
                    continue
                self.assertEqual(decode_data(resp)["id"], "usr_000003")


class DeleteUserTest(unittest.TestCase):
    def test_delete_user(self):
        s = new_test_server()
        self.assertEqual(do_request(s, "DELETE", "/users/usr_000002").status, 204)
        self.assertEqual(do_request(s, "GET", "/users/usr_000002").status, 404)
        self.assertEqual(do_request(s, "DELETE", "/users/usr_000002").status, 404)


if __name__ == "__main__":
    unittest.main()
