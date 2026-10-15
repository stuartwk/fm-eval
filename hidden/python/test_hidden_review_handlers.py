import json
import unittest

from request import Request
from respond import CODE_BAD_JSON, CODE_BAD_QUERY, CODE_NOT_FOUND, CODE_VALIDATION_FAILED
from review_store import Review
from server import Router
from testutil import decode_data, decode_list, error_code, new_test_server
from review_handlers import review_routes


def hidden_review_request(s, method, path, body="", query=None):
    """Routes through a router with only the review routes."""
    router = Router()
    review_routes(s, router)
    return router.serve(Request(method=method, path=path, query=query or {}, body=body))


class HiddenCreateReviewTest(unittest.TestCase):
    def test_create_review(self):
        cases = [
            {"name": "ok", "product": "prd_000001", "body": '{"user_id":"usr_000002","rating":4,"body":"Clicky."}', "want_code": 201},
            {"name": "ok without body", "product": "prd_000001", "body": '{"user_id":"usr_000002","rating":1}', "want_code": 201},
            {"name": "missing product", "product": "prd_000099", "body": '{"user_id":"usr_000002","rating":4}', "want_code": 404,
             "want_err": CODE_NOT_FOUND, "want_msg": "product prd_000099 not found"},
            {"name": "bad json", "product": "prd_000001", "body": '{"rating":', "want_code": 400, "want_err": CODE_BAD_JSON},
            {"name": "unknown field", "product": "prd_000001", "body": '{"user_id":"usr_000002","rating":4,"stars":4}', "want_code": 400, "want_err": CODE_BAD_JSON},
            {"name": "missing user", "product": "prd_000001", "body": '{"rating":4}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "rating zero", "product": "prd_000001", "body": '{"user_id":"usr_000002","rating":0}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "rating six", "product": "prd_000001", "body": '{"user_id":"usr_000002","rating":6}', "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "body too long", "product": "prd_000001", "body": json.dumps({"user_id": "usr_000002", "rating": 3, "body": "x" * 501}),
             "want_code": 422, "want_err": CODE_VALIDATION_FAILED},
            {"name": "unknown user", "product": "prd_000001", "body": '{"user_id":"usr_000099","rating":4}', "want_code": 422,
             "want_err": CODE_VALIDATION_FAILED, "want_msg": "user_id: unknown user"},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                s = new_test_server()
                resp = hidden_review_request(s, "POST", f"/products/{c['product']}/reviews", c["body"])
                self.assertEqual(resp.status, c["want_code"], resp.body)
                if "want_err" in c:
                    err = json.loads(resp.body)["error"]
                    self.assertEqual(err["code"], c["want_err"])
                    if "want_msg" in c:
                        self.assertEqual(err["message"], c["want_msg"])
                    continue
                got = decode_data(resp)
                self.assertEqual((got["id"], got["product_id"], got["user_id"]), ("rev_000001", c["product"], "usr_000002"))
                self.assertIsNotNone(s.reviews.get("rev_000001"))


class HiddenListProductReviewsTest(unittest.TestCase):
    def test_list_reviews(self):
        s = new_test_server()
        s.reviews.create(Review("", "prd_000001", "usr_000001", 5))
        s.reviews.create(Review("", "prd_000003", "usr_000001", 2))
        s.reviews.create(Review("", "prd_000001", "usr_000002", 4))
        cases = [
            {"name": "filters by product", "path": "/products/prd_000001/reviews", "want_ids": ["rev_000001", "rev_000003"],
             "want_page": {"limit": 20, "offset": 0, "total": 2}},
            {"name": "paginates", "path": "/products/prd_000001/reviews", "query": {"limit": "1", "offset": "1"}, "want_ids": ["rev_000003"],
             "want_page": {"limit": 1, "offset": 1, "total": 2}},
            {"name": "no reviews", "path": "/products/prd_000002/reviews", "want_ids": [], "want_page": {"limit": 20, "offset": 0, "total": 0}},
            {"name": "missing product", "path": "/products/prd_000099/reviews", "want_code": 404, "want_err": CODE_NOT_FOUND},
            {"name": "bad query", "path": "/products/prd_000001/reviews", "query": {"limit": "x"}, "want_code": 400, "want_err": CODE_BAD_QUERY},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                resp = hidden_review_request(s, "GET", c["path"], query=c.get("query"))
                self.assertEqual(resp.status, c.get("want_code", 200), resp.body)
                if "want_err" in c:
                    self.assertEqual(error_code(resp), c["want_err"])
                    continue
                reviews, page = decode_list(resp)
                self.assertEqual(page, c["want_page"])
                self.assertEqual([r["id"] for r in reviews], c["want_ids"])


if __name__ == "__main__":
    unittest.main()
