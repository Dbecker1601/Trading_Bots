"""
Databento data loader for 6E (Euro FX Futures) / EURUSD.

Priority:
  1. Databento API  → CME Globex 6E continuous contract
  2. Yahoo Finance  → EURUSD=X spot (fallback, structurally identical for backtesting)

Returns plain pandas DataFrames (columns: open, high, low, close, volume, UTC index).
"""
from __future__ import annotations

import logging
import os

import pandas as pd

from config import (
    DATABENTO_DATASET, DATABENTO_SYMBOL, DATABENTO_STYPE,
    SESSION_START_H, SESSION_END_H, YAHOO_SYMBOL,
)

log = logging.getLogger(__name__)

_YF_INTERVAL_MAP = {
    "15m": "15m",
    "1h":  "1h",
    "4h":  "1h",    # resample 1h → 4h
    "1d":  "1d",
}
_DB_SCHEMA_MAP = {
    "15m": "ohlcv-15m",
    "1h":  "ohlcv-1h",
    "4h":  "ohlcv-1h",   # resample 1h → 4h
    "1d":  "ohlcv-1d",
}
_RESAMPLE_RULES = {"4h": "4h"}


def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.resample("4h", offset="0h")
        .agg({"open": "first", "high": "max", "low": "min",
              "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )


def _from_databento(interval: str, start: str, end: str) -> pd.DataFrame:
    import databento as db

    key = os.environ.get("DATABENTO_API_KEY", "")
    if not key:
        raise EnvironmentError("DATABENTO_API_KEY not set")

    schema = _DB_SCHEMA_MAP.get(interval, "ohlcv-1h")
    log.info("Databento: %s %s %s→%s", DATABENTO_SYMBOL, schema, start, end)

    client = db.Historical(key=key)
    resp = client.timeseries.get_range(
        dataset=DATABENTO_DATASET,
        schema=schema,
        stype_in=DATABENTO_STYPE,
        symbols=[DATABENTO_SYMBOL],
        start=start,
        end=end,
    )
    df = resp.to_df()

    # Normalize: keep only OHLCV, ensure UTC DatetimeIndex
    ohlcv_cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[ohlcv_cols].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "datetime"

    if interval == "4h":
        df = _resample_4h(df)

    return df.astype(float)


def _from_yahoo(interval: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    yf_iv = _YF_INTERVAL_MAP.get(interval, "1h")
    log.info("Yahoo Finance: %s %s %s→%s", YAHOO_SYMBOL, yf_iv, start, end)

    raw = yf.download(YAHOO_SYMBOL, interval=yf_iv, start=start, end=end, progress=False)
    raw.columns = [c.lower() for c in raw.columns.get_level_values(0)]
    df = raw[["open", "high", "low", "close", "volume"]].copy()

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "datetime"

    if interval == "4h":
        df = _resample_4h(df)

    return df.astype(float).dropna()


def load(
    interval: str = "1h",
    start: str = "2020-01-01",
    end: str = "2024-06-01",
) -> pd.DataFrame:
    """Load 6E/EURUSD OHLCV data. Tries Databento first, falls back to Yahoo Finance."""
    try:
        return _from_databento(interval, start, end)
    except Exception as exc:
        log.warning("Databento unavailable (%s) – using Yahoo Finance", exc)
        return _from_yahoo(interval, start, end)


def load_session(
    interval: str = "1h",
    start: str = "2020-01-01",
    end: str = "2024-06-01",
) -> pd.DataFrame:
    """Load data and filter to active trading session (SESSION_START_H – SESSION_END_H UTC).

    No session filter is applied for daily ('1d') data.
    """
    df = load(interval, start, end)
    if interval != "1d":
        df = df[df.index.hour.isin(range(SESSION_START_H, SESSION_END_H))]
    return df.copy()
