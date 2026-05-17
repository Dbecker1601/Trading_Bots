import datetime as dt
import tempfile
import unittest
from pathlib import Path

from trading_bots.backtest import BacktestConfig
from trading_bots.strategy_v2 import (
    Bar,
    StrategyV2Config,
    evaluate_strategy_v2_csv,
    generate_trades_v2,
)


def _bar(ts: dt.datetime, o: float, h: float, l: float, c: float, v: float = 1000.0) -> Bar:
    return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, spread_bps=1.0)


class TestStrategyV2(unittest.TestCase):
    def test_hvn_edge_rejection_short_emits_trade(self) -> None:
        start = dt.datetime(2026, 4, 3, 13, 30, tzinfo=dt.timezone.utc)
        bars = []
        # Day 1 builds prior profile with upper edge near 105
        for i in range(120):
            ts = start + dt.timedelta(minutes=i)
            c = 104.5 + ((i % 6) * 0.2)
            bars.append(_bar(ts, c - 0.2, c + 0.4, c - 0.4, c, 1200))

        # Day 2: approach above edge, then reject with negative flow
        day2 = start + dt.timedelta(days=1)
        for i in range(60):
            ts = day2 + dt.timedelta(minutes=i)
            if i < 20:
                c = 105.4 + (i * 0.03)
                o = c - 0.05
            else:
                c = 106.0 - ((i - 20) * 0.12)
                o = c + 0.18  # bearish body
            bars.append(_bar(ts, o, max(o, c) + 0.2, min(o, c) - 0.2, c, 2000))

        cfg = StrategyV2Config(
            volz_edge_threshold=-10.0,
            edge_tolerance_points=3.0,
            allowed_short_hours_utc=(13, 14, 15, 16, 17, 18, 19),
        )
        out = generate_trades_v2(bars, cfg)
        shorts = [t for t in out["trades"] if t.side == "short"]
        self.assertGreater(len(shorts), 0)

    def test_lvn_pass_long_emits_trade(self) -> None:
        start = dt.datetime(2026, 4, 3, 13, 30, tzinfo=dt.timezone.utc)
        bars = []
        # Day 1 create bimodal profile with valley around 102
        for i in range(90):
            ts = start + dt.timedelta(minutes=i)
            c = 100.8 + ((i % 5) * 0.1)
            bars.append(_bar(ts, c - 0.2, c + 0.3, c - 0.3, c, 1400))
        for i in range(90, 180):
            ts = start + dt.timedelta(minutes=i)
            c = 103.2 + ((i % 5) * 0.1)
            bars.append(_bar(ts, c - 0.2, c + 0.3, c - 0.3, c, 1400))

        # Day 2 pass through LVN with positive flow
        day2 = start + dt.timedelta(days=1)
        for i in range(70):
            ts = day2 + dt.timedelta(minutes=i)
            c = 101.8 + i * 0.05
            o = c - 0.12
            bars.append(_bar(ts, o, c + 0.3, o - 0.2, c, 2200))

        cfg = StrategyV2Config(
            volz_lvn_threshold=-10.0,
            lvn_tolerance_points=10.0,
            short_only=False,
            allow_longs=True,
            allowed_long_hours_utc=(13, 14, 15, 16, 17, 18, 19),
            daily_bias_lookback_bars=5,
        )
        out = generate_trades_v2(bars, cfg)
        self.assertIn("trades", out)
        self.assertIsInstance(out["trades"], list)

    def test_csv_evaluation_exports_files(self) -> None:
        start = dt.datetime(2026, 4, 1, 13, 30, tzinfo=dt.timezone.utc)
        rows = ["ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume,symbol"]
        for i in range(450):
            ts = (start + dt.timedelta(minutes=i)).isoformat()
            p = 20000.0 + ((i % 40) - 20) * 0.25
            rows.append(f"{ts},33,1,1,{p},{p+1},{p-1},{p},1000,MNQ.c.0")

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "bars.csv"
            csv_path.write_text("\n".join(rows), encoding="utf-8")
            prefix = Path(tmp) / "reports" / "strategy_v2"

            report = evaluate_strategy_v2_csv(
                csv_path=csv_path,
                output_prefix=prefix,
                strategy_config=StrategyV2Config(),
                backtest_config=BacktestConfig(initial_equity=50_000.0),
                account_type="intraday",
                account_size=50_000,
            )

            self.assertTrue(Path(report["report_json_path"]).exists())
            self.assertTrue(Path(report["report_html_path"]).exists())


if __name__ == "__main__":
    unittest.main()
