import unittest

from product_store import Product, ProductStore


class HiddenProductStoreAdjustStockTest(unittest.TestCase):
    def test_adjust_stock(self):
        cases = [
            {"name": "add", "id": "prd_000001", "delta": 5, "want_ok": True, "want_stock": 15},
            {"name": "remove", "id": "prd_000001", "delta": -4, "want_ok": True, "want_stock": 6},
            {"name": "to zero", "id": "prd_000001", "delta": -10, "want_ok": True, "want_stock": 0},
            {"name": "below zero", "id": "prd_000001", "delta": -11, "want_ok": False, "want_stock": 10},
            {"name": "missing", "id": "prd_000099", "delta": 1, "want_ok": False},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                st = ProductStore()
                st.create(Product("", "Keyboard", 4999, 10))
                got = st.adjust_stock(c["id"], c["delta"])
                self.assertEqual(got is not None, c["want_ok"])
                if got is not None:
                    self.assertEqual(got.stock, c["want_stock"])
                if c["id"] == "prd_000001":
                    self.assertEqual(st.get(c["id"]).stock, c["want_stock"])


if __name__ == "__main__":
    unittest.main()
