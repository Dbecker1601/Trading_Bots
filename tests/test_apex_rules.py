import unittest

from trading_bots.apex_rules import (
    ApexAccountProfile,
    evaluate_apex_compliance,
    get_apex_profile,
)


class TestApexRules(unittest.TestCase):
    def test_get_apex_profile_intraday_50k(self) -> None:
        profile = get_apex_profile(account_type="intraday", account_size=50_000)
        self.assertEqual(profile.max_loss, 2000.0)
        self.assertEqual(profile.daily_loss_limit, None)
        self.assertEqual(profile.profit_target, 3000.0)

    def test_get_apex_profile_eod_100k(self) -> None:
        profile = get_apex_profile(account_type="eod", account_size=100_000)
        self.assertEqual(profile.max_loss, 3000.0)
        self.assertEqual(profile.daily_loss_limit, 1500.0)
        self.assertEqual(profile.profit_target, 6000.0)

    def test_evaluate_apex_compliance_flags_daily_loss_violation(self) -> None:
        profile = ApexAccountProfile(
            account_type="eod",
            account_size=50_000,
            profit_target=3000.0,
            max_loss=2000.0,
            daily_loss_limit=1000.0,
            consistency_limit=0.5,
        )

        report = evaluate_apex_compliance(
            profile=profile,
            trade_pnls=[300.0, -1200.0, 600.0],
            equity_curve=[50_000.0, 50_300.0, 49_100.0, 49_700.0],
        )

        self.assertFalse(report.passed)
        self.assertIn("daily_loss_limit", report.violations)

    def test_evaluate_apex_compliance_flags_consistency_violation(self) -> None:
        profile = ApexAccountProfile(
            account_type="intraday",
            account_size=50_000,
            profit_target=3000.0,
            max_loss=2000.0,
            daily_loss_limit=None,
            consistency_limit=0.5,
        )

        report = evaluate_apex_compliance(
            profile=profile,
            trade_pnls=[2000.0, 300.0, 200.0],
            equity_curve=[50_000.0, 52_000.0, 52_300.0, 52_500.0],
        )

        self.assertFalse(report.passed)
        self.assertIn("consistency_rule", report.violations)


if __name__ == "__main__":
    unittest.main()
