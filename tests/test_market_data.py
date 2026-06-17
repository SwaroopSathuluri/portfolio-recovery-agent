import unittest

from app.market_data import daily_bar_date


class MarketDataTests(unittest.TestCase):
    def test_daily_bar_date_uses_utc(self):
        self.assertEqual(daily_bar_date(1781481600000), "2026-06-15")


if __name__ == "__main__":
    unittest.main()
