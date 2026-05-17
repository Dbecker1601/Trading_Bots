"""
Strategie 3 – Composite Score Optimizer  (verbessert für 6E / EUR/USD)

System: EMA-Crossover-Breakout mit ADX-Filter.
        Vollständiger Grid-Search auf Trainingsdaten (2020–2022).
        Composite Score gewichtet SQN am stärksten (40 %).

Neuerungen gegenüber v1:
  - ADX-Threshold als Optimierungsparameter
  - Session-Filter aktiv
  - Composite Score: SQN 40 % | Sharpe 30 % | Profit-Factor 20 % | DD-Score 10 %
  - Mindest-Trade-Zahl als harte Disqualifikation (≥ 80 Trades)
  - Max-DD-Limit auf 8 % (Prop-Firm-Standard)

SQN-Ziel: ≥ 3.0 für den besten Parametersatz
"""
from __future__ import annotations

from itertools import product
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import vectorbt as vbt
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange

from config import FEES, INIT_CASH, SESSION_START_H, SESSION_END_H
from databento_loader import load_session
from prop_firm_score import compute_metrics, prop_firm_score, print_prop_firm_report

# ── Parameter-Grid ────────────────────────────────────────────────────────────
PARAM_GRID: dict[str, list[Any]] = {
    "fast_ema":   [8, 10, 15, 20],
    "slow_ema":   [30, 40, 50, 60, 80],
    "atr_period": [10, 14, 20],
    "sl_mult":    [1.5, 2.0, 2.5],
    "rr_ratio":   [2.0, 2.5, 3.0],
    "adx_min":    [0, 15, 20, 25],    # 0 = kein ADX-Filter
}

MAX_DD_LIMIT = 0.08
MIN_TRADES   = 80


def _run_single(df: pd.DataFrame,
                fast: int, slow: int, atr_p: int,
                sl_m: float, rr: float,
                adx_min: float) -> vbt.Portfolio:
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    ema_f = EMAIndicator(close, window=fast).ema_indicator()
    ema_s = EMAIndicator(close, window=slow).ema_indicator()
    atr   = AverageTrueRange(high, low, close, window=atr_p).average_true_range()

    le = (ema_f > ema_s) & (ema_f.shift(1) <= ema_s.shift(1))   # EMA cross up
    se = (ema_f < ema_s) & (ema_f.shift(1) >= ema_s.shift(1))   # EMA cross down

    # ADX-Filter
    if adx_min > 0:
        adx = ADXIndicator(high, low, close, window=14).adx()
        le = le & (adx > adx_min)
        se = se & (adx > adx_min)

    # Session-Filter
    try:
        active = pd.Series(
            df.index.hour.isin(range(SESSION_START_H, SESSION_END_H)),
            index=df.index,
        )
        le = le & active
        se = se & active
    except AttributeError:
        pass

    sl_stop = (sl_m * atr / close).clip(0.0001, 0.10)
    tp_stop = (sl_m * rr * atr / close).clip(0.0001, 0.20)

    return vbt.Portfolio.from_signals(
        close,
        entries=le,
        exits=pd.Series(False, index=df.index),
        short_entries=se,
        short_exits=pd.Series(False, index=df.index),
        sl_stop=sl_stop,
        tp_stop=tp_stop,
        fees=FEES,
        init_cash=INIT_CASH,
        direction="both",
    )


def optimize(df: pd.DataFrame, param_grid: dict | None = None) -> pd.DataFrame:
    """Führt Grid-Search durch. Gibt DataFrame sortiert nach Composite Score zurück."""
    grid  = param_grid or PARAM_GRID
    combos = list(product(*grid.values()))
    keys   = list(grid.keys())
    valid  = [(c[0], c[1], c[2], c[3], c[4], c[5]) for c in combos
              if c[0] < c[1]]   # fast < slow
    print(f"Teste {len(valid)} Parameterkombinationen ...")

    results = []
    for fast, slow, atr_p, sl_m, rr, adx in valid:
        try:
            pf    = _run_single(df, fast, slow, atr_p, sl_m, rr, adx)
            score = prop_firm_score(pf,
                                    max_dd_limit=MAX_DD_LIMIT,
                                    min_trades=MIN_TRADES)
            m = compute_metrics(pf)
            results.append({
                "fast_ema":   fast,  "slow_ema":  slow,
                "atr_period": atr_p, "sl_mult":   sl_m,
                "rr_ratio":   rr,    "adx_min":   adx,
                "score":      score, **m,
            })
        except Exception:
            continue

    df_res = pd.DataFrame(results)
    n_valid = (df_res["score"] > 0).sum()
    print(f"Gültige Kombinationen (Score > 0): {n_valid} / {len(df_res)}")
    return df_res.sort_values("score", ascending=False).reset_index(drop=True)


