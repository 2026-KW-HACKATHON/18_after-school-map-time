from django.test import SimpleTestCase

from .validation import MAX_PK, parse_pk


INVALID_IDS = ("", "abc", "-1", "²", "１２３", "١", " 1", "1 ", "1 2", "0", str(MAX_PK + 1), "9" * 10000)


class PrimaryKeyParsingTests(SimpleTestCase):
    def test_ascii_decimal_ids(self):
        for raw, expected in (("1", 1), ("123", 123), ("00123", 123), (str(MAX_PK), MAX_PK)):
            with self.subTest(raw=raw):
                self.assertEqual(parse_pk(raw), expected)

    def test_invalid_ids(self):
        for raw in INVALID_IDS:
            with self.subTest(raw=raw[:25]):
                self.assertIsNone(parse_pk(raw))

    def test_non_string_values(self):
        for raw in (None, 1, True, [], {}):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_pk(raw))
