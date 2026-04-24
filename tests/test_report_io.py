import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from trading_bots.backtest import BacktestConfig, Trade
from trading_bots.evaluation_pipeline import evaluate_trades_for_apex, export_report_json, export_report_html


class TestReportIO(unittest.TestCase):
    def test_export_json_and_html_report_files(self) -> None:
        trades = [
            Trade(timestamp=dt.datetime(2026, 4, 1, 9, 31), side="long", contracts=1, entry=20000.0, exit=20002.0),
            Trade(timestamp=dt.datetime(2026, 4, 1, 10, 0), side="short", contracts=1, entry=20003.0, exit=20000.0),
        ]
        report = evaluate_trades_for_apex(
            trades=trades,
            backtest_config=BacktestConfig(initial_equity=50_000.0),
            account_type="intraday",
            account_size=50_000,
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            json_path = export_report_json(report, out_dir / "report.json")
            html_path = export_report_html(report, out_dir / "report.html")

            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())

            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("kpis", loaded)
            self.assertIn("apex", loaded)

            html = html_path.read_text(encoding="utf-8")
            self.assertIn("Apex Compliance", html)
            self.assertIn("KPI Summary", html)


if __name__ == "__main__":
    unittest.main()