def plot_results(df_res: pd.DataFrame,
                 save_path: str = "optimizer_results.png") -> None:
    df_v = df_res[df_res["score"] > 0].copy()
    if df_v.empty:
        print("Keine gültigen Ergebnisse zum Plotten.")
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # ── Heatmap: fast × slow EMA, bester Score ───────────────────────────────
    pivot = df_v.pivot_table(values="score",
                             index="fast_ema",
                             columns="slow_ema",
                             aggfunc="max")
    im0 = axes[0].imshow(pivot.values, aspect="auto", cmap="RdYlGn")
    axes[0].set_xticks(range(len(pivot.columns)))
    axes[0].set_xticklabels(pivot.columns)
    axes[0].set_yticks(range(len(pivot.index)))
    axes[0].set_yticklabels(pivot.index)
    axes[0].set_title("Max Composite Score")
    axes[0].set_xlabel("Slow EMA")
    axes[0].set_ylabel("Fast EMA")
    plt.colorbar(im0, ax=axes[0])

    # ── Scatter: Drawdown vs. Sharpe, Farbe = Score ───────────────────────────
    sc = axes[1].scatter(df_v["max_dd_pct"], df_v["sharpe"],
                         c=df_v["score"], cmap="RdYlGn", alpha=0.6)
    axes[1].axvline(x=MAX_DD_LIMIT * 100, color="red", linestyle="--",
                    label=f"DD-Limit {MAX_DD_LIMIT*100:.0f}%")
    axes[1].set_xlabel("Max Drawdown [%]")
    axes[1].set_ylabel("Sharpe Ratio")
    axes[1].set_title("Sharpe vs. Drawdown")
    axes[1].legend()
    plt.colorbar(sc, ax=axes[1])

    # ── SQN Histogramm ────────────────────────────────────────────────────────
    axes[2].hist(df_v["sqn"], bins=30, color="steelblue", edgecolor="white")
    axes[2].axvline(x=2.5, color="orange", linestyle="--", label="SQN 2.5 (gut)")
    axes[2].axvline(x=3.0, color="green",  linestyle="--", label="SQN 3.0 (exzellent)")
    axes[2].set_xlabel("SQN")
    axes[2].set_title("SQN-Verteilung")
    axes[2].legend()

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    print(f"Gespeichert: {save_path}")
    plt.show()


if __name__ == "__main__":
    # Train: 2020–2022  |  OOS: 2023–2024 (manuell in walk_forward.py)
    print("Lade Trainingsdaten 6E/EURUSD H4 (2020-01-01 – 2022-12-31) ...")
    df_train = load_session("4h", start="2020-01-01", end="2022-12-31")
    print(f"  {len(df_train)} H4-Bars\n")

    df_res = optimize(df_train)

    print("\nTop-10 Parametersätze:")
    cols = ["fast_ema", "slow_ema", "atr_period", "sl_mult", "rr_ratio", "adx_min",
            "score", "sharpe", "max_dd_pct", "pf_factor", "sqn", "n_trades"]
    print(df_res[cols].head(10).to_string(index=False))

    # Bester Parametersatz auf Testperiode 2023–2024
    if not df_res.empty and df_res.iloc[0]["score"] > 0:
        best = df_res.iloc[0]
        print(f"\nBeste Parameter: {best[list(PARAM_GRID.keys())].to_dict()}")

        print("\nOOS-Test (2023-01-01 – 2024-06-01):")
        df_oos = load_session("4h", start="2023-01-01", end="2024-06-01")
        pf_oos = _run_single(df_oos,
                             int(best["fast_ema"]),  int(best["slow_ema"]),
                             int(best["atr_period"]), best["sl_mult"],
                             best["rr_ratio"],        best["adx_min"])
        print_prop_firm_report(pf_oos, "S3 Optimizer OOS")

    plot_results(df_res)
