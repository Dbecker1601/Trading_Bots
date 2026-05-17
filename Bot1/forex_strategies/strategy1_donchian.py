"""
Strategie 1 – Donchian Channel Breakout  (verbessert für 6E / EUR/USD)

Kernidee:
  Preis bricht über N-Perioden-Hoch → Long-Entry (umgekehrt Short).
  Zwei zusätzliche Filter reduzieren Fehlsignale stark:
    1. ADX-Filter   : nur handeln wenn Trend stark genug (ADX > adx_min)
    2. Session-Filter: nur aktive UTC-Stunden (7–17 h)

  Exits ausschließlich über Hard-SL und Hard-TP (ATR-basiert, RR 1:2).
  Keine Kreuz-Exits → konsistente R-Multiples → maximaler SQN.

Timeframe: H1 (empfohlen für 6E; mehr Trades → höheres √N in SQN-Formel)

SQN-Ziel: ≥ 2.5
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange

from config import FEES, INIT_CASH, SESSION_START_H, SESSION_END_H
from databento_loader import load_session
from prop_firm_score import compute_metrics, print_prop_firm_report

# ── Default Parameters ────────────────────────────────────────────────────────
CHANNEL_WINDOW = 20     # Donchian-Kanal Perioden
ATR_PERIOD     = 14
SL_MULT        = 2.0    # ATR-Multiplikator Stop-Loss
TP_MULT        = 4.0    # ATR-Multiplikator Take-Profit  (RR 1:2)
ADX_MIN        = 20     # Mindest-ADX für Trendstärke-Filter
ADX_PERIOD     = 14


def _signals(df: pd.DataFrame,
             channel_window: int = CHANNEL_WINDOW,
             atr_period: int = ATR_PERIOD,
             sl_mult: float = SL_MULT,
             tp_mult: float = TP_MULT,
             adx_min: float = ADX_MIN,
             adx_period: int = ADX_PERIOD,
             session_filter: bool = True) -> tuple:
    """Berechnet Long/Short Entries und SL/TP-Stops."""
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # ATR
    atr = AverageTrueRange(high=high, low=low, close=close,
                           window=atr_period).average_true_range()

    # Donchian-Kanal
    donchian_high = high.rolling(channel_window).max().shift(1)
    donchian_low  = low.rolling(channel_window).min().shift(1)

    # ADX-Trendstärke-Filter
    adx_ind = ADXIndicator(high=high, low=low, close=close, window=adx_period)
    adx     = adx_ind.adx()
    trend_ok = adx > adx_min

    # Session-Filter
    if session_filter and df.index.tz is not None:
        active_hours = df.index.hour.isin(range(SESSION_START_H, SESSION_END_H))
    elif session_filter:
        active_hours = pd.Series(True, index=df.index)
        active_hours[:] = True
        try:
            active_hours = df.index.hour.isin(range(SESSION_START_H, SESSION_END_H))
        except AttributeError:
            pass
    else:
        active_hours = pd.Series(True, index=df.index)

    active_mask = pd.Series(active_hours, index=df.index)

    # Signale
    long_entries  = (close > donchian_high) & trend_ok & active_mask
    short_entries = (close < donchian_low)  & trend_ok & active_mask

    # SL/TP als Anteil des Kurses
    sl_stop = (sl_mult * atr / close).clip(0.0001, 0.10)
    tp_stop = (tp_mult * atr / close).clip(0.0001, 0.20)

    return long_entries, short_entries, sl_stop, tp_stop


def run(df: pd.DataFrame,
        channel_window: int = CHANNEL_WINDOW,
        atr_period: int = ATR_PERIOD,
        sl_mult: float = SL_MULT,
        tp_mult: float = TP_MULT,
        adx_min: float = ADX_MIN,
        session_filter: bool = True) -> vbt.Portfolio:
    """Führt den Backtest aus, gibt VBT-Portfolio zurück."""
    le, se, sl, tp = _signals(
        df, channel_window=channel_window, atr_period=atr_period,
        sl_mult=sl_mult, tp_mult=tp_mult, adx_min=adx_min,
        session_filter=session_filter,
    )
    return vbt.Portfolio.from_signals(
        df["close"],
        entries=le,
        exits=pd.Series(False, index=df.index),    # nur Hard-SL/TP, kein Cross-Exit
        short_entries=se,
        short_exits=pd.Series(False, index=df.index),
        sl_stop=sl,
        tp_stop=tp,
        fees=FEES,
        init_cash=INIT_CASH,
        direction="both",
    )


def tune(df: pd.DataFrame) -> pd.DataFrame:
    """Grid-Search: channel_window × sl_mult × adx_min.  Ziel: SQN ≥ 2.5."""
    from itertools import product
    from prop_firm_score import compute_metrics

    grid = {
        "channel_window": [15, 20, 25, 30],
        "sl_mult":        [1.5, 2.0, 2.5],
        "adx_min":        [15, 20, 25, 30],
    }
    results = []
    combos = list(product(*grid.values()))
    print(f"[S1 tune] {len(combos)} Kombinationen ...")

    for cw, slm, adx in combos:
        try:
            pf = run(df, channel_window=cw, sl_mult=slm, tp_mult=slm * 2.0,
                     adx_min=adx)
            m = compute_metrics(pf)
            results.append({
                "channel_window": cw, "sl_mult": slm, "tp_mult": slm * 2.0,
                "adx_min": adx, **m,
            })
        except Exception:
            continue

    return (pd.DataFrame(results)
            .sort_values("sqn", ascending=False)
            .reset_index(drop=True))


if __name__ == "__main__":
    print("Lade 6E/EURUSD H1 Daten ...")
    df = load_session("1h", start="2020-01-01", end="2024-06-01")
    print(f"  {len(df)} Bars geladen\n")

    pf = run(df)

    print("=" * 58)
    print("  STRATEGIE 1 – Donchian Breakout + ADX-Filter (H1)")
    print("=" * 58)
    print(pf.stats())
    print_prop_firm_report(pf, "S1 Donchian H1")

    print("\nTop-10 Parameter-Kombinationen (tune):")
    best = tune(df)
    cols = ["channel_window", "sl_mult", "adx_min",
            "sharpe", "max_dd_pct", "pf_factor", "win_rate", "sqn", "n_trades"]
    print(best[cols].head(10).to_string(index=False))
