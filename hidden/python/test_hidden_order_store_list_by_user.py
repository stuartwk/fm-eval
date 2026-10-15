import unittest

from order_store import ORDER_PAID, Order, OrderStore


class HiddenOrderStoreListByUserTest(unittest.TestCase):
    def test_list_by_user(self):
        st = OrderStore()
        st.create(Order("", "usr_000001"))
        st.create(Order("", "usr_000002"))
        st.create(Order("", "usr_000001", status=ORDER_PAID))
        cases = [
            {"name": "two orders", "user": "usr_000001", "want": ["ord_000001", "ord_000003"]},
            {"name": "one order", "user": "usr_000002", "want": ["ord_000002"]},
            {"name": "none", "user": "usr_000099", "want": []},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                got = st.list_by_user(c["user"])
                self.assertIsInstance(got, list)
                self.assertEqual([o.id for o in got], c["want"])


if __name__ == "__main__":
    unittest.main()
