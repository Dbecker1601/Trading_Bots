"""
Walk-Forward Validation für Bot1 – 6E / EUR/USD Strategien.

Echtes WFA-Schema:
  1. Trainingsperiode → strategy3_optimizer.optimize() findet beste Parameter
  2. OOS-Testperiode  → bester Parametersatz wird unverändert getestet
  3. Fenster rücken um step_pct vor

Auswertung:
  - OOS-Sharpe, -SQN, -Return, -Drawdown pro Fenster
  - Profitable Splits ≥ 60 %  AND  Ø OOS-SQN ≥ 2.0  → bestanden
  - Funding-Assessment auf gepoolten OOS-Trades
"""
from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd
import vectorbt as vbt

from config import FEES, INIT_CASH, PROP_FIRMS
from databento_loader import load_session
from prop_firm_score import compute_metrics, print_prop_firm_report
from strategy3_optimizer import PARAM_GRID, _run_single, optimize

warnings.filterwarnings("ignore")

# ── WFA-Konfiguration ─────────────────────────────────────────────────────────
TRAIN_PCT = 0.65     # 65 % Training
TEST_PCT  = 0.20     # 20 % OOS-Test
STEP_PCT  = 0.15     # 15 % Step (Überlappung = 0 wenn TRAIN+TEST+STEP = 1.0)

# Mindestanforderungen für bestandene Validierung
MIN_PROFITABLE_SPLITS_PCT = 0.60
MIN_OOS_SQN               = 2.0


def _oos_portfolio(df_oos: pd.DataFrame, params: dict) -> Optional[vbt.Portfolio]:
    """Führt _run_single mit params-Dict aus. None bei Fehler."""
    try:
        return _run_single(
            df_oos,
            fast    = int(params["fast_ema"]),
            slow    = int(params["slow_ema"]),
            atr_p   = int(params["atr_period"]),
            sl_m    = float(params["sl_mult"]),
            rr      = float(params["rr_ratio"]),
            adx_min = float(params["adx_min"]),
        )
    except Exception:
        return None


