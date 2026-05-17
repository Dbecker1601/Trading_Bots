from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bots.backtest import BacktestConfig
from trading_bots.strategy_v2 import StrategyV2Config, evaluate_strategy_v2_csv


def main() -> None:
    csv_path = ROOT / "reports" / "cache" / "mnq_1m_2025-10-29_to_2026-04-27.csv.gz"
    out_prefix = ROOT / "reports" / "strategy_v2_1_profile_edge_orderflow"

    report = evaluate_strategy_v2_csv(
        csv_path=csv_path,
        output_prefix=out_prefix,
        strategy_config=StrategyV2Config(),
        backtest_config=BacktestConfig(
            initial_equity=50_000.0,
            fee_bps=0.5,
            slippage_bps=0.5,
            point_value=2.0,
        ),
        account_type="intraday",
        account_size=50_000,
    )

    print("trade_count:", report.get("trade_count"))
    print("total_pnl:", report.get("kpis", {}).get("total_pnl"))
    print("win_rate:", report.get("kpis", {}).get("win_rate"))
    print("profit_factor:", report.get("kpis", {}).get("profit_factor"))
    print("json:", report.get("report_json_path"))
    print("html:", report.get("report_html_path"))


if __name__ == "__main__":
    main()
