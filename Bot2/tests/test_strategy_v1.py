import datetime as dt
import tempfile
import unittest
from pathlib import Path

from trading_bots.backtest import BacktestConfig
from trading_bots.strategy_v1 import (
    Bar,
    StrategyV1Config,
    evaluate_strategy_v1_csv,
    generate_trades_v1,
    run_walk_forward_evaluation,
)


def _make_bar(ts: dt.datetime, price: float) -> Bar:
    return Bar(
        timestamp=ts,
        open=price,
        high=price + 1.0,
        low=price - 1.0,
        close=price,
        volume=1000,
        spread_bps=1.0,
    )


class TestStrategyV1(unittest.TestCase):
    def test_no_lookahead_signals_unchanged_for_past_when_future_changes(self) -> None:
        start = dt.datetime(2026, 4, 1, 13, 30)
        bars = [_make_bar(start + dt.timedelta(minutes=i), 20000.0 + i * 0.5) for i in range(180)]

        cfg = StrategyV1Config(ema_fast=5, ema_slow=15, breakout_lookback=10, range_lookback=10)
        decisions_a = generate_trades_v1(bars, cfg, return_decisions=True)["decisions"]

        bars_changed = list(bars)
        bars_changed[-1] = _make_bar(bars_changed[-1].timestamp, 40000.0)
        decisions_b = generate_trades_v1(bars_changed, cfg, return_decisions=True)["decisions"]

        self.assertEqual(decisions_a[:-1], decisions_b[:-1])

    def test_session_filter_blocks_entries_outside_window(self) -> None:
        start = dt.datetime(2026, 4, 1, 2, 0)  # outside configured session
        bars = [_make_bar(start + dt.timedelta(minutes=i), 20000.0 + i * 0.4) for i in range(200)]

        cfg = StrategyV1Config(session_start_utc_minute=13 * 60 + 30, session_end_utc_minute=20 * 60)
        result = generate_trades_v1(bars, cfg, return_decisions=False)

        self.assertEqual(len(result["trades"]), 0)

    def test_kill_switch_stops_new_entries_after_daily_loss_limit(self) -> None:
        start = dt.datetime(2026, 4, 1, 13, 30)
        bars = [_make_bar(start + dt.timedelta(minutes=i), 20000.0 + i * 0.2) for i in range(220)]

        cfg = StrategyV1Config(
            ema_fast=3,
            ema_slow=7,
            breakout_lookback=6,
            range_lookback=6,
            max_daily_loss=0.0,  # immediate kill switch when day_pnl starts at 0
            min_hold_bars=1,
            max_hold_bars=5,
        )
        result = generate_trades_v1(bars, cfg, return_decisions=True)

        decisions = result["decisions"]
        kill_indices = [i for i, d in enumerate(decisions) if d == "kill_switch"]
        self.assertTrue(kill_indices)

    def test_walk_forward_returns_report_and_windows(self) -> None:
        start = dt.datetime(2026, 4, 1, 13, 30)
        bars = [_make_bar(start + dt.timedelta(minutes=i), 20000.0 + i * 0.3) for i in range(400)]

        cfg = StrategyV1Config(ema_fast=5, ema_slow=15, breakout_lookback=10, range_lookback=10)
        report = run_walk_forward_evaluation(
            bars=bars,
            strategy_config=cfg,
            backtest_config=BacktestConfig(initial_equity=50_000.0),
            account_type="intraday",
            account_size=50_000,
            train_size=120,
            test_size=120,
            step=120,
        )

        self.assertIn("kpis", report)
        self.assertIn("apex", report)
        self.assertIn("walk_forward", report)
        self.assertGreaterEqual(len(report["walk_forward"]["windows"]), 1)

    def test_csv_evaluation_exports_json_and_html(self) -> None:
        start = dt.datetime(2026, 4, 1, 13, 30, tzinfo=dt.timezone.utc)
        rows = ["ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume,symbol"]
        for i in range(360):
            ts = (start + dt.timedelta(minutes=i)).isoformat()
            p = 20000.0 + i * 0.25
            rows.append(f"{ts},33,1,1,{p},{p+1},{p-1},{p},1000,MNQ.c.0")

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "bars.csv"
            csv_path.write_text("\n".join(rows), encoding="utf-8")

            prefix = Path(tmp) / "reports" / "strategy_v1"
            report = evaluate_strategy_v1_csv(
                csv_path=csv_path,
                output_prefix=prefix,
                strategy_config=StrategyV1Config(ema_fast=5, ema_slow=15),
                backtest_config=BacktestConfig(initial_equity=50_000.0),
                account_type="intraday",
                account_size=50_000,
                train_size=120,
                test_size=120,
                step=120,
            )

            self.assertTrue(Path(report["report_json_path"]).exists())
            self.assertTrue(Path(report["report_html_path"]).exists())


if __name__ == "__main__":
    unittest.main()
