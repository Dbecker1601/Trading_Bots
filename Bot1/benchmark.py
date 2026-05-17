"""Benchmark all 3 strategies across timeframes for EURUSD."""
import vectorbt as vbt
import numpy as np
import pandas as pd
import os
import sys

# Suppress plots
import matplotlib
matplotlib.use("Agg")

sys.path.insert(0, "/app/forex_strategies")
from config import SYMBOL, FEES, INIT_CASH
from prop_firm_score import prop_firm_score

# Strategy 1 imports
from strategy1_donchian import run as run_s1, tune as tune_s1
# Strategy 2 imports
from strategy2_mtf_rsi import run as run_s2, tune as tune_s2
# Strategy 3 imports
from strategy3_optimizer import _run_single as run_s3, optimize as optimize_s3

# Helper to fetch data
def fetch(tf, start, end):
    return vbt.YFData.download(SYMBOL, period="max", interval=tf, start=start, end=end)

print("=" * 70)
print("STRATEGY 1: Donchian Breakout")
print("=" * 70)

results = []

for tf in ["1h", "4h", "1d"]:
    print(f"\n--- Timeframe: {tf} ---")
    try:
        data = fetch(tf, "2020-01-01", "2024-01-01")
        pf = run_s1(data)
        row = {
            "strategy": "S1_Donchian",
            "timeframe": tf,
            "sharpe": pf.sharpe_ratio(),
            "max_dd": abs(pf.max_drawdown()),
            "pf_factor": pf.trades.profit_factor(),
            "win_rate": pf.trades.win_rate(),
            "sqn": pf.trades.sqn(),
            "trades": pf.trades.count(),
            "total_ret": pf.total_return(),
            "score": prop_firm_score(pf),
        }
        results.append(row)
        print(f"  Sharpe={row['sharpe']:.3f} | DD={row['max_dd']*100:.1f}% | PF={row['pf_factor']:.3f} | SQN={row['sqn']:.3f} | Trades={row['trades']} | Score={row['score']:.3f}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("STRATEGY 2: MTF Trend + RSI Pullback")
print("=" * 70)

for entry_tf in ["15m", "1h"]:
    filter_tf = "4h" if entry_tf == "15m" else "1d"
    print(f"\n--- Entry: {entry_tf} | Filter: {filter_tf} ---")
    try:
        data_filter = fetch(filter_tf, "2020-01-01", "2024-01-01")
        data_entry = fetch(entry_tf, "2020-01-01", "2024-01-01")
        pf = run_s2(data_filter, data_entry)
        row = {
            "strategy": "S2_MTF_RSI",
            "timeframe": f"{entry_tf}/{filter_tf}",
            "sharpe": pf.sharpe_ratio(),
            "max_dd": abs(pf.max_drawdown()),
            "pf_factor": pf.trades.profit_factor(),
            "win_rate": pf.trades.win_rate(),
            "sqn": pf.trades.sqn(),
            "trades": pf.trades.count(),
            "total_ret": pf.total_return(),
            "score": prop_firm_score(pf),
        }
        results.append(row)
        print(f"  Sharpe={row['sharpe']:.3f} | DD={row['max_dd']*100:.1f}% | PF={row['pf_factor']:.3f} | SQN={row['sqn']:.3f} | Trades={row['trades']} | Score={row['score']:.3f}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("STRATEGY 3: EMA Cross Optimizer")
print("=" * 70)

for tf in ["4h", "1d"]:
    print(f"\n--- Timeframe: {tf} ---")
    try:
        data = fetch(tf, "2019-01-01", "2023-01-01")
        df_opt = optimize_s3(data)
        if len(df_opt) == 0:
            print("  No valid parameter combinations.")
            continue
        best = df_opt.iloc[0]
        # Re-run best on full period to get proper metrics
        pf = run_s3(data, best["fast_ema"], best["slow_ema"], best["atr_period"], best["sl_mult"], best["rr_ratio"])
        row = {
            "strategy": "S3_EMA_Cross",
            "timeframe": tf,
            "sharpe": pf.sharpe_ratio(),
            "max_dd": abs(pf.max_drawdown()),
            "pf_factor": pf.trades.profit_factor(),
            "win_rate": pf.trades.win_rate(),
            "sqn": pf.trades.sqn(),
            "trades": pf.trades.count(),
            "total_ret": pf.total_return(),
            "score": best["score"],
            "best_params": f"fast={best['fast_ema']} slow={best['slow_ema']} atr={best['atr_period']} sl={best['sl_mult']} rr={best['rr_ratio']}",
        }
        results.append(row)
        print(f"  Sharpe={row['sharpe']:.3f} | DD={row['max_dd']*100:.1f}% | PF={row['pf_factor']:.3f} | SQN={row['sqn']:.3f} | Trades={row['trades']} | Score={row['score']:.3f}")
        print(f"  Best params: {row['best_params']}")
    except Exception as e:
        import traceback
        print(f"  ERROR: {e}")
        traceback.print_exc()

df_results = pd.DataFrame(results)
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(df_results.to_string(index=False))

# Save
os.makedirs("/app/logs", exist_ok=True)
df_results.to_csv("/app/logs/benchmark_results.csv", index=False)
print("\nSaved to /app/logs/benchmark_results.csv")
