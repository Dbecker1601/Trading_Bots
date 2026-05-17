"""Walk-Forward Validation

Testet ob optimierte Parameter auf ungesehenen Daten (OOS) funktionieren.

Timeline:
  |─── Train 1 ───|─ Test 1 ─|
          |─── Train 2 ───|─ Test 2 ─|
                  |─── Train 3 ───|─ Test 3 ─|
"""
import vectorbt as vbt
import numpy as np
import pandas as pd
from config import SYMBOL, FEES, INIT_CASH

# Beste Parameter aus Optimizer eintragen
BEST_FAST    = 15
BEST_SLOW    = 50
BEST_ATR_P   = 14
BEST_SL_MULT = 2.0
BEST_RR      = 2.5


def _run_strategy(data, fast, slow, atr_p, sl_m, rr):
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


def run(data_full,
        fast=BEST_FAST, slow=BEST_SLOW, atr_p=BEST_ATR_P,
        sl_m=BEST_SL_MULT, rr=BEST_RR,
        train_pct=0.70, test_pct=0.15, step_pct=0.10) -> pd.DataFrame:

    n_bars     = len(data_full.index)
    train_size = int(n_bars * train_pct)
    test_size  = int(n_bars * test_pct)
    step_size  = int(n_bars * step_pct)

    results   = []
    split_idx = 0
    start     = 0

    print("Walk-Forward Validation:")
    print("-" * 60)

    while start + train_size + test_size <= n_bars:
        train_end  = start + train_size
        test_end   = train_end + test_size
        test_data  = data_full.iloc[train_end:test_end]

        pf = _run_strategy(test_data, fast, slow, atr_p, sl_m, rr)

        row = {
            "split":      split_idx,
            "train_from": data_full.index[start].date(),
            "train_to":   data_full.index[train_end - 1].date(),
            "test_from":  data_full.index[train_end].date(),
            "test_to":    data_full.index[test_end - 1].date(),
            "oos_sharpe": round(pf.sharpe_ratio(),          3),
            "oos_ret":    round(pf.total_return() * 100,    2),
            "oos_dd":     round(abs(pf.max_drawdown()) * 100, 2),
            "oos_trades": pf.trades.count(),
            "oos_pf":     round(pf.trades.profit_factor(),  3),
        }
        results.append(row)
        print(f"Split {split_idx}: OOS Sharpe={row['oos_sharpe']:.3f} | "
              f"Return={row['oos_ret']:.1f}% | DD={row['oos_dd']:.1f}%")

        start     += step_size
        split_idx += 1

    df = pd.DataFrame(results)

    print("\n" + "=" * 60)
    print("Walk-Forward Zusammenfassung:")
    print(df.to_string(index=False))
    print(f"\n  OOS Sharpe:        {df['oos_sharpe'].mean():.3f} ± {df['oos_sharpe'].std():.3f}")
    print(f"  OOS Return:        {df['oos_ret'].mean():.1f}%")
    print(f"  OOS DD:            {df['oos_dd'].mean():.1f}%")
    print(f"  Profitable Splits: {(df['oos_ret'] > 0).sum()} / {len(df)}")

    profitable_ratio = (df["oos_ret"] > 0).mean()
    avg_oos_sharpe   = df["oos_sharpe"].mean()

    if profitable_ratio >= 0.6 and avg_oos_sharpe >= 0.5:
        print("\n✅ Strategie besteht Walk-Forward Validierung!")
        print("   → Geeignet für Prop-Firm Challenge")
    else:
        print("\n❌ Strategie besteht Walk-Forward NICHT.")
        print("   → Parameter anpassen oder andere Strategie wählen")

    return df


if __name__ == "__main__":
    data_full = vbt.YFData.download(SYMBOL, period="max", interval="4h", start="2018-01-01", end="2024-01-01")
    run(data_full)
