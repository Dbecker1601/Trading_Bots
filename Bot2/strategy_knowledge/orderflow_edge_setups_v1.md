# Orderflow-Setups (Kanten-basiert, ohne POC-Fokus)

Datengrundlage (Mining):
- Datei: `reports/cache/mnq_1m_2025-10-29_to_2026-04-27.csv.gz`
- Session: 13:30–20:00 UTC (RTH)
- Profilzonen aus Vortag (1-Punkt-Bins, geglättetes Volumenprofil):
  - HVN-Kanten
  - LVN-Gates
- Orderflow-Proxys auf M1:
  - `rf` (rotational factor Proxy)
  - `vol_z` (Volume Z-Score ggü. Rolling Mean)

Wichtig:
- Das ist ein schnelles Regel-Mining, kein finaler Walk-Forward mit vollständigem Cost-Model.
- Ziel: robuste Kandidaten für den nächsten formalen Backtest.

---

## Setup 1: Inside-HVN Edge Rejection (dein Wunsch-Setup)

Idee:
- Preis ist im „Berg“ (HVN-Cluster), testet eine Kante und wird dort abgewiesen.

Long-Regel:
1. Distanz zur nächsten HVN-Kante in `[-2, 0]` Punkte (untere Kante getestet)
2. `rf > 0`
3. Candle bestätigt Rücklauf nach oben (`Close > Close[-1]`)
4. `vol_z > 0.5` (Reaktion mit Beteiligung)
5. Entry auf nächster Kerze

Short-Regel:
1. Distanz zur nächsten HVN-Kante in `[0, +2]` Punkte (obere Kante getestet)
2. `rf < 0`
3. Candle bestätigt Rücklauf nach unten (`Close < Close[-1]`)
4. `vol_z > 0.5`
5. Entry auf nächster Kerze

Invalidierung (Stop):
- Long: unter Rejection-Swing-Low oder 0.6x ATR(14)
- Short: über Rejection-Swing-High oder 0.6x ATR(14)

Ziele:
- TP1: HVN-Innenbereich (Mean)
- TP2: Gegenkante des HVN

---

## Setup 2: LVN Acceptance Pass-through

Idee:
- Preis erreicht „Tal“ (LVN), zeigt Akzeptanz + Flow in Durchlaufrichtung, dann Impuls zum nächsten Cluster.

Long-Regel:
1. Distanz zur nächsten LVN <= 1.5 Punkte
2. `rf[t] > 0` und `rf[t-1] > 0`
3. `vol_z > 0.8`
4. `Close[t] > Close[t-1]`
5. Entry nächste Kerze

Short-Regel:
1. Distanz zur nächsten LVN <= 1.5 Punkte
2. `rf[t] < 0` und `rf[t-1] < 0`
3. `vol_z > 0.8`
4. `Close[t] < Close[t-1]`
5. Entry nächste Kerze

Invalidierung:
- Reclaim zurück über/unter das LVN-Gate + 1 Tick Puffer

Ziele:
- Nächste HVN-Kante in Bewegungsrichtung

---

## Was das Mining gezeigt hat (Quick-Findings)

Gesamtergebnis (ohne strenge Kosten):
- `inside_hvn_edge_reject_short`: 396 Trades, Winrate 47.5%, avg +4.80 (beste Rohkante)
- `lvn_accept_pass_short`: 399 Trades, Winrate 50.4%, avg +2.59 (zweite Rohkante)
- Long-Varianten waren im Gesamtzeitraum schwächer/instabil.

Zeitfenster-Effekt (Inside-HVN Rejection):
- Long funktionierte besser in UTC-Stunden: 13, 16, 18, 19
- Short funktionierte besser in UTC-Stunden: 14, 15, 17, 19

=> Konsequenz:
- Nicht symmetrisch handeln.
- Side- und Zeitfensterfilter nutzen.

---

## Priorisierung (praktisch für v1)

A1) Inside-HVN Edge Rejection SHORT
- Nur UTC 14–15 und 17–19
- Nur bei `vol_z > 0.5`

A2) LVN Pass-through SHORT
- Nur bei `vol_z > 0.8` und 2-bar `rf` Bestätigung

B1) Inside-HVN Edge Rejection LONG
- Nur in UTC 13, 16, 18, 19
- zusätzlicher Filter: Tagesbias long (Open/erste 30m über Vortagsschluss)

B2) LVN Pass-through LONG
- erst nach zusätzlichem Trendfilter aktivieren

---

## v2.2 Ergebnis (umgesetzt)

Durchgeführter Sweep (MNQ Cache, short-bias):
- 246 Kandidaten (inkl. Setup-separater Baselines)
- Parameterraum (reduziert):
  - `volz_edge` in {0.5, 0.8, 1.1}
  - `volz_lvn` in {0.8, 1.1, 1.4}
  - `hold_edge` in {8, 12, 16}
  - `hold_lvn` in {12, 18, 24}
  - `entry_gap` in {15, 25, 40}

Bestes Set (bisher):
- `short_only=True`
- `use_edge_setup=True`
- `use_lvn_setup=True`
- `volz_edge_threshold=1.1`
- `volz_lvn_threshold=1.4`
- `hold_bars_edge=16`
- `hold_bars_lvn=12`
- `min_entry_gap_bars=40`

KPI (mit Kostenmodell im Projekt):
- Trades: 144
- Total PnL: +1699.44
- Winrate: 52.08%
- Profit Factor: 1.367
- Max Drawdown: -1857.72

Reports:
- `reports/strategy_v2_2_best_profile_edge_orderflow.json`
- `reports/strategy_v2_2_best_profile_edge_orderflow.html`
- Sweep-Übersicht:
  - `reports/strategy_v2_2_sweep_results.json`
  - `reports/strategy_v2_2_sweep_results.csv`

## Konkrete nächste Backtest-Schritte
1. Walk-Forward nur mit dem Best-Set über rollierende Fenster.
2. Hour-by-hour Robustheit prüfen (nicht nur Gesamt-PnL).
3. Entry-Kosten-Sensitivität (höhere Slippage) stressen.
4. Wenn stabil: Long-Seite separat und deutlich restriktiver hinzufügen.
