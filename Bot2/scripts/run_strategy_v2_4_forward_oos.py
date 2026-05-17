from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import re
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_bots.backtest import BacktestConfig
from trading_bots.databento_client import create_databento_client
from trading_bots.market_data import fetch_historical_bars
from trading_bots.smoke import load_env_file
from trading_bots.strategy_v2 import StrategyV2Config, evaluate_strategy_v2_csv


def _clip_end_from_error(err_text: str) -> dt.datetime | None:
    m = re.search(r"available up to '([^']+)'", err_text)
    if not m:
        return None
    ts = dt.datetime.fromisoformat(m.group(1))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    # small safety margin
    return ts - dt.timedelta(minutes=1)


def _download_cache(cache_path: Path, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    load_env_file(str(REPO_ROOT / ".env"))
    client = create_databento_client()

    try:
        data = fetch_historical_bars(client=client, symbols=["MNQ.c.0"], start=start, end=end)
    except RuntimeError as exc:
        clipped = _clip_end_from_error(str(exc))
        if clipped is None or clipped <= start:
            raise
        data = fetch_historical_bars(client=client, symbols=["MNQ.c.0"], start=start, end=clipped)
        end = clipped

    if not hasattr(data, "to_df"):
        raise RuntimeError("Databento response does not support to_df()")

    df = data.to_df().reset_index()
    if len(df) == 0:
        raise RuntimeError("Databento lieferte 0 Zeilen im Forward-Zeitraum")

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
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache_path, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts_event", "open", "high", "low", "close", "volume"])
        w.writerows(rows)

    return {
        "rows": len(rows),
        "ts_min": rows[0][0],
        "ts_max": rows[-1][0],
        "cache_path": str(cache_path),
    }


def main() -> None:
    # echtes Forward-OOS: alles NACH dem bisherigen Ende 2026-04-27
    start = dt.datetime(2026, 4, 28, 0, 0, tzinfo=dt.timezone.utc)
    end = dt.datetime.now(dt.timezone.utc)

    cache_path = REPO_ROOT / "reports" / "cache" / f"mnq_1m_{start.date().isoformat()}_to_{end.date().isoformat()}_forward_oos.csv.gz"
    download_meta = _download_cache(cache_path, start, end)

    cfg = StrategyV2Config(
        short_only=True,
        use_edge_setup=True,
        use_lvn_setup=True,
        volz_edge_threshold=1.1,
        volz_lvn_threshold=1.4,
        hold_bars_edge=16,
        hold_bars_lvn=12,
        min_entry_gap_bars=40,
    )

    bt = BacktestConfig(initial_equity=50_000.0, fee_bps=0.5, slippage_bps=0.5, point_value=2.0)
    out_prefix = REPO_ROOT / "reports" / "strategy_v2_4_forward_oos_profile_edge_orderflow"

    report = evaluate_strategy_v2_csv(
        csv_path=cache_path,
        output_prefix=out_prefix,
        strategy_config=cfg,
        backtest_config=bt,
        account_type="intraday",
        account_size=50_000,
    )
    report["forward_window"] = {"start": start.isoformat(), "end": end.isoformat()}
    report["cache"] = download_meta

    json_path = Path(report["report_json_path"])
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    saved["forward_window"] = report["forward_window"]
    saved["cache"] = report["cache"]
    json_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    print("forward_start:", start.isoformat())
    print("forward_end:", end.isoformat())
    print("cache_rows:", download_meta["rows"])
    print("trade_count:", report.get("trade_count"))
    print("total_pnl:", report.get("kpis", {}).get("total_pnl"))
    print("win_rate:", report.get("kpis", {}).get("win_rate"))
    print("profit_factor:", report.get("kpis", {}).get("profit_factor"))
    print("max_drawdown:", report.get("kpis", {}).get("max_drawdown"))
    print("json:", report.get("report_json_path"))
    print("html:", report.get("report_html_path"))


if __name__ == "__main__":
    main()
