"""
Strategie 2 – Multi-Timeframe RSI Pullback  (verbessert für 6E / EUR/USD)

Ebenen:
  D1  → 200-EMA definiert den Makrotrend (Bias Long / Short)
  H4  → 20/50-EMA Crossover bestätigt übergeordnete Richtung
  H1  → RSI < 35 (Long) / RSI > 65 (Short) als Entry-Trigger
  H1  → MACD-Histogramm muss in Entry-Richtung drehen

Exits:
  - RSI kehrt in neutrale Zone zurück (> 55 für Longs / < 45 für Shorts)
  - Hard-SL: 1.5 × ATR
  - Hard-TP: 3.0 × ATR  (RR 1:2)

SQN-Ziel: ≥ 2.5  (höhere Win-Rate als S1 durch Alignment aller Timeframes)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange

from config import FEES, INIT_CASH, SESSION_START_H, SESSION_END_H
from databento_loader import load, load_session
from prop_firm_score import compute_metrics, print_prop_firm_report

# ── Default Parameters ────────────────────────────────────────────────────────
EMA_FAST_H4    = 20
EMA_SLOW_H4    = 50
EMA_D1_TREND   = 200
RSI_PERIOD_H1  = 14
RSI_OS         = 35     # Oversold → Long-Entry
RSI_OB         = 65     # Overbought → Short-Entry
RSI_EXIT_LONG  = 55     # Long-Exit
RSI_EXIT_SHORT = 45     # Short-Exit
ATR_PERIOD     = 14
SL_MULT        = 1.5
TP_MULT        = 3.0


def _build_h4_trend(df_h4: pd.DataFrame,
                    ema_fast: int = EMA_FAST_H4,
                    ema_slow: int = EMA_SLOW_H4) -> pd.Series:
    """Gibt +1 (Aufwärtstrend), -1 (Abwärtstrend) auf H4-Basis zurück."""
    fast = EMAIndicator(df_h4["close"], window=ema_fast).ema_indicator()
    slow = EMAIndicator(df_h4["close"], window=ema_slow).ema_indicator()
    trend = pd.Series(0, index=df_h4.index, dtype=int)
    trend[fast > slow] = 1
    trend[fast < slow] = -1
    return trend


def _align_to_h1(series_h4: pd.Series, index_h1: pd.Index) -> pd.Series:
    """Forward-filled Reindex von H4 auf H1 (Session-gefiltert oder vollständig)."""
    return (series_h4
            .reindex(index_h1, method="ffill")
            .fillna(0))


def run(df_h1: pd.DataFrame,
        df_h4: pd.DataFrame,
        df_d1: pd.DataFrame,
        ema_fast: int = EMA_FAST_H4,
        ema_slow: int = EMA_SLOW_H4,
        rsi_os: float = RSI_OS,
        rsi_ob: float = RSI_OB,
        sl_mult: float = SL_MULT,
        tp_mult: float = TP_MULT) -> vbt.Portfolio:
    """Führt den Backtest aus."""
    close_h1 = df_h1["close"]
    high_h1  = df_h1["high"]
    low_h1   = df_h1["low"]

    # ── H1 Indikatoren ───────────────────────────────────────────────────────
    rsi = RSIIndicator(close_h1, window=RSI_PERIOD_H1).rsi()
    atr = AverageTrueRange(high_h1, low_h1, close_h1, window=ATR_PERIOD).average_true_range()
    macd_ind = MACD(close_h1)
    macd_hist = macd_ind.macd_diff()          # Histogramm: positiv = bullish momentum

    # ── H4 Trend → auf H1 alignen ────────────────────────────────────────────
    h4_trend = _build_h4_trend(df_h4, ema_fast, ema_slow)
    trend_h4 = _align_to_h1(h4_trend, df_h1.index)

    # ── D1 Makrotrend (200-EMA) → auf H1 alignen ─────────────────────────────
    ema200_d1 = EMAIndicator(df_d1["close"], window=EMA_D1_TREND).ema_indicator()
    d1_bias   = (df_d1["close"] > ema200_d1).astype(int)          # 1 = Long-Bias, 0 = Short-Bias
    d1_bias_h1 = _align_to_h1(d1_bias.astype(float), df_h1.index)

    # ── Session-Filter (07–17 UTC) ────────────────────────────────────────────
    try:
        active = pd.Series(
            df_h1.index.hour.isin(range(SESSION_START_H, SESSION_END_H)),
            index=df_h1.index,
        )
    except AttributeError:
        active = pd.Series(True, index=df_h1.index)

    # ── Entry-Signale ─────────────────────────────────────────────────────────
    # Long:  D1 Long-Bias  AND H4 Aufwärtstrend  AND H1 RSI oversold  AND MACD Hist dreht hoch
    long_entries = (
        (d1_bias_h1 > 0.5) &
        (trend_h4 > 0) &
        (rsi < rsi_os) &
        (macd_hist > macd_hist.shift(1)) &   # Momentum dreht aufwärts
        active
    )
    # Short: D1 Short-Bias AND H4 Abwärtstrend  AND H1 RSI overbought AND MACD Hist dreht runter
    short_entries = (
        (d1_bias_h1 < 0.5) &
        (trend_h4 < 0) &
        (rsi > rsi_ob) &
        (macd_hist < macd_hist.shift(1)) &   # Momentum dreht abwärts
        active
    )

    # ── Exit-Signale (RSI-basiert, zusätzlich zu Hard-SL/TP) ─────────────────
    long_exits  = rsi > RSI_EXIT_LONG
    short_exits = rsi < RSI_EXIT_SHORT

    # ── SL / TP ──────────────────────────────────────────────────────────────
    sl_stop = (sl_mult * atr / close_h1).clip(0.0001, 0.10)
    tp_stop = (tp_mult * atr / close_h1).clip(0.0001, 0.20)

    return vbt.Portfolio.from_signals(
        close_h1,
        entries=long_entries,
        exits=long_exits,
        short_entries=short_entries,
        short_exits=short_exits,
        sl_stop=sl_stop,
        tp_stop=tp_stop,
        fees=FEES,
        init_cash=INIT_CASH,
        direction="both",
    )


def tune(df_h1: pd.DataFrame,
         df_h4: pd.DataFrame,
         df_d1: pd.DataFrame) -> pd.DataFrame:
    """Grid-Search über EMA-Perioden × RSI-Schwellwerte × SL-Multiplikator."""
    from itertools import product
    from prop_firm_score import compute_metrics

    grid = {
        "ema_fast": [15, 20, 25],
        "ema_slow": [40, 50, 60],
        "rsi_os":   [30, 35],
        "rsi_ob":   [65, 70],
        "sl_mult":  [1.5, 2.0],
    }
    results = []
    combos = list(product(*grid.values()))
    print(f"[S2 tune] {len(combos)} Kombinationen ...")

    for ef, es, os_, ob, slm in combos:
        if ef >= es:
            continue
        try:
            pf = run(df_h1, df_h4, df_d1,
                     ema_fast=ef, ema_slow=es,
                     rsi_os=os_, rsi_ob=ob,
                     sl_mult=slm, tp_mult=slm * 2.0)
            m = compute_metrics(pf)
            results.append({
                "ema_fast": ef, "ema_slow": es,
                "rsi_os": os_, "rsi_ob": ob, "sl_mult": slm,
                **m,
            })
        except Exception:
            continue

    return (pd.DataFrame(results)
            .sort_values("sqn", ascending=False)
            .reset_index(drop=True))


if __name__ == "__main__":
    print("Lade Daten (H1 / H4 / D1) ...")
    df_h1 = load_session("1h", start="2020-01-01", end="2024-06-01")
    df_h4 = load("4h",  start="2019-06-01", end="2024-06-01")   # etwas mehr History für EMA200
    df_d1 = load("1d",  start="2018-01-01", end="2024-06-01")   # D1 für 200-EMA braucht 200 Tage Anlauf
    print(f"  H1: {len(df_h1)} Bars | H4: {len(df_h4)} Bars | D1: {len(df_d1)} Bars\n")

    pf = run(df_h1, df_h4, df_d1)

    print("=" * 58)
    print("  STRATEGIE 2 – MTF RSI + MACD + D1-Trend (H1/H4/D1)")
    print("=" * 58)
    print(pf.stats())
    print_prop_firm_report(pf, "S2 MTF RSI")

    print("\nTop-10 Parameter-Kombinationen (tune):")
    best = tune(df_h1, df_h4, df_d1)
    cols = ["ema_fast", "ema_slow", "rsi_os", "rsi_ob", "sl_mult",
            "sharpe", "max_dd_pct", "pf_factor", "win_rate", "sqn", "n_trades"]
    print(best[cols].head(10).to_string(index=False))
