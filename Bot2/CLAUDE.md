# CLAUDE.md – Bot2: MNQ Futures Bot

> **Pflicht:** Bei jeder Änderung an Modulen, Strategien, Parametern oder Architektur
> diese Datei UND `CODEX.md` im selben Commit aktualisieren.
> Gleiches gilt für das Root-`CLAUDE.md` bei strukturellen Änderungen.

---

## Zweck

Bot2 ist ein **Intraday-Trading-System für MNQ (Micro Nasdaq Futures)**.
Kern ist eine regelbasierte Decision Engine mit Volume-Profile-basierter Strategie und
automatischem **Apex Prop-Firm-Compliance-Check** nach jedem Backtest.

Datenquelle: **Databento API** (`DATABENTO_API_KEY` via ENV – nie in Code).
CI/CD: GitHub Actions (`.github/workflows/`). Tests: **pytest**.

---

## Verzeichnisstruktur

```
Bot2/
├── trading_bots/              # Haupt-Paket
│   ├── __init__.py
│   ├── config.py              # Konfigurationsdatenpunkte
│   ├── databento_client.py    # API-Client-Factory
│   ├── market_data.py         # Historische Bars fetchen + validieren
│   ├── decision_engine.py     # Regime + Signal + Edge-Gate + Kill-Switch
│   ├── execution.py           # Order-Typ-Entscheidung (limit vs. market)
│   ├── backtest.py            # BacktestConfig, Trade, Walk-Forward-Fenster
│   ├── reporting.py           # KPI-Berechnung
│   ├── apex_rules.py          # Apex-Profile + Compliance-Checks
│   ├── evaluation_pipeline.py # Kombinierter Report → JSON/HTML
│   ├── strategy_v1.py         # Strategie V1: EMA-Breakout + Pullback + Range
│   ├── strategy_v2.py         # Strategie V2: Volume Profile HVN/LVN
│   └── smoke.py               # Smoke-Tests für schnellen Sanity-Check
├── scripts/                   # Standalone-Skripte (Backtest-Runs, Visualisierungen)
├── strategy_knowledge/        # Markdown-Dokumente mit Trading-Domänenwissen
├── tests/                     # pytest-Testsuite
├── docs/plans/                # Architektur-ADRs
├── reports/                   # Generierte Reports (gitignored)
├── .github/workflows/         # CI-Pipeline + Databento-Smoke-Test
└── .env.example
```

---

## Kernmodule im Detail

### `decision_engine.py` – Zentrale Entscheidungslogik

**Datenklassen:**
```python
DecisionConfig   # Schwellwerte und Limits (frozen dataclass)
MarketSnapshot   # Momentaufnahme des Markts (returns, EMA, vol, ATR, spread, session_minute)
RiskState        # Aktueller Portfolio-Zustand (position, daily_pnl)
TradeDecision    # Ergebnis: action, target_position, regime, signal_score, edge_bps, reason
```

**Regime-Erkennung (`detect_regime`):**
```
realized_vol >= 0.02           → "risk_off"  (kein Trading)
|EMA_fast - EMA_slow| >= 8.0
 AND returns_5m aligned        → "trend"
else                           → "range"
```

**Edge-Gate:**
```
edge_bps = signal_score × max_edge_bps
Nur Trade wenn: edge_bps > estimated_cost_bps(4.0) + safety_buffer_bps(1.0) = 5.0 bps
```

**Kill-Switch:** Kein Trade wenn `daily_pnl < max_daily_loss (-500 $)`

**Position Sizing:** Vol-Targeting (`target_vol=0.01`), max 3 Kontrakte,
skaliert linear von 1 (min edge) bis 3 (bei `edge_for_max_size_bps=12.0`).

---

### `strategy_v1.py` – Baseline-Strategie

**Typen:**
- **Trend-Breakout:** Preis bricht über 20-Bar-Hoch → Long; unter 20-Bar-Tief → Short
- **Pullback:** Preis zieht innerhalb 0.75×ATR zur EMA zurück nach Breakout
- **Range:** Z-Score(close vs. range-mean) > 1.2 → Countertrend-Entry

**Position-Management:**
- TP1 bei 1.0×R → Half-Close + Trail auf Break-Even
- Trailing Stop: 2.0×ATR
- Max Hold: 45 Bars, Min Hold: 3 Bars
- Loss-Streak-Reduction: nach 2 Verlust-Trades → halbe Größe

