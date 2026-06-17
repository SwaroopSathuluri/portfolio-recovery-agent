import unittest

from app.market_monitor import evaluate_monitor_rules


class MarketMonitorTests(unittest.TestCase):
    def test_no_snapshots_no_alerts(self):
        self.assertEqual(evaluate_monitor_rules({}, {}, {"rules": {}}), [])


if __name__ == "__main__":
    unittest.main()
