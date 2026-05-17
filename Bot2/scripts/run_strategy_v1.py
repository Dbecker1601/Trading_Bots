import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_bots.backtest import BacktestConfig
from trading_bots.strategy_v1 import StrategyV1Config, evaluate_strategy_v1_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Strategy v1 walk-forward evaluation and export JSON/HTML reports")
    parser.add_argument("--csv", required=True, help="Input bars CSV path")
    parser.add_argument("--output-prefix", default="reports/strategy_v1_walkforward", help="Output report prefix path")
    parser.add_argument("--account-type", default="intraday", choices=["intraday", "eod"])
    parser.add_argument("--account-size", type=int, default=50_000)
    parser.add_argument("--train-size", type=int, default=720)
    parser.add_argument("--test-size", type=int, default=360)
    parser.add_argument("--step", type=int, default=360)
    args = parser.parse_args()

    report = evaluate_strategy_v1_csv(
        csv_path=args.csv,
        output_prefix=args.output_prefix,
        strategy_config=StrategyV1Config(),
        backtest_config=BacktestConfig(initial_equity=float(args.account_size), fee_bps=0.5, slippage_bps=0.5, point_value=2.0),
        account_type=args.account_type,
        account_size=args.account_size,
        train_size=args.train_size,
        test_size=args.test_size,
        step=args.step,
    )

    print(f"JSON: {report['report_json_path']}")
    print(f"HTML: {report['report_html_path']}")
    print(f"Trade Count: {report['trade_count']}")
    print(f"Total PnL: {report['kpis']['total_pnl']}")
    print(f"Apex Passed: {report['apex']['passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
