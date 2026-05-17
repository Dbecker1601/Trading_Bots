import datetime as dt
import unittest

from trading_bots.apex_rules import (
    ApexAccountProfile,
    evaluate_apex_compliance,
    get_apex_profile,
)
from trading_bots.backtest import Trade


class TestApexRules(unittest.TestCase):
    def test_get_apex_profile_intraday_50k(self) -> None:
        profile = get_apex_profile(account_type="intraday", account_size=50_000)
        self.assertEqual(profile.max_loss, 2000.0)
        self.assertEqual(profile.daily_loss_limit, None)
        self.assertEqual(profile.profit_target, 3000.0)
        self.assertEqual(profile.max_contracts, 6)

    def test_get_apex_profile_eod_100k(self) -> None:
        profile = get_apex_profile(account_type="eod", account_size=100_000)
        self.assertEqual(profile.max_loss, 3000.0)
        self.assertEqual(profile.daily_loss_limit, 1500.0)
        self.assertEqual(profile.profit_target, 6000.0)

    def test_evaluate_apex_compliance_flags_daily_loss_violation_by_day(self) -> None:
        profile = ApexAccountProfile(
            account_type="eod",
            account_size=50_000,
            profit_target=3000.0,
            max_loss=2000.0,
            daily_loss_limit=1000.0,
            consistency_limit=0.5,
            max_contracts=10,
        )

        trades = [
            Trade(timestamp=dt.datetime(2026, 4, 1, 9, 30), side="long", contracts=1, entry=1.0, exit=1.0),
            Trade(timestamp=dt.datetime(2026, 4, 1, 10, 0), side="long", contracts=1, entry=1.0, exit=1.0),
            Trade(timestamp=dt.datetime(2026, 4, 2, 9, 30), side="long", contracts=1, entry=1.0, exit=1.0),
        ]

        report = evaluate_apex_compliance(
            profile=profile,
            trade_pnls=[-600.0, -500.0, 300.0],
            equity_curve=[50_000.0, 49_400.0, 48_900.0, 49_200.0],
            trades=trades,
        )

        self.assertFalse(report.passed)
        self.assertIn("daily_loss_limit", report.violations)

    def test_evaluate_apex_compliance_flags_consistency_violation(self) -> None:
        profile = ApexAccountProfile(
            account_type="eod",
            account_size=50_000,
            profit_target=3000.0,
            max_loss=2000.0,
            daily_loss_limit=1000.0,
            consistency_limit=0.5,
            max_contracts=10,
        )

        report = evaluate_apex_compliance(
            profile=profile,
            trade_pnls=[2000.0, 300.0, 200.0],
            equity_curve=[50_000.0, 52_000.0, 52_300.0, 52_500.0],
            trades=[
                Trade(timestamp=dt.datetime(2026, 4, 1, 9, 30), side="long", contracts=1, entry=1.0, exit=1.0),
                Trade(timestamp=dt.datetime(2026, 4, 2, 9, 30), side="long", contracts=1, entry=1.0, exit=1.0),
                Trade(timestamp=dt.datetime(2026, 4, 3, 9, 30), side="long", contracts=1, entry=1.0, exit=1.0),
            ],
        )

        self.assertFalse(report.passed)
        self.assertIn("consistency_rule", report.violations)

    def test_intraday_evaluation_does_not_apply_consistency_rule(self) -> None:
        profile = get_apex_profile(account_type="intraday", account_size=50_000)

        report = evaluate_apex_compliance(
            profile=profile,
            trade_pnls=[2000.0, 300.0, 200.0],
            equity_curve=[50_000.0, 52_000.0, 52_300.0, 52_500.0],
            trades=[
                Trade(timestamp=dt.datetime(2026, 4, 1, 9, 30), side="long", contracts=1, entry=1.0, exit=1.0),
                Trade(timestamp=dt.datetime(2026, 4, 2, 9, 30), side="long", contracts=1, entry=1.0, exit=1.0),
                Trade(timestamp=dt.datetime(2026, 4, 3, 9, 30), side="long", contracts=1, entry=1.0, exit=1.0),
            ],
        )

        self.assertNotIn("consistency_rule", report.violations)

    def test_intraday_trailing_threshold_moves_up_with_equity_peak(self) -> None:
        profile = get_apex_profile(account_type="intraday", account_size=50_000)

        report = evaluate_apex_compliance(
            profile=profile,
            trade_pnls=[1800.0, -100.0],
            equity_curve=[50_000.0, 51_800.0, 49_799.0],
        )

        self.assertFalse(report.passed)
        self.assertIn("max_loss", report.violations)

    def test_evaluate_apex_compliance_flags_contract_limit_violation(self) -> None:
        profile = ApexAccountProfile(
            account_type="intraday",
            account_size=50_000,
            profit_target=3000.0,
            max_loss=2000.0,
            daily_loss_limit=None,
            consistency_limit=0.5,
            max_contracts=10,
        )

        trades = [
            Trade(timestamp=dt.datetime(2026, 4, 1, 9, 30), side="long", contracts=12, entry=1.0, exit=1.0),
        ]

        report = evaluate_apex_compliance(
            profile=profile,
            trade_pnls=[100.0],
            equity_curve=[50_000.0, 50_100.0],
            trades=trades,
        )

        self.assertFalse(report.passed)
        self.assertIn("max_contracts", report.violations)


if __name__ == "__main__":
    unittest.main()
