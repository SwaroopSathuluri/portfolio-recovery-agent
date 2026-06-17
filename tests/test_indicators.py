import unittest

from app.indicators import pct_change, sma


class IndicatorTests(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(sma([1, 2, 3, 4, 5], 3), 4)

    def test_pct_change(self):
        self.assertEqual(pct_change(125, 100), 25)
        self.assertEqual(pct_change(125, 0), 0)


if __name__ == "__main__":
    unittest.main()
