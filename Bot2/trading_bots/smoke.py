import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, MutableMapping

from trading_bots.databento_client import create_databento_client
from trading_bots.market_data import fetch_historical_bars


def load_env_file(
    path: str = ".env",
    environ: MutableMapping[str, str] | None = None,
) -> list[str]:
    """Load KEY=VALUE pairs from .env into the given environment mapping."""
    target = environ if environ is not None else os.environ
    env_path = Path(path)
    if not env_path.exists():
        return []

    loaded_keys: list[str] = []
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        target[key] = value.strip()
        loaded_keys.append(key)
    return loaded_keys


def _default_window() -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime(2026, 4, 1, 9, 30)
    end = dt.datetime(2026, 4, 1, 9, 45)
    return start, end


def run_databento_smoke_test(
    symbol: str = "MNQ.c.0",
    output_dir: str = "reports",
    sample_rows: int = 20,
) -> dict[str, Any]:
    """Run a minimal authenticated Databento pull and persist sample artifacts."""
    load_env_file()
    client = create_databento_client()

    start, end = _default_window()
    data = fetch_historical_bars(
        client=client,
        symbols=[symbol],
        start=start,
        end=end,
    )

    if not hasattr(data, "to_df"):
        raise RuntimeError("Databento response does not support to_df(); cannot build sample output")

    df = data.to_df()
    row_count = int(len(df))
    if row_count == 0:
        raise RuntimeError("Databento returned 0 rows for smoke-test window")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "smoke_first_pull.csv"
    json_path = out_dir / "smoke_first_pull_summary.json"

    sample = df.head(sample_rows)
    sample.to_csv(csv_path)

    first_ts = str(df.index[0]) if row_count > 0 else None
    last_ts = str(df.index[-1]) if row_count > 0 else None
    columns = [str(c) for c in df.columns]

    summary: dict[str, Any] = {
        "symbol": symbol,
        "dataset": "GLBX.MDP3",
        "schema": "ohlcv-1m",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rows_total": row_count,
        "rows_saved": int(len(sample)),
        "columns": columns,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "csv_path": str(csv_path),
    }

    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    summary["json_path"] = str(json_path)
    return summary
