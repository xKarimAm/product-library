import unittest
from datetime import date

from habits import streak

TODAY = date(2026, 10, 17)


class StreakTest(unittest.TestCase):
    def test_counts_back_from_today(self):
        self.assertEqual(streak(["2026-10-15", "2026-10-16", "2026-10-17"], TODAY), 3)

    def test_unchecked_today_keeps_yesterdays_streak(self):
        self.assertEqual(streak(["2026-10-15", "2026-10-16"], TODAY), 2)

    def test_gap_breaks_the_streak(self):
        self.assertEqual(streak(["2026-10-13", "2026-10-17"], TODAY), 1)


if __name__ == "__main__":
    unittest.main()
