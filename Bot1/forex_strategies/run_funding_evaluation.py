from __future__ import annotations

import argparse
from pathlib import Path

from databento_loader import load, load_session
from evaluation_pipeline import (
    evaluate_portfolio_for_funding,
    export_report_html,
    export_report_json,
)
from strategy1_donchian import run as run_s1
from strategy2_mtf_rsi import run as run_s2
from strategy3_optimizer import _run_single


def _run_strategy(track: str, strategy: str, start: str, end: str):
    market = "EURUSD" if track == "eurusd" else "6E"
    if strategy == "s1":
        df = load_session("1h", start=start, end=end, market=market)
        return run_s1(df), "S1 Donchian H1"
    if strategy == "s2":
        df_h1 = load_session("1h", start=start, end=end, market=market)
        df_h4 = load("4h", start=start, end=end, market=market)
        df_d1 = load("1d", start=start, end=end, market=market)
        return run_s2(df_h1, df_h4, df_d1), "S2 MTF RSI"
    if strategy == "s3":
        df = load_session("4h", start=start, end=end, market=market)
        return _run_single(df, fast=10, slow=50, atr_p=14, sl_m=2.0, rr=2.5, adx_min=20), "S3 EMA ADX"
    raise ValueError(f"Unknown strategy: {strategy}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Bot1 strategies against funding gates.")
    parser.add_argument("--track", choices=["6e", "eurusd"], default="6e")
    parser.add_argument("--strategy", choices=["s1", "s2", "s3"], default="s1")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-05-01")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()

    profile_key = "FTMO_100K_2STEP" if args.track == "eurusd" else "APEX_50K_INTRADAY"
    symbol = "EURUSD" if args.track == "eurusd" else "6E"
    portfolio, strategy_name = _run_strategy(args.track, args.strategy, args.start, args.end)
    report = evaluate_portfolio_for_funding(
        portfolio,
        profile_key=profile_key,
        strategy_name=strategy_name,
        symbol=symbol,
    )

    out_dir = Path(args.output_dir)
    stem = f"{args.track}_{args.strategy}_funding_evaluation"
    json_path = export_report_json(report, out_dir / f"{stem}.json")
    html_path = export_report_html(report, out_dir / f"{stem}.html")

    print(f"funding_ready: {report['funding_ready']}")
    print(f"json: {json_path}")
    print(f"html: {html_path}")


if __name__ == "__main__":
    main()
