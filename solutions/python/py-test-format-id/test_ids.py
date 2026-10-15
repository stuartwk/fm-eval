import unittest

from ids import format_id


class FormatIDTest(unittest.TestCase):
    def test_format_id(self):
        cases = [
            {"name": "one", "prefix": "usr", "n": 1, "want": "usr_000001"},
            {"name": "zero", "prefix": "ord", "n": 0, "want": "ord_000000"},
            {"name": "six digits", "prefix": "prd", "n": 123456, "want": "prd_123456"},
            {"name": "seven digits", "prefix": "rev", "n": 1234567, "want": "rev_1234567"},
        ]
        for c in cases:
            with self.subTest(c["name"]):
                self.assertEqual(format_id(c["prefix"], c["n"]), c["want"])


if __name__ == "__main__":
    unittest.main()
