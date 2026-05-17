import datetime as dt
import unittest

from trading_bots.backtest import (
    BacktestConfig,
    Trade,
    apply_costs,
    run_backtest,
    walk_forward_windows,
)


class TestBacktest(unittest.TestCase):
    def test_apply_costs_reduces_pnl(self) -> None:
        net = apply_costs(gross_pnl=100.0, notional=20_000.0, fee_bps=0.5, slippage_bps=1.0)
        self.assertAlmostEqual(net, 97.0)

    def test_walk_forward_windows(self) -> None:
        items = list(range(20))
        windows = walk_forward_windows(items, train_size=10, test_size=5, step=5)

        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0][0], list(range(10)))
        self.assertEqual(windows[0][1], list(range(10, 15)))

    def test_run_backtest_returns_equity_curve(self) -> None:
        trades = [
            Trade(timestamp=dt.datetime(2026, 4, 1, 9, 31), side="long", contracts=1, entry=20000.0, exit=20005.0),
            Trade(timestamp=dt.datetime(2026, 4, 1, 9, 35), side="short", contracts=1, entry=20010.0, exit=20000.0),
        ]
        config = BacktestConfig(initial_equity=50_000.0, fee_bps=0.5, slippage_bps=0.5, point_value=2.0)

        result = run_backtest(trades, config)

        self.assertEqual(len(result.equity_curve), 3)
        self.assertGreater(result.equity_curve[-1], 50_000.0)
        self.assertEqual(len(result.trade_pnls), 2)


if __name__ == "__main__":
    unittest.main()
