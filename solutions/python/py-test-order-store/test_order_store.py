import unittest

from order_store import ORDER_PAID, ORDER_PENDING, Order, OrderStore


class OrderStoreTest(unittest.TestCase):
    def test_create_and_get(self):
        st = OrderStore()
        cases = [
            {"name": "first", "order": Order("", "usr_000001", status=ORDER_PENDING), "want_id": "ord_000001"},
            {"name": "second", "order": Order("", "usr_000002", status=ORDER_PAID), "want_id": "ord_000002"},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                got = st.create(c["order"])
                self.assertEqual(got.id, c["want_id"])
                stored = st.get(c["want_id"])
                self.assertEqual((stored.user_id, stored.status), (c["order"].user_id, c["order"].status))

    def test_set_status(self):
        st = OrderStore()
        st.create(Order("", "usr_000001", status=ORDER_PENDING))
        got = st.set_status("ord_000001", ORDER_PAID)
        self.assertEqual(got.status, ORDER_PAID)
        self.assertEqual(st.get("ord_000001").status, ORDER_PAID)
        self.assertIsNone(st.set_status("ord_000099", ORDER_PAID))

    def test_list_sorted(self):
        st = OrderStore()
        for _ in range(3):
            st.create(Order("", "usr_000001"))
        self.assertEqual([o.id for o in st.list()], ["ord_000001", "ord_000002", "ord_000003"])


if __name__ == "__main__":
    unittest.main()