def run(df_full: pd.DataFrame,
        train_pct: float = TRAIN_PCT,
        test_pct: float  = TEST_PCT,
        step_pct: float  = STEP_PCT,
        param_grid: dict | None = None) -> pd.DataFrame:
    """
    Vollständiger Walk-Forward Validation Run.

    Parameter
    ---------
    df_full     : kompletter Datensatz (H4 empfohlen)
    param_grid  : Grid für strategy3_optimizer.optimize() – None = PARAM_GRID
    """
    n          = len(df_full)
    train_size = int(n * train_pct)
    test_size  = int(n * test_pct)
    step_size  = int(n * step_pct)

    if train_size + test_size > n:
        raise ValueError("Datensatz zu kurz für gewählte WFA-Aufteilung.")

    results    = []
    split_idx  = 0
    start      = 0

    print("Walk-Forward Validation – 6E / EUR/USD")
    print("=" * 70)
    print(f"  Gesamt-Bars: {n} | Train: {train_pct*100:.0f}% | OOS: {test_pct*100:.0f}% | Step: {step_pct*100:.0f}%")
    print("-" * 70)

    while start + train_size + test_size <= n:
        train_end  = start + train_size
        test_end   = train_end + test_size
        df_train   = df_full.iloc[start:train_end]
        df_oos     = df_full.iloc[train_end:test_end]

        train_from = df_full.index[start]
        train_to   = df_full.index[train_end - 1]
        oos_from   = df_full.index[train_end]
        oos_to     = df_full.index[test_end - 1]

        print(f"\nSplit {split_idx}: Train [{train_from.date()} → {train_to.date()}]"
              f"  OOS [{oos_from.date()} → {oos_to.date()}]")

        # Optimierung auf Trainingsdaten
        try:
            df_opt = optimize(df_train, param_grid=param_grid or PARAM_GRID)
        except Exception as e:
            print(f"  ⚠️  Optimierung fehlgeschlagen: {e}")
            start += step_size
            split_idx += 1
            continue

        valid = df_opt[df_opt["score"] > 0]
        if valid.empty:
            print("  ⚠️  Kein gültiger Parametersatz gefunden.")
            start += step_size
            split_idx += 1
            continue

        best_params = valid.iloc[0].to_dict()
        print(f"  Beste Parameter (Train): "
              f"fast={int(best_params['fast_ema'])}  slow={int(best_params['slow_ema'])}  "
              f"adx={best_params['adx_min']}  sl={best_params['sl_mult']:.1f}  "
              f"rr={best_params['rr_ratio']:.1f}")

        # OOS-Test
        pf_oos = _oos_portfolio(df_oos, best_params)
        if pf_oos is None:
            print("  ⚠️  OOS-Portfolio konnte nicht erstellt werden.")
            start += step_size
            split_idx += 1
            continue

        m = compute_metrics(pf_oos)
        print(f"  OOS: Sharpe={m['sharpe']:.3f} | SQN={m['sqn']:.3f} | "
              f"Return={m['total_ret_pct']:.1f}% | DD={m['max_dd_pct']:.1f}% | "
              f"Trades={m['n_trades']}")

        results.append({
            "split":           split_idx,
            "train_from":      train_from.date(),
            "train_to":        train_to.date(),
            "oos_from":        oos_from.date(),
            "oos_to":          oos_to.date(),
            "best_fast":       int(best_params["fast_ema"]),
            "best_slow":       int(best_params["slow_ema"]),
            "best_adx":        best_params["adx_min"],
            "best_sl":         best_params["sl_mult"],
            "best_rr":         best_params["rr_ratio"],
            "train_score":     round(best_params["score"], 4),
            "oos_sharpe":      m["sharpe"],
            "oos_sqn":         m["sqn"],
            "oos_ret_pct":     m["total_ret_pct"],
            "oos_dd_pct":      m["max_dd_pct"],
            "oos_pf":          m["pf_factor"],
            "oos_win_rate":    m["win_rate"],
            "oos_trades":      m["n_trades"],
        })

        start     += step_size
        split_idx += 1

    if not results:
        print("\n❌ Keine OOS-Ergebnisse verfügbar.")
        return pd.DataFrame()

    df_res = pd.DataFrame(results)

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    n_splits      = len(df_res)
    n_profitable  = (df_res["oos_ret_pct"] > 0).sum()
    profitable_r  = n_profitable / n_splits
    avg_oos_sqn   = df_res["oos_sqn"].mean()
    avg_oos_sharpe= df_res["oos_sharpe"].mean()
    avg_oos_dd    = df_res["oos_dd_pct"].mean()

    print("\n" + "=" * 70)
    print("Walk-Forward Zusammenfassung:")
    print("-" * 70)
    display_cols = ["split", "oos_from", "oos_to", "oos_sharpe",
                    "oos_sqn", "oos_ret_pct", "oos_dd_pct", "oos_trades"]
    print(df_res[display_cols].to_string(index=False))
    print("-" * 70)
    print(f"  Profitable Splits:   {n_profitable}/{n_splits}  ({profitable_r*100:.1f}%)"
          f"   {'✅' if profitable_r >= MIN_PROFITABLE_SPLITS_PCT else '❌'}")
    print(f"  Ø OOS Sharpe:        {avg_oos_sharpe:.3f}")
    print(f"  Ø OOS SQN:           {avg_oos_sqn:.3f}"
          f"   {'✅' if avg_oos_sqn >= MIN_OOS_SQN else '❌ < 2.0'}")
    print(f"  Ø OOS Drawdown:      {avg_oos_dd:.1f}%")

    passed = profitable_r >= MIN_PROFITABLE_SPLITS_PCT and avg_oos_sqn >= MIN_OOS_SQN
    print()
    if passed:
        print("  ✅ Strategie BESTEHT Walk-Forward Validierung!")
        print("     → Geeignet für Prop-Firm Challenge")

        # Funding-Bewertung auf Basis der OOS-Metriken
        print(f"\n  Funding-Empfehlung (basierend auf Ø OOS-Metriken):")
        for fk, firm in PROP_FIRMS.items():
            dd_ok = avg_oos_dd <= firm["max_loss_pct"]
            if dd_ok and avg_oos_sqn >= 2.0:
                print(f"     ✅ {firm['label']}")
            elif dd_ok:
                print(f"     🟡 {firm['label']} (SQN grenzwertig)")
            else:
                print(f"     ❌ {firm['label']} (DD-Limit verletzt)")
    else:
        print("  ❌ Strategie besteht Walk-Forward NICHT.")
        if profitable_r < MIN_PROFITABLE_SPLITS_PCT:
            print(f"     → Nur {n_profitable}/{n_splits} Splits profitabel (Ziel ≥ 60 %)")
        if avg_oos_sqn < MIN_OOS_SQN:
            print(f"     → Ø OOS-SQN {avg_oos_sqn:.3f} < {MIN_OOS_SQN}")
        print("     → Parameter verfeinern oder anderen Timeframe testen")

    print("=" * 70)
    return df_res


if __name__ == "__main__":
    print("Lade 6E/EURUSD H4 (2019-01-01 – 2024-06-01) für WFA ...")
    df_full = load_session("4h", start="2019-01-01", end="2024-06-01")
    print(f"  {len(df_full)} H4-Bars geladen\n")

    df_wfa = run(df_full)

    if not df_wfa.empty:
        df_wfa.to_csv("wfa_results.csv", index=False)
        print("\nErgebnisse gespeichert: wfa_results.csv")
