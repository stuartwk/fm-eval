import unittest

from respond import CODE_BAD_JSON, CODE_NOT_FOUND, CODE_VALIDATION_FAILED
from testutil import decode_data, do_request, error_code, new_test_server


class GetProductTest(unittest.TestCase):
    def test_get_product(self):
        cases = [
            {"name": "found", "id": "prd_000003", "want_code": 200},
            {"name": "missing", "id": "prd_000099", "want_code": 404, "want_err": CODE_NOT_FOUND},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "GET", "/products/" + c["id"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_err" in c:
                    self.assertEqual(error_code(resp), c["want_err"])
                    continue
                product = decode_data(resp)
                self.assertEqual((product["name"], product["price_cents"]), ("Monitor", 18999))


class ListProductsTest(unittest.TestCase):
    def test_list_products(self):
        s = new_test_server()
        resp = do_request(s, "GET", "/products")
        self.assertEqual(resp.status, 200, resp.body)
        products = decode_data(resp)
        self.assertEqual([p["id"] for p in products], ["prd_000001", "prd_000002", "prd_000003"])


class CreateProductTest(unittest.TestCase):
    def test_create_product(self):
        cases = [
            {"name": "ok", "body": '{"name":"Cable","price_cents":599,"stock":40}', "want_code": 201},
            {"name": "bad json", "body": "[]", "want_code": 400, "want_err": CODE_BAD_JSON},
            {"name": "missing name", "body": '{"price_cents":599}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "zero price", "body": '{"name":"Cable","price_cents":0}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "negative stock", "body": '{"name":"Cable","price_cents":599,"stock":-1}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = do_request(s, "POST", "/products", c["body"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_err" in c:
                    self.assertEqual(error_code(resp), c["want_err"])
                    continue
                self.assertEqual(decode_data(resp)["id"], "prd_000004")


if __name__ == "__main__":
    unittest.main()
