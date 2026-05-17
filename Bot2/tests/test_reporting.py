import unittest

from trading_bots.reporting import compute_kpis


class TestReporting(unittest.TestCase):
    def test_compute_kpis(self) -> None:
        kpis = compute_kpis(trade_pnls=[100.0, -50.0, 120.0, -20.0], equity_curve=[50_000.0, 50_100.0, 50_050.0, 50_170.0, 50_150.0])
        self.assertGreater(kpis.win_rate, 0.0)
        self.assertGreater(kpis.profit_factor, 1.0)
        self.assertLessEqual(kpis.max_drawdown, 0.0)


if __name__ == "__main__":
    unittest.main()
