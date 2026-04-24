import datetime as dt
import unittest

from trading_bots.backtest import BacktestConfig, Trade
from trading_bots.evaluation_pipeline import evaluate_trades_for_apex


class TestEvaluationPipeline(unittest.TestCase):
    def test_evaluate_trades_for_apex_returns_combined_report(self) -> None:
        trades = [
            Trade(timestamp=dt.datetime(2026, 4, 1, 9, 31), side="long", contracts=1, entry=20000.0, exit=20003.0),
            Trade(timestamp=dt.datetime(2026, 4, 1, 10, 00), side="short", contracts=1, entry=20005.0, exit=20000.0),
        ]
        config = BacktestConfig(initial_equity=50_000.0, fee_bps=0.5, slippage_bps=0.5, point_value=2.0)

        report = evaluate_trades_for_apex(
            trades=trades,
            backtest_config=config,
            account_type="intraday",
            account_size=50_000,
        )

        self.assertIn("kpis", report)
        self.assertIn("apex", report)
        self.assertIn("equity_curve", report)


if __name__ == "__main__":
    unittest.main()
