from __future__ import annotations

from dataclasses import asdict
import datetime as dt
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bots.backtest import BacktestConfig, Trade
from trading_bots.evaluation_pipeline import evaluate_trades_for_apex, export_report_html, export_report_json
from trading_bots.strategy_v2 import StrategyV2Config, generate_trades_v2, load_bars_from_csv, _in_session


BEST_CFG = StrategyV2Config(
    short_only=True,
    use_edge_setup=True,
    use_lvn_setup=True,
    volz_edge_threshold=1.1,
    volz_lvn_threshold=1.4,
    hold_bars_edge=16,
    hold_bars_lvn=12,
    min_entry_gap_bars=40,
)


def _group_session_bars_by_day(bars: list[Any], cfg: StrategyV2Config) -> dict[dt.date, list[Any]]:
    by_day: dict[dt.date, list[Any]] = {}
    for b in bars:
        if _in_session(b.timestamp, cfg):
            by_day.setdefault(b.timestamp.date(), []).append(b)
    return by_day


def run_walk_forward(
    bars: list[Any],
    strategy_cfg: StrategyV2Config,
    backtest_cfg: BacktestConfig,
    train_days: int = 60,
    test_days: int = 20,
    step_days: int = 20,
) -> dict[str, Any]:
    by_day = _group_session_bars_by_day(bars, strategy_cfg)
    days = sorted(by_day.keys())
    if len(days) < train_days + test_days:
        raise ValueError(f"Nicht genug Handelstage für Walk-Forward: {len(days)} < {train_days + test_days}")

    all_oos_trades: list[Trade] = []
    window_reports: list[dict[str, Any]] = []

    i = train_days
    widx = 1
    while i + test_days <= len(days):
        train_slice = days[i - train_days : i]
        test_slice = days[i : i + test_days]
        context_slice = train_slice + test_slice

        context_bars: list[Any] = []
        for d in context_slice:
            context_bars.extend(by_day[d])

        raw = generate_trades_v2(context_bars, strategy_cfg)
        test_set = set(test_slice)
        oos_trades = [t for t in raw["trades"] if t.timestamp.date() in test_set]

        oos_trades.sort(key=lambda t: t.timestamp)
        all_oos_trades.extend(oos_trades)

        wr = evaluate_trades_for_apex(
            trades=oos_trades,
            backtest_config=backtest_cfg,
            account_type="intraday",
            account_size=50_000,
        )
        window_reports.append(
            {
                "window_index": widx,
                "train_start": str(train_slice[0]),
                "train_end": str(train_slice[-1]),
                "test_start": str(test_slice[0]),
                "test_end": str(test_slice[-1]),
                "trade_count": len(oos_trades),
                "kpis": wr.get("kpis", {}),
                "apex": wr.get("apex", {}),
            }
        )

        i += step_days
        widx += 1

    all_oos_trades.sort(key=lambda t: t.timestamp)
    final_report = evaluate_trades_for_apex(
        trades=all_oos_trades,
        backtest_config=backtest_cfg,
        account_type="intraday",
        account_size=50_000,
    )
    final_report["strategy"] = "v2_3_profile_edge_orderflow_walk_forward"
    final_report["strategy_config"] = asdict(strategy_cfg)
    final_report["walk_forward"] = {
        "train_days": train_days,
        "test_days": test_days,
        "step_days": step_days,
        "windows": len(window_reports),
        "window_reports": window_reports,
        "total_oos_trades": len(all_oos_trades),
    }
    return final_report


def main() -> None:
    csv_path = ROOT / "reports" / "cache" / "mnq_1m_2025-10-29_to_2026-04-27.csv.gz"
    out_prefix = ROOT / "reports" / "strategy_v2_3_walk_forward_profile_edge_orderflow"

    backtest_cfg = BacktestConfig(
        initial_equity=50_000.0,
        fee_bps=0.5,
        slippage_bps=0.5,
        point_value=2.0,
    )

    bars = load_bars_from_csv(csv_path)
    report = run_walk_forward(
        bars=bars,
        strategy_cfg=BEST_CFG,
        backtest_cfg=backtest_cfg,
        train_days=60,
        test_days=20,
        step_days=20,
    )

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = export_report_json(report, out_prefix.with_suffix(".json"))
    html_path = export_report_html(report, out_prefix.with_suffix(".html"))

    print("wf_windows:", report.get("walk_forward", {}).get("windows"))
    print("trade_count:", report.get("trade_count"))
    print("total_pnl:", report.get("kpis", {}).get("total_pnl"))
    print("win_rate:", report.get("kpis", {}).get("win_rate"))
    print("profit_factor:", report.get("kpis", {}).get("profit_factor"))
    print("max_drawdown:", report.get("kpis", {}).get("max_drawdown"))
    print("json:", json_path)
    print("html:", html_path)


if __name__ == "__main__":
    main()
