import csv
import datetime as dt
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_bots.backtest import BacktestConfig, Trade, run_backtest
from trading_bots.evaluation_pipeline import evaluate_trades_for_apex
from trading_bots.market_data import fetch_historical_bars
from trading_bots.databento_client import create_databento_client
from trading_bots.smoke import load_env_file
from trading_bots.strategy_v1 import Bar, StrategyV1Config, generate_trades_v1


REPORTS_DIR = REPO_ROOT / "reports"
CACHE_DIR = REPORTS_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

ACCOUNT_SIZE = 50_000
ACCOUNT_TYPE = "intraday"
SYMBOL = "MNQ.c.0"
LEARNING_CANDIDATES = [5, 10, 15, 20, 30, 45, 60, 90]

BACKTEST_CONFIG = BacktestConfig(
    initial_equity=float(ACCOUNT_SIZE),
    fee_bps=0.5,
    slippage_bps=0.5,
    point_value=2.0,
)

VARIANT_CONFIGS: dict[str, StrategyV1Config] = {
    "v1_default": StrategyV1Config(),
    "v1_conservative": StrategyV1Config(
        range_zscore_entry=1.6,
        risk_off_vol_threshold=0.0024,
        trend_threshold_points=8.0,
        stop_atr_mult=1.3,
        trailing_atr_mult=2.2,
        no_new_entries_last_minutes=20,
        max_daily_loss=-350.0,
        max_contracts=3,
        risk_per_trade=0.002,
        max_spread_bps_for_entry=2.0,
    ),
    "v1_aggressive": StrategyV1Config(
        range_zscore_entry=1.0,
        risk_off_vol_threshold=0.0032,
        trend_threshold_points=4.0,
        stop_atr_mult=1.0,
        trailing_atr_mult=1.6,
        no_new_entries_last_minutes=5,
        max_daily_loss=-700.0,
        max_contracts=8,
        risk_per_trade=0.005,
        max_spread_bps_for_entry=4.0,
    ),
}


def _utc_day_boundaries() -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_utc = now_utc.date()
    test_end = dt.datetime.combine(today_utc, dt.time.min, tzinfo=dt.timezone.utc)
    test_start = test_end - dt.timedelta(days=90)
    data_start = test_start - dt.timedelta(days=max(LEARNING_CANDIDATES))
    return data_start, test_start, test_end


def _cache_path(data_start: dt.datetime, test_end: dt.datetime) -> Path:
    return CACHE_DIR / f"mnq_1m_{data_start.date().isoformat()}_to_{test_end.date().isoformat()}.csv.gz"


