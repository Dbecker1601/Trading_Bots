"""Databento/Yahoo data loader for 6E futures and EURUSD spot."""
from __future__ import annotations

import logging
import os

import pandas as pd

from config import (
    DATABENTO_DATASET,
    DATABENTO_FX_DATASET,
    DATABENTO_FX_STYPE,
    DATABENTO_FX_SYMBOL,
    DATABENTO_STYPE,
    DATABENTO_SYMBOL,
    SESSION_END_H,
    SESSION_START_H,
    YAHOO_SYMBOL,
)
from env_loader import load_project_env

log = logging.getLogger(__name__)

_YF_INTERVAL_MAP = {
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",
    "1d": "1d",
}
_DB_SCHEMA_MAP = {
    "15m": "ohlcv-15m",
    "1h": "ohlcv-1h",
    "4h": "ohlcv-1h",
    "1d": "ohlcv-1d",
}


def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.resample("4h", offset="0h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )


def _databento_market_config(market: str) -> tuple[str, str, str]:
    if market.upper() == "EURUSD":
        return DATABENTO_FX_DATASET, DATABENTO_FX_SYMBOL, DATABENTO_FX_STYPE
    return DATABENTO_DATASET, DATABENTO_SYMBOL, DATABENTO_STYPE


def _from_databento(interval: str, start: str, end: str, market: str = "6E") -> pd.DataFrame:
    import databento as db

    load_project_env()
    key = os.environ.get("DATABENTO_API_KEY", "")
    if not key:
        raise EnvironmentError("DATABENTO_API_KEY not set")

    schema = _DB_SCHEMA_MAP.get(interval, "ohlcv-1h")
    dataset, symbol, stype = _databento_market_config(market)
    log.info("Databento: %s %s %s to %s", symbol, schema, start, end)

    client = db.Historical(key=key)
    resp = client.timeseries.get_range(
        dataset=dataset,
        schema=schema,
        stype_in=stype,
        symbols=[symbol],
        start=start,
        end=end,
    )
    df = resp.to_df()

    ohlcv_cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[ohlcv_cols].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "datetime"

    if interval == "4h":
        df = _resample_4h(df)

    return df.astype(float)


def _from_yahoo(interval: str, start: str, end: str, market: str = "EURUSD") -> pd.DataFrame:
    import yfinance as yf

    yf_iv = _YF_INTERVAL_MAP.get(interval, "1h")
    log.info("Yahoo Finance: %s %s %s to %s", YAHOO_SYMBOL, yf_iv, start, end)

    raw = yf.download(YAHOO_SYMBOL, interval=yf_iv, start=start, end=end, progress=False)
    if raw.empty:
        raise ValueError(f"Yahoo returned no rows for {YAHOO_SYMBOL} {yf_iv} {start} to {end}")
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
    market: str = "6E",
) -> pd.DataFrame:
    """Load 6E/EURUSD OHLCV data, Databento first and Yahoo as development fallback."""
    try:
        return _from_databento(interval, start, end, market=market)
    except Exception as databento_exc:
        log.warning("Databento unavailable (%s) - using Yahoo Finance", databento_exc)
        try:
            return _from_yahoo(interval, start, end, market=market)
        except Exception as yahoo_exc:
            if market.upper() == "EURUSD":
                log.warning(
                    "EURUSD spot fallback unavailable (%s) - using 6E futures as proxy data",
                    yahoo_exc,
                )
                return _from_databento(interval, start, end, market="6E")
            raise


def load_session(
    interval: str = "1h",
    start: str = "2020-01-01",
    end: str = "2024-06-01",
    market: str = "6E",
) -> pd.DataFrame:
    """Load data and filter to active trading session unless daily bars are requested."""
    df = load(interval, start, end, market=market)
    if interval != "1d":
        df = df[df.index.hour.isin(range(SESSION_START_H, SESSION_END_H))]
    return df.copy()
