"""Strategie 3: Composite Score Optimizer

Vollständiger Optimierungs-Workflow für Prop-Firm-Ziele.
Disqualifiziert Parametersätze die Prop-Firm-Regeln verletzen (DD > 8%).
"""
import vectorbt as vbt
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from itertools import product
from config import SYMBOL, FEES, INIT_CASH
from prop_firm_score import prop_firm_score

PARAM_GRID = {
    "fast_ema":   [8, 10, 15, 20, 25],
    "slow_ema":   [30, 40, 50, 60, 80],
    "atr_period": [10, 14, 20],
    "sl_mult":    [1.5, 2.0, 2.5],
    "rr_ratio":   [2.0, 2.5, 3.0],
}


def _run_single(data, fast, slow, atr_p, sl_m, rr):
    ema_f = data.run("ema", fast)
    ema_s = data.run("ema", slow)
    atr   = data.run("talib_func:atr", timeperiod=atr_p)
    le    = ema_f.real.vbt.crossed_above(ema_s.real)
    se    = ema_f.real.vbt.crossed_below(ema_s.real)
    return vbt.PF.from_signals(
        data, le, se, se, le,
        sl_stop=sl_m * atr.real / data.close,
        tp_stop=sl_m * rr * atr.real / data.close,
        fees=FEES, init_cash=INIT_CASH, direction="both"
    )


def optimize(data, param_grid=None) -> pd.DataFrame:
    if param_grid is None:
        param_grid = PARAM_GRID

    combos = list(product(
        param_grid["fast_ema"],
        param_grid["slow_ema"],
        param_grid["atr_period"],
        param_grid["sl_mult"],
        param_grid["rr_ratio"],
    ))
    print(f"Teste {len(combos)} Parameterkombinationen...")

    results = []
    for fast, slow, atr_p, sl_m, rr in combos:
        if fast >= slow:
            continue
        try:
            pf    = _run_single(data, fast, slow, atr_p, sl_m, rr)
            score = prop_firm_score(pf)
            results.append({
                "fast_ema":   fast,  "slow_ema":   slow,
                "atr_period": atr_p, "sl_mult":    sl_m,  "rr_ratio":  rr,
                "score":      score,
                "sharpe":     round(pf.sharpe_ratio(),          3),
                "max_dd":     round(abs(pf.max_drawdown()) * 100, 2),
                "pf_factor":  round(pf.trades.profit_factor(),  3),
                "sqn":        round(pf.trades.sqn(),            3),
                "win_rate":   round(pf.trades.win_rate() * 100, 1),
                "trades":     pf.trades.count(),
                "total_ret":  round(pf.total_return() * 100,    2),
            })
        except Exception:
            continue

    df = pd.DataFrame(results)
    print(f"Gültige Kombinationen: {(df['score'] > 0).sum()} / {len(df)}")
    return df.sort_values("score", ascending=False)


def plot_results(df: pd.DataFrame, save_path="optimizer_results.png"):
    df_valid = df[df["score"] > 0]
    pivot    = df_valid.pivot_table(values="score", index="fast_ema", columns="slow_ema", aggfunc="max")

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    im0 = axes[0].imshow(pivot, aspect="auto", cmap="RdYlGn")
    axes[0].set_title("Composite Score")
    axes[0].set_xlabel("Slow EMA")
    axes[0].set_ylabel("Fast EMA")
    plt.colorbar(im0, ax=axes[0])

    axes[1].scatter(df_valid["max_dd"], df_valid["sharpe"],
                    c=df_valid["score"], cmap="RdYlGn", alpha=0.6)
    axes[1].set_xlabel("Max Drawdown [%]")
    axes[1].set_ylabel("Sharpe Ratio")
    axes[1].set_title("Sharpe vs. Drawdown")
    axes[1].axvline(x=8, color="red", linestyle="--", label="DD-Limit 8%")

    axes[2].hist(df_valid["score"], bins=30, color="steelblue", edgecolor="white")
    axes[2].set_xlabel("Composite Score")
    axes[2].set_title("Score-Verteilung")

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.show()
    print(f"Gespeichert: {save_path}")


if __name__ == "__main__":
    data = vbt.YFData.download(SYMBOL, period="max", interval="4h", start="2019-01-01", end="2023-01-01")
    df   = optimize(data)

    print("\nTop 10 Parametersätze:")
    print(df.head(10).to_string(index=False))

    best = df.iloc[0].to_dict()
    print(f"\nBeste Parameter: {best}")

    plot_results(df)
