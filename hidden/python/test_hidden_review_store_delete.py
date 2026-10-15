import unittest

from review_store import Review, ReviewStore


class HiddenReviewStoreDeleteTest(unittest.TestCase):
    def test_delete(self):
        st = ReviewStore()
        st.create(Review("", "prd_000001", "usr_000001", 5))
        st.create(Review("", "prd_000001", "usr_000002", 3))
        self.assertTrue(st.delete("rev_000001"))
        self.assertIsNone(st.get("rev_000001"))
        self.assertEqual([r.id for r in st.list_by_product("prd_000001")], ["rev_000002"])
        self.assertFalse(st.delete("rev_000001"))
        self.assertFalse(st.delete("rev_000099"))


if __name__ == "__main__":
    unittest.main()
