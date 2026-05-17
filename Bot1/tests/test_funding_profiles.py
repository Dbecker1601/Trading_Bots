import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "forex_strategies"))

from funding_profiles import (  # noqa: E402
    FundingTrade,
    compute_sqn,
    evaluate_funding_rules,
    evaluate_strategy_quality,
    get_profile,
)


class TestFundingProfiles(unittest.TestCase):
    def test_apex_50k_intraday_profile(self) -> None:
        profile = get_profile("APEX_50K_INTRADAY")

        self.assertEqual(profile.account_size, 50_000.0)
        self.assertEqual(profile.profit_target, 3_000.0)
        self.assertEqual(profile.max_loss, 2_000.0)
        self.assertEqual(profile.max_contracts, 6)
        self.assertEqual(profile.trailing_mode, "intraday_trailing")

    def test_apex_intraday_trailing_drawdown_moves_with_peak(self) -> None:
        profile = get_profile("APEX_50K_INTRADAY")

        report = evaluate_funding_rules(
            profile,
            trade_pnls=[1_800.0, -100.0],
            equity_curve=[50_000.0, 51_800.0, 49_799.0],
        )

        self.assertFalse(report.passed_rules)
        self.assertIn("max_loss", report.violations)

    def test_ftmo_two_step_daily_loss_and_min_days(self) -> None:
        profile = get_profile("FTMO_100K_2STEP")
        trades = [
            FundingTrade(dt.datetime(2026, 5, 1, 9), pnl=-3_000.0),
            FundingTrade(dt.datetime(2026, 5, 1, 10), pnl=-2_100.0),
        ]

        report = evaluate_funding_rules(
            profile,
            trade_pnls=[t.pnl for t in trades],
            equity_curve=[100_000.0, 97_000.0, 94_900.0],
            trades=trades,
        )

        self.assertFalse(report.passed_rules)
        self.assertIn("daily_loss_limit", report.violations)
        self.assertIn("min_trading_days", report.violations)

    def test_strategy_quality_gate(self) -> None:
        pnls = [100.0, -40.0] * 60
        equity = [50_000.0]
        for pnl in pnls:
            equity.append(equity[-1] + pnl)

        report = evaluate_strategy_quality(
            pnls,
            equity,
            min_trades=100,
            min_profit_factor=1.4,
            min_sqn=2.0,
            max_drawdown_buffer=2_000.0,
        )

        self.assertGreater(compute_sqn(pnls), 2.0)
        self.assertTrue(report.passed_quality_gate)


if __name__ == "__main__":
    unittest.main()
