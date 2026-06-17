import unittest

from app.options_walls import analyze_option_walls


def option_row(contract_type, strike, open_interest, spot=100.0):
    return {
        "details": {
            "contract_type": contract_type,
            "expiration_date": "2026-06-17",
            "strike_price": strike,
        },
        "open_interest": open_interest,
        "underlying_asset": {"price": spot, "last_updated": 1781694750988707896},
    }


class OptionsWallTests(unittest.TestCase):
    def test_uses_relevant_put_wall_instead_of_far_away_open_interest(self):
        chain = [
            option_row("put", 70, 50000),
            option_row("put", 98, 900),
            option_row("call", 104, 1200),
            option_row("call", 112, 7000),
        ]

        result = analyze_option_walls("TEST", chain, "2026-06-17", relevance_pct=5.0)

        self.assertTrue(result["available"])
        self.assertEqual(result["put_wall"]["strike"], 98)
        self.assertEqual(result["call_wall"]["strike"], 104)
        self.assertNotEqual(result["put_wall"]["strike"], 70)


if __name__ == "__main__":
    unittest.main()