**Key-Parameter (`StrategyV1Config`):**

| Parameter                   | Default | Beschreibung                              |
|-----------------------------|---------|-------------------------------------------|
| `ema_fast` / `ema_slow`     | 20/100  | Trend-Filter EMAs                         |
| `breakout_lookback`         | 20      | N-Bar-Hoch/Tief für Breakout              |
| `stop_atr_mult`             | 1.2     | ATR-Mult für Stop-Loss                    |
| `tp1_r_multiple`            | 1.0     | Erstes TP bei 1×R                         |
| `trailing_atr_mult`         | 2.0     | ATR-Mult für Trailing Stop                |
| `max_hold_bars`             | 45      | Maximale Haltedauer                       |
| `risk_per_trade`            | 0.003   | Risiko pro Trade (0.3% des Kapitals)      |
| `max_daily_loss`            | -500 $  | Tagesverlust-Kill-Switch                  |
| `session_start_utc_minute`  | 810     | 13:30 UTC (NYSE Open)                     |
| `session_end_utc_minute`    | 1200    | 20:00 UTC                                 |
| `point_value`               | 2.0     | $ pro Punkt pro Kontrakt (MNQ)            |

---

### `strategy_v2.py` – Volume Profile Strategie

**Kernkonzept:** Tägliches Volume-Profile aus 1-Minuten-Bars berechnen.
HVN (High Volume Nodes) = Widerstands-/Unterstützungszonen.
LVN (Low Volume Nodes) = Schnelle Durchgangszonen.

**Zwei Setup-Typen:**

**Setup 1 – Edge Setup (HVN-Kante):**
```
Preis nähert sich HVN-Kante von oben/unten (Toleranz: 2.0 Punkte)
Vol-Z-Score > 0.5 (aktive Umsatzbeteiligung)
→ Short an HVN-Oberkante, Long an HVN-Unterkante
Hold: 12 Bars
```

**Setup 2 – LVN Rejection:**
```
Preis testet LVN (Toleranz: 1.5 Punkte) + Rejection-Kerze
Vol-Z-Score > 0.8 (Bestätigung durch höheres Volumen)
→ Short wenn Preis über LVN + Rejection, Long darunter
Hold: 15 Bars
```

**Filter (v2.1):**
- `short_only=True` (Standard) – nur Short-Trades
- `allowed_short_hours_utc = (14, 15, 17, 19)` – erlaubte Short-Entry-Stunden
- `min_entry_gap_bars=20` – Mindestabstand zwischen Trades (verhindert Over-Trading)
- `max_spread_bps_for_entry=3.0` – kein Entry bei weiten Spreads
- `daily_bias_lookback_bars=30` – Trend-Bias aus letzten 30 Bars

**Volume-Profile-Berechnung:**
```python
# 1-Minuten-Bars → Histogramm nach Preisklasse (bin_size=1.0 Punkt)
# Leichtes Smoothing (3-Bar Moving Average)
# HVN = Bins über hvn_quantile (0.70)
# LVN = Bins unter lvn_quantile (0.30)
# Kontiguous-Regions → Kanten extrahieren
```

**Key-Parameter (`StrategyV2Config`):**

| Parameter                       | Default    | Beschreibung                             |
|---------------------------------|------------|------------------------------------------|
| `bin_size`                      | 1.0        | Volume-Profile Bin in Punkten            |
| `hvn_quantile` / `lvn_quantile` | 0.70/0.30  | Node-Schwellwerte                        |
| `edge_tolerance_points`         | 2.0        | Toleranz für HVN-Edge-Entry              |
| `lvn_tolerance_points`          | 1.5        | Toleranz für LVN-Entry                   |
| `volz_edge_threshold`           | 0.5        | Min. Vol-Z-Score für Edge-Setup          |
| `volz_lvn_threshold`            | 0.8        | Min. Vol-Z-Score für LVN-Setup           |
| `hold_bars_edge` / `hold_bars_lvn` | 12/15   | Haltedauer in Bars                       |
| `short_only`                    | True       | Nur Short-Richtung erlaubt               |
| `min_entry_gap_bars`            | 20         | Mindestabstand zwischen Trades           |

---

### `apex_rules.py` – Apex Compliance

**Kontogrößen** (Stand: 2026-04-24, Quelle: PropFirmApp):

