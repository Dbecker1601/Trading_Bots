import unittest

from trading_bots.execution import build_entry_plan


class TestExecution(unittest.TestCase):
    def test_build_entry_plan_prefers_limit_when_spread_is_tight(self) -> None:
        plan = build_entry_plan(action="long", spread_bps=1.2, max_spread_for_limit_bps=2.0)
        self.assertEqual(plan.order_type, "limit")

    def test_build_entry_plan_uses_market_when_spread_is_wide(self) -> None:
        plan = build_entry_plan(action="short", spread_bps=4.0, max_spread_for_limit_bps=2.0)
        self.assertEqual(plan.order_type, "market")


if __name__ == "__main__":
    unittest.main()
