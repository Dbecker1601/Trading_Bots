"""
Prop-Firm Scoring & Funding Assessment für Bot1 / 6E-Strategien.

Kernfunktionen:
  compute_metrics()      → alle KPIs aus einem VBT-Portfolio
  prop_firm_score()      → gewichteter Composite Score (Disqualifikation wenn DD > Limit)
  funding_probability()  → Monte-Carlo-Schätzung der Bestehenschance
  print_prop_firm_report()→ vollständiges Multi-Firm Dashboard
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt

from config import INIT_CASH, SQN_TIERS, PROP_FIRMS


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────

def _safe(fn, *args, default=float("nan"), **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def _win_rate(pf: vbt.Portfolio) -> float:
    try:
        return float(pf.trades.win_rate())
    except Exception:
        pass
    try:
        pnl = _trade_pnl(pf)
        return float((pnl > 0).mean()) if len(pnl) > 0 else 0.0
    except Exception:
        return float("nan")


def _profit_factor(pf: vbt.Portfolio) -> float:
    try:
        return float(pf.trades.profit_factor())
    except Exception:
        pass
    try:
        pnl = _trade_pnl(pf)
        wins   = pnl[pnl > 0].sum()
        losses = abs(pnl[pnl < 0].sum())
        return float(wins / losses) if losses > 0 else float("inf")
    except Exception:
        return float("nan")


def _trade_pnl(pf: vbt.Portfolio) -> pd.Series:
    """Gibt Trade-PnL als pandas Series zurück (vbt-versionsunabhängig)."""
    try:
        return pf.trades.pnl.to_pandas()
    except Exception:
        pass
    try:
        return pd.Series(pf.trades.records["pnl"])
    except Exception:
        pass
    try:
        rec = pf.trades.records_readable
        col = next((c for c in ("PnL", "pnl", "profit") if c in rec.columns), None)
        if col:
            return rec[col].reset_index(drop=True)
    except Exception:
        pass
    return pd.Series([], dtype=float)


def compute_sqn(pf: vbt.Portfolio, init_cash: float = INIT_CASH) -> float:
    """SQN (Van Tharp): sqrt(N) × mean(R) / std(R), wobei R = PnL / Kapital."""
    try:
        # VBT Pro hat sqn() direkt
        return float(pf.trades.sqn())
    except Exception:
        pass
    pnl = _trade_pnl(pf)
    n = len(pnl)
    if n < 2:
        return 0.0
    r = pnl / init_cash
    std_r = r.std()
    if std_r == 0:
        return 0.0
    return float(np.sqrt(n) * r.mean() / std_r)


def sqn_tier(sqn: float) -> str:
    """Klassifiziert SQN nach Van-Tharp-Stufen."""
    if sqn >= SQN_TIERS["superb"]:    return "SUPERB   (> 5.0)"
    if sqn >= SQN_TIERS["excellent"]: return "EXZELLENT (≥ 3.0)"
    if sqn >= SQN_TIERS["good"]:      return "GUT       (≥ 2.5)"
    if sqn >= SQN_TIERS["average"]:   return "DURCHSCHN.(≥ 2.0)"
    if sqn >= SQN_TIERS["poor"]:      return "SCHWACH   (≥ 1.6)"
    return                                    "SCHLECHT  (< 1.6)"


# ─────────────────────────────────────────────────────────────────────────────
# Haupt-Metriken
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(pf: vbt.Portfolio,
                    init_cash: float = INIT_CASH) -> dict:
    """Berechnet alle relevanten KPIs. Gibt Dict zurück (kompatibel mit Optimizer-DataFrame)."""
    sharpe    = _safe(pf.sharpe_ratio)
    sortino   = _safe(pf.sortino_ratio)
    calmar    = _safe(pf.calmar_ratio)
    max_dd    = abs(_safe(pf.max_drawdown, default=float("nan")))
    total_ret = _safe(pf.total_return)
    n_trades  = _safe(lambda: int(pf.trades.count()), default=0)
    win_rate  = _win_rate(pf)
    pf_factor = _profit_factor(pf)
    sqn       = compute_sqn(pf, init_cash)

    return {
        "sharpe":      round(sharpe,           3) if np.isfinite(sharpe)    else float("nan"),
        "sortino":     round(sortino,          3) if np.isfinite(sortino)   else float("nan"),
        "calmar":      round(calmar,           3) if np.isfinite(calmar)    else float("nan"),
        "max_dd_pct":  round(max_dd * 100,     2),
        "total_ret_pct": round(total_ret * 100, 2) if np.isfinite(total_ret) else float("nan"),
        "n_trades":    n_trades,
        "win_rate":    round(win_rate * 100,   1) if np.isfinite(win_rate)  else float("nan"),
        "pf_factor":   round(pf_factor,        3) if np.isfinite(pf_factor) else float("nan"),
        "sqn":         round(sqn,              3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Composite Score (Optimizer-Zielgröße)
# ─────────────────────────────────────────────────────────────────────────────

def prop_firm_score(pf: vbt.Portfolio,
                    max_dd_limit: float = 0.08,
                    min_trades: int = 80) -> float:
    """
    Gewichteter Composite Score optimiert für Prop-Firm-Ziele.

    Gewichtung:
        SQN             40 %   ← stärkster Einzelindikator für Systemqualität
        Sharpe Ratio    30 %
        Profit Factor   20 %
        DD-Score        10 %   ← Bonus je weiter unter dem DD-Limit

    Gibt -999 zurück wenn Disqualifikationskriterien verletzt werden.
    """
    m = compute_metrics(pf)
    sharpe    = m["sharpe"]
    max_dd    = m["max_dd_pct"] / 100
    pf_factor = m["pf_factor"]
    n_trades  = m["n_trades"]
    sqn       = m["sqn"]

    if not np.isfinite(sharpe):    return -999
    if not np.isfinite(pf_factor): return -999
    if max_dd > max_dd_limit:      return -999
    if n_trades < min_trades:      return -999
    if pf_factor < 1.0:            return -999

    dd_score = max(0.0, 1.0 - (max_dd / max_dd_limit))

    score = (
        sqn       * 0.40 +
        sharpe    * 0.30 +
        pf_factor * 0.20 +
        dd_score  * 0.10
    )
    return round(score, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Funding-Wahrscheinlichkeit (vereinfachte Monte-Carlo-Schätzung)
# ─────────────────────────────────────────────────────────────────────────────

def funding_probability(pf: vbt.Portfolio,
                        firm_key: str,
                        n_sim: int = 10_000,
                        seed: int = 42) -> float:
    """
    Schätzt P(Challenge bestehen) per Monte-Carlo.

    Modell:
      - Tagliche Returns werden als normal-verteilt angenommen (mean + std aus Backtest).
      - N Pfade à 30 Handelstage werden simuliert.
      - Erfolg = Profit-Target erreicht OHNE Max-Loss (und ohne Daily-Loss-Überschreitung).
    """
    if firm_key not in PROP_FIRMS:
        return float("nan")

    firm    = PROP_FIRMS[firm_key]
    target  = firm["profit_target_pct"] / 100
    max_los = firm["max_loss_pct"] / 100
    daily_l = firm["max_daily_loss_pct"] / 100
    days    = 30     # typische Challenge-Laufzeit

    # Tägliche Returns aus dem Portfolio
    try:
        daily_ret = pf.returns().resample("D").apply(lambda x: (1 + x).prod() - 1).dropna()
    except Exception:
        return float("nan")

    if len(daily_ret) < 20:
        return float("nan")

    mu  = daily_ret.mean()
    sig = daily_ret.std()

    rng  = np.random.default_rng(seed)
    sims = rng.normal(mu, sig, (n_sim, days))    # (n_sim, 30)

    cum_ret    = np.cumprod(1 + sims, axis=1) - 1   # kumulativer Return
    cum_drawdown = cum_ret - np.maximum.accumulate(cum_ret, axis=1)   # DD relativ zum Peak

    # Erfolg: Pfad erreicht target UND bleibt über -max_los UND kein Tag > -daily_l
    hit_target   = cum_ret.max(axis=1) >= target
    stay_safe    = cum_ret.min(axis=1)  > -max_los
    daily_ok     = (daily_l == 0) or (sims.min(axis=1) > -daily_l)

    p_pass = float((hit_target & stay_safe & daily_ok).mean())
    return round(p_pass, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard-Ausgabe
# ─────────────────────────────────────────────────────────────────────────────

def print_prop_firm_report(pf: vbt.Portfolio,
                           strategy_name: str = "Strategie") -> None:
    """Vollständiges Prop-Firm Dashboard mit Multi-Firm Assessment."""
    m    = compute_metrics(pf)
    sqn  = m["sqn"]
    sep  = "=" * 62

    print(f"\n{sep}")
    print(f"  PROP-FIRM REPORT: {strategy_name}")
    print(sep)

    # ── Rendite & Risiko ─────────────────────────────────────────────────────
    print(f"\n{'─'*28} Rendite & Risiko {'─'*14}")
    print(f"  Total Return:      {m['total_ret_pct']:>8.2f}%")
    print(f"  Sharpe Ratio:      {m['sharpe']:>8.3f}   {'✅' if m['sharpe'] >= 1.0 else '❌ < 1.0'}")
    print(f"  Sortino Ratio:     {m['sortino']:>8.3f}")
    print(f"  Calmar Ratio:      {m['calmar']:>8.3f}")
    print(f"  Max Drawdown:      {m['max_dd_pct']:>7.2f}%   {'✅' if m['max_dd_pct'] <= 8 else '❌ > 8%'}")

    # ── Trade-Qualität ───────────────────────────────────────────────────────
    print(f"\n{'─'*28} Trade-Qualität {'─'*17}")
    print(f"  Trades gesamt:     {m['n_trades']:>8d}   {'✅' if m['n_trades'] >= 80 else '⚠️  < 80'}")
    print(f"  Win Rate:          {m['win_rate']:>7.1f}%   {'✅' if m['win_rate'] >= 45 else '⚠️  < 45%'}")
    print(f"  Profit Factor:     {m['pf_factor']:>8.3f}   {'✅' if m['pf_factor'] >= 1.4 else '❌ < 1.4'}")

    # ── SQN ──────────────────────────────────────────────────────────────────
    print(f"\n{'─'*28} SQN (Van Tharp) {'─'*15}")
    print(f"  SQN:               {sqn:>8.3f}   {sqn_tier(sqn)}")
    print(f"  Composite Score:   {prop_firm_score(pf):>8.4f}")

    # ── Multi-Firm Funding-Assessment ────────────────────────────────────────
    print(f"\n{'─'*28} Funding-Assessment {'─'*13}")
    print(f"  {'Firma':<26} {'P(Bestehen)':<14} {'Max-DD OK':<12} {'Bewertung'}")
    print(f"  {'─'*26} {'─'*13} {'─'*11} {'─'*20}")

    for fk, firm in PROP_FIRMS.items():
        dd_ok   = m["max_dd_pct"] <= firm["max_loss_pct"]
        p_pass  = funding_probability(pf, fk)
        p_str   = f"{p_pass*100:.1f}%" if np.isfinite(p_pass) else "n/a"

        if not np.isfinite(p_pass):
            rating = "⚠️  Zu wenig Daten"
        elif p_pass >= 0.65 and dd_ok:
            rating = "✅ Empfohlen"
        elif p_pass >= 0.40 and dd_ok:
            rating = "🟡 Möglich"
        elif dd_ok:
            rating = "🟠 Grenzwertig"
        else:
            rating = "❌ DD-Limit verletzt"

        print(f"  {firm['label']:<26} {p_str:<14} {'✅' if dd_ok else '❌':<12} {rating}")

    print(sep)
