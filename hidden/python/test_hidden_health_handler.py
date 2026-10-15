import unittest

from request import Request
from server import Router
from testutil import decode_data, new_test_server
from health import health_routes


class HiddenHealthTest(unittest.TestCase):
    def test_health(self):
        s = new_test_server()
        router = Router()
        health_routes(s, router)
        resp = router.serve(Request(method="GET", path="/healthz"))
        self.assertEqual(resp.status, 200, resp.body)
        self.assertEqual(decode_data(resp), {"status": "ok", "users": 2, "products": 3, "orders": 2})


if __name__ == "__main__":
    unittest.main()
