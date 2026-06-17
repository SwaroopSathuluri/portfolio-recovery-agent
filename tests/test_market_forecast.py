import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_forecast import remove_unfinished_current_day, strategy_playbook


class MarketForecastTests(unittest.TestCase):
    def test_strategy_playbook_contains_defined_risk_options(self):
        names = [item["name"] for item in strategy_playbook()]
        self.assertIn("Defined-risk call spread", names)
        self.assertIn("50 SMA failure exit", names)

    def test_remove_unfinished_current_day_during_session(self):
        eastern = ZoneInfo("America/New_York")
        history = [{"date": "2026-06-15"}, {"date": "2026-06-16"}]
        filtered = remove_unfinished_current_day(history, now=datetime(2026, 6, 16, 10, 0, tzinfo=eastern))
        self.assertEqual(filtered, [{"date": "2026-06-15"}])

    def test_keep_current_day_after_settlement(self):
        eastern = ZoneInfo("America/New_York")
        history = [{"date": "2026-06-15"}, {"date": "2026-06-16"}]
        filtered = remove_unfinished_current_day(history, now=datetime(2026, 6, 16, 16, 30, tzinfo=eastern))
        self.assertEqual(filtered, history)


if __name__ == "__main__":
    unittest.main()
