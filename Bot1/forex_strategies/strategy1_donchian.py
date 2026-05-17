"""Strategie 1: Volatility Breakout (Donchian Channel)

Konzept:
  - Preis bricht über/unter das N-Perioden-Hoch/Tief → Trendfolge-Entry
  - Stop-Loss und Take-Profit ATR-basiert (RR 1:2)
  - Empfohlene Timeframes: H1, H4, Daily
"""
import vectorbt as vbt
import numpy as np
import pandas as pd
from config import SYMBOL, FEES, INIT_CASH
from prop_firm_score import print_prop_firm_report

ATR_MULT_SL = 2.0
ATR_MULT_TP = 4.0


def run(data, channel_window=20, atr_period=14, sl_mult=ATR_MULT_SL, tp_mult=ATR_MULT_TP):
    atr     = data.run("talib_func:atr", timeperiod=atr_period)
    high_n  = data.high.rolling(channel_window).max()
    low_n   = data.low.rolling(channel_window).min()

    long_entries  = data.close > high_n.shift(1)
    short_entries = data.close < low_n.shift(1)

    return vbt.PF.from_signals(
        data,
        long_entries=long_entries,
        short_entries=short_entries,
        long_exits=short_entries,
        short_exits=long_entries,
        sl_stop=sl_mult * atr.real / data.close,
        tp_stop=tp_mult * atr.real / data.close,
        fees=FEES,
        init_cash=INIT_CASH,
        direction="both"
    )


def tune(data):
    """Parameter-Scan über channel_window und atr_mult_sl."""
    channel_windows = np.arange(10, 50, 5)
    atr_mults_sl    = [1.5, 2.0, 2.5, 3.0]
    results = []

    for window in channel_windows:
        for atr_m in atr_mults_sl:
            pf = run(data, channel_window=window, sl_mult=atr_m, tp_mult=atr_m * 2)
            results.append({
                "window":    window,
                "atr_mult":  atr_m,
                "sharpe":    pf.sharpe_ratio(),
                "max_dd":    pf.max_drawdown(),
                "pf_factor": pf.trades.profit_factor(),
                "trades":    pf.trades.count(),
                "sqn":       pf.trades.sqn(),
            })

    return pd.DataFrame(results).sort_values("sharpe", ascending=False)


if __name__ == "__main__":
    data = vbt.YFData.download(SYMBOL, period="max", interval="1h", start="2020-01-01", end="2024-01-01")
    pf   = run(data)

    print("=" * 50)
    print("STRATEGIE 1: Volatility Breakout (Donchian)")
    print("=" * 50)
    print(pf.stats())
    print(f"\nSQN:           {pf.trades.sqn():.3f}")
    print(f"Profit Factor: {pf.trades.profit_factor():.3f}")
    print(f"Win Rate:      {pf.trades.win_rate() * 100:.1f}%")
    print_prop_firm_report(pf, "Donchian H1")
    pf.plot().show()
