"""Strategie 2: Multi-Timeframe Trend + RSI Pullback

Konzept:
  - H4: EMA-Crossover definiert übergeordnete Trendrichtung
  - M15: RSI-Pullback in Trendrichtung als Entry
  - Empfohlene Timeframes: M15 Entry / H4 Filter
"""
import vectorbt as vbt
import numpy as np
import pandas as pd
from config import SYMBOL, FEES, INIT_CASH
from prop_firm_score import print_prop_firm_report

RSI_OVERSOLD   = 35
RSI_OVERBOUGHT = 65


def run(data_h4, data_m15,
        ema_fast=20, ema_slow=50,
        rsi_os=RSI_OVERSOLD, rsi_ob=RSI_OVERBOUGHT,
        sl_mult=1.5, tp_mult=3.0):

    ema_f = data_h4.run("ema", ema_fast)
    ema_s = data_h4.run("ema", ema_slow)

    trend_up   = (ema_f.real > ema_s.real).resample("15min").ffill().reindex(data_m15.index, method="ffill")
    trend_down = (ema_f.real < ema_s.real).resample("15min").ffill().reindex(data_m15.index, method="ffill")

    rsi = data_m15.run("talib_func:rsi", timeperiod=14)
    atr = data_m15.run("talib_func:atr", timeperiod=14)

    long_entries  = trend_up   & (rsi.real < rsi_os)
    short_entries = trend_down & (rsi.real > rsi_ob)
    long_exits    = (rsi.real > 55) | short_entries
    short_exits   = (rsi.real < 45) | long_entries

    return vbt.PF.from_signals(
        data_m15,
        long_entries=long_entries,
        short_entries=short_entries,
        long_exits=long_exits,
        short_exits=short_exits,
        sl_stop=sl_mult * atr.real / data_m15.close,
        tp_stop=tp_mult * atr.real / data_m15.close,
        fees=FEES,
        init_cash=INIT_CASH,
        direction="both"
    )


def tune(data_h4, data_m15):
    """Grid Search über EMA-Perioden und RSI-Schwellwerte."""
    ema_fast_periods  = [10, 15, 20, 25]
    ema_slow_periods  = [40, 50, 60, 80]
    rsi_oversold_lvls = [30, 35, 40]
    rsi_ob_lvls       = [60, 65, 70]
    results = []

    for ef in ema_fast_periods:
        for es in ema_slow_periods:
            if ef >= es:
                continue
            for ov in rsi_oversold_lvls:
                for ob in rsi_ob_lvls:
                    pf = run(data_h4, data_m15, ema_fast=ef, ema_slow=es, rsi_os=ov, rsi_ob=ob)
                    results.append({
                        "ema_fast": ef, "ema_slow": es,
                        "rsi_os":   ov, "rsi_ob":   ob,
                        "sharpe":    pf.sharpe_ratio(),
                        "max_dd":    abs(pf.max_drawdown()),
                        "pf_factor": pf.trades.profit_factor(),
                        "trades":    pf.trades.count(),
                        "sqn":       pf.trades.sqn(),
                    })

    return pd.DataFrame(results).sort_values("sharpe", ascending=False)


if __name__ == "__main__":
    data_h4  = vbt.YFData.download(SYMBOL, period="max", interval="4h",  start="2020-01-01", end="2024-01-01")
    data_m15 = vbt.YFData.download(SYMBOL, period="max", interval="15m", start="2020-01-01", end="2024-01-01")
    pf = run(data_h4, data_m15)

    print("=" * 50)
    print("STRATEGIE 2: MTF Trend + RSI Pullback")
    print("=" * 50)
    print(pf.stats())
    print(f"\nSQN:           {pf.trades.sqn():.3f}")
    print(f"Profit Factor: {pf.trades.profit_factor():.3f}")
    print(f"Win Rate:      {pf.trades.win_rate() * 100:.1f}%")
    print_prop_firm_report(pf, "MTF RSI M15")
    pf.plot().show()
