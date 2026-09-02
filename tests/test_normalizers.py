"""Tests for the pure normalizer module (no DuckDB, no filesystem)."""
import unittest
from datetime import date, datetime

from scripts.normalizers import parse_temporal


class ParseTemporalTests(unittest.TestCase):
    def assert_temporal(self, raw, expected, has_time):
        result = parse_temporal(raw)
        self.assertIsNotNone(result, f"should parse {raw!r}")
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1], has_time)

    def test_iso_date(self):
        self.assert_temporal("2026-09-02", date(2026, 9, 2), False)

    def test_iso_with_time_and_microseconds(self):
        self.assert_temporal(
            "2026-09-02T14:30:15.250",
            datetime(2026, 9, 2, 14, 30, 15, 250000),
            True,
        )

    def test_brazilian_separators(self):
        self.assert_temporal("02/09/2026", date(2026, 9, 2), False)
        self.assert_temporal("02-09-2026", date(2026, 9, 2), False)
        self.assert_temporal("02.09.2026", date(2026, 9, 2), False)

    def test_two_digit_year_becomes_2000s(self):
        self.assert_temporal("02-09-26", date(2026, 9, 2), False)

    def test_ambiguous_prefers_brazilian_day_first(self):
        self.assert_temporal("01/02/2026", date(2026, 2, 1), False)
        self.assert_temporal("15/03/2026", date(2026, 3, 15), False)

    def test_year_first_with_slashes(self):
        self.assert_temporal("2026/09/02", date(2026, 9, 2), False)

    def test_written_out_ptbr(self):
        self.assert_temporal("2 de setembro de 2026", date(2026, 9, 2), False)
        self.assert_temporal("2 DE SETEMBRO DE 2026", date(2026, 9, 2), False)
        self.assertIsNone(parse_temporal("2 de setembro"))  # no year -> unrecoverable

    def test_abbreviated_month_with_separators(self):
        self.assert_temporal("02/set/2026", date(2026, 9, 2), False)
        self.assert_temporal("02/set.2026", date(2026, 9, 2), False)
        self.assert_temporal("02.out.26", date(2026, 10, 2), False)

    def test_time_after_brazilian_date(self):
        self.assert_temporal("02/09/2026 14:30", datetime(2026, 9, 2, 14, 30), True)
        self.assert_temporal(
            "02/09/2026 14:30:15.250",
            datetime(2026, 9, 2, 14, 30, 15, 250000),
            True,
        )

    def test_timezone_offsets_are_converted_to_utc_naive(self):
        self.assert_temporal("2026-09-02T14:30:00-04:00", datetime(2026, 9, 2, 18, 30), True)
        self.assert_temporal("2026-09-02T14:30:00Z", datetime(2026, 9, 2, 14, 30), True)

    def test_python_objects_pass_through(self):
        self.assert_temporal(date(2026, 9, 2), date(2026, 9, 2), False)
        self.assert_temporal(
            datetime(2026, 9, 2, 14, 30), datetime(2026, 9, 2, 14, 30), True
        )

    def test_invalid_values_return_none(self):
        for raw in ("31/02/2025", "s/ data", "", "—", "sem data", "n/a", None, 123):
            self.assertIsNone(parse_temporal(raw), f"should not parse {raw!r}")


if __name__ == "__main__":
    unittest.main()
