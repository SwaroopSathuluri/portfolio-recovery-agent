import unittest

from app.goal import compute_goal_snapshot


class GoalTests(unittest.TestCase):
    def test_recovery_math(self):
        snapshot = compute_goal_snapshot(
            {
                "account_name": "Sample Brokerage",
                "current_value": 8000,
                "initial_capital": 10000,
                "recovery_target": 10000,
                "recovery_months": 3,
                "target_monthly_return_after_recovery_pct": 10,
            }
        )
        self.assertEqual(snapshot.gain_needed, 2000)
        self.assertAlmostEqual(snapshot.gain_needed_pct, 25.0)
        self.assertAlmostEqual(snapshot.required_monthly_return_pct, 7.72, places=2)
        self.assertEqual(snapshot.realism_label, "Aggressive")


if __name__ == "__main__":
    unittest.main()
