import unittest

from review_store import Review, ReviewStore


class ReviewStoreTest(unittest.TestCase):
    def test_create_and_get(self):
        st = ReviewStore()
        cases = [
            {"name": "first", "review": Review("", "prd_000001", "usr_000001", 5), "want_id": "rev_000001"},
            {"name": "second", "review": Review("", "prd_000002", "usr_000001", 3), "want_id": "rev_000002"},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                got = st.create(c["review"])
                self.assertEqual(got.id, c["want_id"])
                self.assertEqual(st.get(c["want_id"]), got)

    def test_get_missing(self):
        self.assertIsNone(ReviewStore().get("rev_000001"))

    def test_list_by_product(self):
        st = ReviewStore()
        for product in ["prd_000001", "prd_000002", "prd_000001", "prd_000001"]:
            st.create(Review("", product, "usr_000001", 4))
        cases = [
            {"name": "filters and sorts", "product": "prd_000001", "want": ["rev_000001", "rev_000003", "rev_000004"]},
            {"name": "single", "product": "prd_000002", "want": ["rev_000002"]},
            {"name": "none", "product": "prd_000009", "want": []},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                self.assertEqual([r.id for r in st.list_by_product(c["product"])], c["want"])


if __name__ == "__main__":
    unittest.main()
