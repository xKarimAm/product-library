import unittest

from calculator import evaluate


class CalculatorTest(unittest.TestCase):
    def test_precedence(self):
        self.assertEqual(evaluate("2 + 3 * 4"), 14)

    def test_parentheses(self):
        self.assertEqual(evaluate("2 * (3 + 4)"), 14)

    def test_unary_minus(self):
        self.assertEqual(evaluate("-3 + 5"), 2)

    def test_decimals(self):
        self.assertEqual(evaluate("0.5 * 4"), 2)

    def test_division_by_zero(self):
        with self.assertRaises(ZeroDivisionError):
            evaluate("1 / (2 - 2)")

    def test_rejects_garbage(self):
        for bad, at in (("2 +", 3), ("(1 + 2", 6), ("2 $ 3", 2), ("2 + * 3", 4)):
            with self.assertRaises(ValueError) as ctx:
                evaluate(bad)
            self.assertEqual(ctx.exception.at, at, bad)   # the caret lands on the culprit


if __name__ == "__main__":
    unittest.main()