| Typ       | Größe    | Profit-Ziel | Max Loss | Daily Loss | Max Contracts |
|-----------|----------|-------------|----------|------------|---------------|
| intraday  | $25.000  | $1.500      | $1.000   | –          | 4             |
| intraday  | $50.000  | $3.000      | $2.000   | –          | 10            |
| intraday  | $100.000 | $6.000      | $3.000   | –          | 14            |
| intraday  | $150.000 | $9.000      | $4.000   | –          | 17            |
| eod       | $25.000  | $1.500      | $1.000   | $500       | 4             |
| eod       | $50.000  | $3.000      | $2.000   | $1.000     | 10            |
| eod       | $100.000 | $6.000      | $3.000   | $1.500     | 14            |
| eod       | $150.000 | $9.000      | $4.000   | $2.000     | 17            |

**Checks:**
1. **Trailing Threshold:** `min(equity_curve) >= peak_equity - max_loss`
2. **Daily Loss Limit** (nur EOD): Kein Tag unter `daily_loss_limit`
3. **Max Contracts:** Nie mehr Kontrakte als erlaubt
4. **Consistency Rule:** Kein Trade > 50% des Gesamtgewinns

---

### `evaluation_pipeline.py` – Kompletter Report

```python
report = evaluate_trades_for_apex(
    trades=trades,
    backtest_config=BacktestConfig(initial_equity=50_000, fee_bps=0.5,
                                   slippage_bps=0.5, point_value=2.0),
    account_type="intraday",
    account_size=50_000,
)
export_report_json(report, "reports/report.json")
export_report_html(report, "reports/report.html")
```

Report enthält: KPIs (Sharpe, Win Rate, Profit Factor, Max DD, SQN) + Apex Compliance-Status.

---

## Scripts-Übersicht

| Script                                          | Was es macht                                     |
|-------------------------------------------------|--------------------------------------------------|
| `run_strategy_v1.py`                            | V1 auf Testdaten, gibt Report aus                |
| `run_strategy_v2.py`                            | V2 Basis-Run                                     |
| `run_strategy_v2_3_walkforward.py`              | Walk-Forward über mehrere Fenster                |
| `run_strategy_v2_3b_walkforward_sensitivity.py` | Sensitivitätsanalyse der V2-Parameter            |
| `run_strategy_v2_3c_walkforward_step10.py`      | Walk-Forward mit Step-Größe 10 Bars              |
| `run_strategy_v2_3d_walkforward_step10_dedup.py`| Wie 3c aber mit Duplikat-Trade-Filterung         |
| `run_strategy_v2_4_forward_oos.py`              | Forward Out-of-Sample Test (echter Stresstest)   |
| `make_trade_decision_images.py`                 | Visualisiert Einzel-Trade-Entscheidungen         |
| `make_trade_decision_profile_chart.py`          | Zeichnet Volume-Profile + Einstiegspunkte        |
| `smoke_test_databento.py`                       | Prüft Databento-API-Verbindung                   |

---

## Tests ausführen

```bash
cd Bot2
pip install -r requirements.txt
pytest tests/ -v

# Einzelne Test-Module
pytest tests/test_strategy_v2.py -v
pytest tests/test_apex_rules.py -v
pytest tests/test_decision_engine.py -v
```

**CI:** `.github/workflows/ci.yml` läuft bei jedem Push.
Databento-Smoke-Test (`databento-smoke.yml`) prüft API-Erreichbarkeit separat.

---

## Strategy Knowledge

Domänenwissen in `strategy_knowledge/`:
- `intraday_amt_priceaction_strategy.md` – Auction Market Theory + Price Action Konzepte
- `orderflow_edge_setups_v1.md` – Order Flow Edge Setups (konkrete Entry-Muster)

Diese Dokumente sind die konzeptionelle Grundlage für Strategy V2 und zukünftige Strategien.

---

## Nächste Ausbaustufen

1. **ML-Overlay:** LightGBM-Modell für `ml_prob_up` (bessere Trade-Filterung)
2. **RL-Execution:** Position Sizing / Execution-Optimierung via RL (Phase 3)
3. **Live-Order-Router:** `execution.py` → Broker-API-Anbindung
4. **News-Filter:** Makro-Event-Kalender-Integration
5. **Session-Filter:** Separate Parameter pro Session (London Open, NYSE Open, Close)
