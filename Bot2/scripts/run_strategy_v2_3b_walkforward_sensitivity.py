from __future__ import annotations

import csv
from dataclasses import asdict
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bots.backtest import BacktestConfig, Trade
from trading_bots.evaluation_pipeline import evaluate_trades_for_apex
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
    train_days: int,
    test_days: int,
    step_days: int,
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
    agg = evaluate_trades_for_apex(
        trades=all_oos_trades,
        backtest_config=backtest_cfg,
        account_type="intraday",
        account_size=50_000,
    )
    return {
        "schema": {"train_days": train_days, "test_days": test_days, "step_days": step_days},
        "kpis": agg.get("kpis", {}),
        "apex": agg.get("apex", {}),
        "trade_count": agg.get("trade_count", len(all_oos_trades)),
        "windows": len(window_reports),
        "window_reports": window_reports,
    }


def main() -> None:
    csv_path = ROOT / "reports" / "cache" / "mnq_1m_2025-10-29_to_2026-04-27.csv.gz"
    out_prefix = ROOT / "reports" / "strategy_v2_3b_walk_forward_sensitivity"

    bars = load_bars_from_csv(csv_path)
    bt = BacktestConfig(initial_equity=50_000.0, fee_bps=0.5, slippage_bps=0.5, point_value=2.0)

    schemas = [(40, 20, 20), (60, 20, 20), (80, 20, 20)]
    results: list[dict[str, Any]] = []
    for tr, te, st in schemas:
        results.append(run_walk_forward(bars, BEST_CFG, bt, train_days=tr, test_days=te, step_days=st))

    def score(item: dict[str, Any]) -> tuple[float, float, float]:
        k = item.get("kpis", {})
        return (
            float(k.get("profit_factor") or 0.0),
            float(k.get("total_pnl") or 0.0),
            float(k.get("max_drawdown") or -1e12),
        )

    ranked = sorted(results, key=score, reverse=True)

    payload = {
        "strategy": "v2_3b_profile_edge_orderflow_walk_forward_sensitivity",
        "strategy_config": asdict(BEST_CFG),
        "source_csv": str(csv_path),
        "results": results,
        "ranked": ranked,
        "best_schema": ranked[0]["schema"] if ranked else None,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = out_prefix.with_suffix(".json")
    csv_out = out_prefix.with_suffix(".csv")
    html_out = out_prefix.with_suffix(".html")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(csv_out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["train_days", "test_days", "step_days", "windows", "trade_count", "total_pnl", "win_rate", "profit_factor", "max_drawdown", "apex_passed"])
        for r in ranked:
            s = r["schema"]
            k = r.get("kpis", {})
            a = r.get("apex", {})
            w.writerow([
                s["train_days"], s["test_days"], s["step_days"], r.get("windows"), r.get("trade_count"),
                k.get("total_pnl"), k.get("win_rate"), k.get("profit_factor"), k.get("max_drawdown"), a.get("passed")
            ])

    rows = []
    for r in ranked:
        s = r["schema"]
        k = r.get("kpis", {})
        rows.append(
            f"<tr><td>{s['train_days']}/{s['test_days']}/{s['step_days']}</td><td>{r.get('windows')}</td><td>{r.get('trade_count')}</td>"
            f"<td>{k.get('total_pnl', 0):.2f}</td><td>{(k.get('win_rate', 0)*100):.2f}%</td><td>{k.get('profit_factor', 0):.3f}</td><td>{k.get('max_drawdown', 0):.2f}</td></tr>"
        )
    html = (
        "<html><head><meta charset='utf-8'><title>v2.3b Walk-Forward Sensitivity</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;}table{border-collapse:collapse;}th,td{border:1px solid #ccc;padding:8px;}th{background:#f2f2f2;}</style>"
        "</head><body>"
        "<h1>v2.3b Walk-Forward Sensitivity (Best-Set fixed)</h1>"
        f"<p>Best Schema: {payload['best_schema']}</p>"
        "<table><tr><th>Schema train/test/step</th><th>Windows</th><th>Trades</th><th>Total PnL</th><th>Winrate</th><th>PF</th><th>Max DD</th></tr>"
        + "".join(rows)
        + "</table></body></html>"
    )
    with open(html_out, "w", encoding="utf-8") as f:
        f.write(html)

    best = ranked[0]
    print("best_schema:", best["schema"])
    print("total_pnl:", best.get("kpis", {}).get("total_pnl"))
    print("win_rate:", best.get("kpis", {}).get("win_rate"))
    print("profit_factor:", best.get("kpis", {}).get("profit_factor"))
    print("max_drawdown:", best.get("kpis", {}).get("max_drawdown"))
    print("json:", json_path)
    print("csv:", csv_out)
    print("html:", html_out)


if __name__ == "__main__":
    main()