def _download_to_cache(cache_path: Path, data_start: dt.datetime, test_end: dt.datetime) -> dict[str, Any]:
    load_env_file(str(REPO_ROOT / ".env"))
    client = create_databento_client()
    data = fetch_historical_bars(client=client, symbols=[SYMBOL], start=data_start, end=test_end)
    if not hasattr(data, "to_df"):
        raise RuntimeError("Databento response does not support to_df()")

    df = data.to_df().reset_index()
    if len(df) == 0:
        raise RuntimeError("Databento lieferte 0 Zeilen")

    ts_col = "ts_event" if "ts_event" in df.columns else str(df.columns[0])
    rows: list[tuple[str, float, float, float, float, float]] = []
    for _, r in df.iterrows():
        ts = r[ts_col]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if not isinstance(ts, dt.datetime):
            ts = dt.datetime.fromisoformat(str(ts))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        ts = ts.astimezone(dt.timezone.utc)
        volume = float(r["volume"]) if "volume" in df.columns and r["volume"] is not None else 0.0
        rows.append((ts.isoformat(), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), volume))

    rows.sort(key=lambda x: x[0])
    with gzip.open(cache_path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ts_event", "open", "high", "low", "close", "volume"])
        writer.writerows(rows)

    return {"rows": len(rows), "ts_min": rows[0][0], "ts_max": rows[-1][0], "cache_path": str(cache_path)}


def _load_bars_from_cache(cache_path: Path) -> list[Bar]:
    bars: list[Bar] = []
    with gzip.open(cache_path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = dt.datetime.fromisoformat(row["ts_event"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            bars.append(
                Bar(
                    timestamp=ts.astimezone(dt.timezone.utc),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                    spread_bps=1.0,
                )
            )
    if not bars:
        raise RuntimeError("Cache enthält keine Daten")
    return bars


def _slice_trades(trades: list[Trade], start: dt.datetime, end: dt.datetime) -> list[Trade]:
    return [t for t in trades if start <= t.timestamp < end]


def _eval_trades(trades: list[Trade]) -> dict[str, Any]:
    rep = evaluate_trades_for_apex(
        trades=trades,
        backtest_config=BACKTEST_CONFIG,
        account_type=ACCOUNT_TYPE,
        account_size=ACCOUNT_SIZE,
    )
    return {
        "trade_count": rep["trade_count"],
        "kpis": rep["kpis"],
        "apex": rep["apex"],
        "trade_pnls": rep["trade_pnls"],
    }


def _select_best_variant(training_reports: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        r for r in training_reports
        if r["apex"].get("passed", False) and float(r["kpis"].get("max_drawdown", 0.0)) >= -2000.0
    ]
    if not eligible:
        eligible = [r for r in training_reports if r["apex"].get("passed", False)]
    if not eligible:
        eligible = list(training_reports)

    return sorted(
        eligible,
        key=lambda r: (float(r["kpis"].get("sharpe_like", 0.0)), float(r["kpis"].get("total_pnl", 0.0))),
        reverse=True,
    )[0]


def _loss_diagnostics(trades: list[Trade]) -> dict[str, Any]:
    bt = run_backtest(trades, BACKTEST_CONFIG)
    losses: list[dict[str, Any]] = []
    for tr, pnl in zip(trades, bt.trade_pnls):
        if pnl < 0:
            losses.append(
                {
                    "timestamp": tr.timestamp.isoformat(),
                    "side": tr.side,
                    "contracts": tr.contracts,
                    "entry": tr.entry,
                    "exit": tr.exit,
                    "pnl": pnl,
                }
            )
    losses_sorted = sorted(losses, key=lambda x: x["pnl"])
    return {
        "loss_trades": len(losses_sorted),
        "sum_losses": float(sum(x["pnl"] for x in losses_sorted)),
        "largest_loss": float(losses_sorted[0]["pnl"]) if losses_sorted else 0.0,
        "top_5_loss_trades": losses_sorted[:5],
    }


def _build_html(report: dict[str, Any]) -> str:
    rows = []
    for c in report["candidate_results"]:
        o = c["oos"]
        k = o["kpis"]
        rows.append(
            f"<tr><td>{c['learning_days']}</td><td>{c['selected_variant']}</td><td>{o['trade_count']}</td>"
            f"<td>{k['total_pnl']:.2f}</td><td>{k['win_rate']:.4f}</td><td>{k['profit_factor']:.4f}</td>"
            f"<td>{k['max_drawdown']:.2f}</td><td>{k['sharpe_like']:.4f}</td><td>{o['apex']['passed']}</td></tr>"
        )

    best = report["best_candidate"]
    second = report["second_best_candidate"]

    return f"""<!doctype html>
<html lang='de'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>90d Lernfenster Vergleich</title>
<style>
body {{font-family:Arial,sans-serif;background:#0b1020;color:#e8ecff;padding:20px;}}
.card {{background:#121933;border:1px solid #23305f;border-radius:10px;padding:14px;margin-bottom:14px;}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:8px;border-bottom:1px solid #23305f;text-align:left}}
</style></head><body>
<h1>MNQ Strategy v1: 90d OOS Lernfenster-Vergleich</h1>
<div class='card'><p><b>Testfenster (UTC):</b> {report['test_window']['start']} bis {report['test_window']['end']} (Ende exkl.)</p>
<p><b>Best:</b> {best['learning_days']} Tage / {best['selected_variant']} | <b>Second:</b> {second['learning_days']} Tage / {second['selected_variant']}</p></div>
<div class='card'><table><thead><tr><th>Lerntage</th><th>Variante</th><th>Trades</th><th>Total PnL</th><th>Win Rate</th><th>Profit Factor</th><th>Max DD</th><th>Sharpe-like</th><th>Apex</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
</body></html>"""


def main() -> int:
    data_start, test_start, test_end = _utc_day_boundaries()
    cache_path = _cache_path(data_start, test_end)
    downloaded_now = False
    download_meta = None

    if not cache_path.exists():
        download_meta = _download_to_cache(cache_path, data_start, test_end)
        downloaded_now = True

    bars_all = _load_bars_from_cache(cache_path)

    # Performance-Optimierung: nur reguläre Strategy-Session (13:30-20:00 UTC) behalten.
    bars = [b for b in bars_all if (13 * 60 + 30) <= (b.timestamp.hour * 60 + b.timestamp.minute) < (20 * 60)]

    precomputed_trades: dict[str, list[Trade]] = {}
    for name, cfg in VARIANT_CONFIGS.items():
        precomputed_trades[name] = generate_trades_v1(bars, cfg, return_decisions=False)["trades"]

    candidate_results: list[dict[str, Any]] = []

    for learning_days in LEARNING_CANDIDATES:
        train_start = test_start - dt.timedelta(days=learning_days)

        training_variant_reports = []
        for variant_name in VARIANT_CONFIGS:
            train_trades = _slice_trades(precomputed_trades[variant_name], train_start, test_start)
            train_eval = _eval_trades(train_trades)
            training_variant_reports.append(
                {
                    "variant": variant_name,
                    "trade_count": train_eval["trade_count"],
                    "kpis": train_eval["kpis"],
                    "apex": train_eval["apex"],
                }
            )

        selected = _select_best_variant(training_variant_reports)
        selected_name = selected["variant"]
        oos_trades = _slice_trades(precomputed_trades[selected_name], test_start, test_end)
        oos_eval = _eval_trades(oos_trades)

        candidate_results.append(
            {
                "learning_days": learning_days,
                "train_window": {"start": train_start.isoformat(), "end": test_start.isoformat()},
                "selected_variant": selected_name,
                "training_variant_reports": training_variant_reports,
                "selection_basis": {
                    "primary": "sharpe_like",
                    "risk_constraint": "apex_passed=true and max_drawdown >= -2000",
                    "tiebreaker": "higher_total_pnl",
                },
                "oos": {
                    **oos_eval,
                    "loss_diagnostics": _loss_diagnostics(oos_trades),
                },
            }
        )

    ranked = sorted(
        candidate_results,
        key=lambda c: (float(c["oos"]["kpis"]["sharpe_like"]), float(c["oos"]["kpis"]["total_pnl"])),
        reverse=True,
    )

    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else ranked[0]

    report = {
        "symbol": SYMBOL,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "test_window": {"start": test_start.isoformat(), "end": test_end.isoformat()},
        "data_window": {"start": data_start.isoformat(), "end": test_end.isoformat()},
        "cache": {
            "path": str(cache_path),
            "downloaded_now": downloaded_now,
            "download_meta": download_meta,
            "bars_loaded_total": len(bars_all),
            "bars_used_session_only": len(bars),
        },
        "variants": {k: asdict(v) for k, v in VARIANT_CONFIGS.items()},
        "learning_candidates": LEARNING_CANDIDATES,
        "candidate_results": candidate_results,
        "best_candidate": {
            "learning_days": best["learning_days"],
            "selected_variant": best["selected_variant"],
            "oos": best["oos"],
            "loss_diagnostics": best["oos"]["loss_diagnostics"],
        },
        "second_best_candidate": {
            "learning_days": second["learning_days"],
            "selected_variant": second["selected_variant"],
            "oos": second["oos"],
        },
        "method_note": "Variante je Lerntage via Trainingsfenster gewählt, OOS fix auf identischem 90d-Fenster. Trades pro Variante wurden einmal über den Gesamtzeitraum erzeugt und für Train/OOS zeitlich gesliced (kein Lookahead aus Testdaten in die Auswahl).",
    }

    json_path = REPORTS_DIR / "strategy_v1_90d_learning_window_comparison.json"
    html_path = REPORTS_DIR / "strategy_v1_90d_learning_window_comparison.html"
    csv_path = REPORTS_DIR / "strategy_v1_90d_learning_window_comparison_summary.csv"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    html_path.write_text(_build_html(report), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["learning_days", "selected_variant", "trades", "total_pnl", "win_rate", "profit_factor", "max_drawdown", "sharpe_like", "apex_passed"])
        for c in ranked:
            o = c["oos"]
            k = o["kpis"]
            w.writerow([c["learning_days"], c["selected_variant"], o["trade_count"], k["total_pnl"], k["win_rate"], k["profit_factor"], k["max_drawdown"], k["sharpe_like"], o["apex"]["passed"]])

    print(json.dumps({
        "json": str(json_path),
        "html": str(html_path),
        "csv": str(csv_path),
        "best_learning_days": best["learning_days"],
        "best_variant": best["selected_variant"],
        "second_learning_days": second["learning_days"],
        "second_variant": second["selected_variant"],
        "cache_path": str(cache_path),
        "downloaded_now": downloaded_now,
    }, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
