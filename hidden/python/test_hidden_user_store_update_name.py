import unittest

from user_store import User, UserStore


class HiddenUserStoreUpdateNameTest(unittest.TestCase):
    def test_update_name(self):
        st = UserStore()
        st.create(User("", "ada@example.com", "Ada"))
        got = st.update_name("usr_000001", "Ada Lovelace")
        self.assertEqual((got.id, got.email, got.name), ("usr_000001", "ada@example.com", "Ada Lovelace"))
        self.assertEqual(st.get("usr_000001").name, "Ada Lovelace")
        self.assertIsNone(st.update_name("usr_000099", "Nobody"))


if __name__ == "__main__":
    unittest.main()
