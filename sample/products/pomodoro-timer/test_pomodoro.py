import unittest

from pomodoro import mmss, schedule, total


class PomodoroTest(unittest.TestCase):
    def test_no_break_after_last_round(self):
        self.assertEqual(schedule(2), [("work", 25), ("break", 5), ("work", 25)])
        self.assertEqual(total(schedule(2)), 55)

    def test_long_break_after_fourth_round(self):
        self.assertEqual(schedule(5)[7], ("long break", 15))

    def test_mmss(self):
        self.assertEqual(mmss(25 * 60), "25:00")
        self.assertEqual(mmss(61), "01:01")


if __name__ == "__main__":
    unittest.main()
