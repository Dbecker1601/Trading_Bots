import numpy as np


def prop_firm_score(pf, max_dd_limit=0.08, min_trades=100) -> float:
    """
    Composite Score optimiert für Prop-Firm Kriterien.

    Gewichtung:
        Sharpe Ratio    35%
        SQN             30%
        Profit Factor   20%
        DD-Penalty      15%

    Returns -999 bei Disqualifikation.
    """
    try:
        sharpe    = pf.sharpe_ratio()
        max_dd    = abs(pf.max_drawdown())
        pf_factor = pf.trades.profit_factor()
        n_trades  = pf.trades.count()
        sqn       = pf.trades.sqn()

        if not np.isfinite(sharpe):    return -999
        if not np.isfinite(pf_factor): return -999
        if max_dd > max_dd_limit:      return -999
        if n_trades < min_trades:      return -999

        dd_score = max(0.0, 1.0 - (max_dd / max_dd_limit))

        return round(
            sharpe    * 0.35 +
            sqn       * 0.30 +
            pf_factor * 0.20 +
            dd_score  * 0.15,
            4
        )
    except Exception:
        return -999


def print_prop_firm_report(pf, strategy_name="Strategie"):
    """Vollständiges Prop-Firm Bewertungs-Dashboard."""
    sharpe    = pf.sharpe_ratio()
    sortino   = pf.sortino_ratio()
    calmar    = pf.calmar_ratio()
    max_dd    = abs(pf.max_drawdown())
    total_ret = pf.total_return()
    pf_factor = pf.trades.profit_factor()
    win_rate  = pf.trades.win_rate()
    sqn       = pf.trades.sqn()
    n_trades  = pf.trades.count()

    max_dd_limit = 0.08
    min_trades   = 100

    dd_ok     = max_dd    <= max_dd_limit
    trades_ok = n_trades  >= min_trades
    pf_ok     = pf_factor >  1.4
    sharpe_ok = sharpe    >  1.0

    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  PROP-FIRM REPORT: {strategy_name}")
    print(sep)

    print(f"\n{'─'*30} Rendite {'─'*16}")
    print(f"  Total Return:      {total_ret * 100:>8.2f}%")
    print(f"  Sharpe Ratio:      {sharpe:>8.3f}   {'✅' if sharpe_ok else '❌ < 1.0'}")
    print(f"  Sortino Ratio:     {sortino:>8.3f}")
    print(f"  Calmar Ratio:      {calmar:>8.3f}")

    print(f"\n{'─'*30} Risiko {'─'*17}")
    print(f"  Max Drawdown:      {max_dd*100:>7.2f}%   {'✅' if dd_ok else '❌ LIMIT VERLETZT'}")
    print(f"  DD-Limit (Prop):   {max_dd_limit*100:>7.1f}%")

    print(f"\n{'─'*30} Trade-Qualität {'─'*9}")
    print(f"  Trades gesamt:     {n_trades:>8d}   {'✅' if trades_ok else '⚠️ Zu wenig'}")
    print(f"  Win Rate:          {win_rate*100:>7.1f}%")
    print(f"  Profit Factor:     {pf_factor:>8.3f}   {'✅' if pf_ok else '❌'}")
    print(f"  SQN:               {sqn:>8.3f}   {'✅' if sqn > 2.0 else '⚠️ '}")

    print(f"\n{'─'*30} Prop-Firm Eignung {'─'*6}")
    if all([dd_ok, trades_ok, pf_ok, sharpe_ok]):
        print("  ✅ GEEIGNET für Prop-Firm Challenge")
    else:
        print("  ❌ NICHT geeignet - folgende Kriterien verletzt:")
        if not dd_ok:     print(f"     → Drawdown {max_dd*100:.1f}% > Limit {max_dd_limit*100:.0f}%")
        if not trades_ok: print(f"     → Zu wenig Trades: {n_trades}")
        if not pf_ok:     print(f"     → Profit Factor < 1.4")
        if not sharpe_ok: print(f"     → Sharpe < 1.0")

    print(sep)
