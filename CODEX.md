# CODEX.md – Projektkontext für OpenAI Codex / Copilot

> **Pflicht:** Diese Datei UND `CLAUDE.md` müssen bei jeder strukturellen Änderung am Projekt
> (neue Module, neue Bots, geänderte Architektur, neue Abhängigkeiten) sofort aktualisiert werden.
> Kein Commit, der die Projektstruktur ändert, ohne beide Dateien zu synchronisieren.

---

## Projektübersicht

**Trading_Bots** – algorithmisches Trading-System mit zwei unabhängigen Bots.

| Bot   | Markt                       | Kernansatz                                          | Wichtigste Abhängigkeiten     |
|-------|-----------------------------|-----------------------------------------------------|-------------------------------|
| Bot1  | Forex (EUR/USD, GBP/USD …)  | Regelbasierte Strategien, Prop-Firm-Scoring         | VectorBT Pro, Databento, TA-Lib |
| Bot2  | MNQ Futures (Micro Nasdaq)  | Decision Engine, Volume Profile, Apex Compliance    | Databento, pytest             |

**Datenquelle:** Databento API (`DATABENTO_API_KEY` als Umgebungsvariable).
**Sicherheitsregel:** API-Key niemals im Code oder in Commits – nur via `.env` (lokal) oder GitHub Secrets.

---

## Verzeichnisstruktur

```
Trading_Bots/
├── CLAUDE.md          # Claude Code Projektkontext (immer synchron halten)
├── CODEX.md           # Dieses Dokument – für Codex/Copilot (immer synchron halten)
├── Bot1/              # Forex-Strategien (VectorBT Pro)
└── Bot2/              # MNQ Futures Bot (Decision Engine + Apex)
```

---

## Bot1 – Forex Strategies

**Einstiegspunkt:** `Bot1/main.py`  
**Strategie-Logik:** `Bot1/forex_strategies/`

### Module

| Datei                          | Zweck                                                        |
|--------------------------------|--------------------------------------------------------------|
| `main.py`                      | Endlos-Loop mit `tick()`, ENV-Variablen für Konfiguration    |
| `Dockerfile` / `docker-compose.yml` | Container-Deployment                                   |
| `benchmark.py`                 | Strategie-Benchmarking, schreibt `logs/benchmark_results.csv`|
| `forex_strategies/config.py`   | `SYMBOL`, `FEES`, `INIT_CASH`                                |
| `forex_strategies/prop_firm_score.py` | Prop-Firm-Scoring-Funktion + Report-Dashboard       |
| `forex_strategies/strategy1_donchian.py` | Donchian-Channel Breakout, ATR-basierter SL/TP   |
| `forex_strategies/strategy2_mtf_rsi.py`  | Multi-Timeframe RSI Pullback (M15 Entry, H4 Filter)|
| `forex_strategies/strategy3_optimizer.py`| Grid-Search Optimizer, Composite Score             |
| `forex_strategies/walk_forward.py`       | Walk-Forward-Validierung                           |

### Konfiguration via ENV
```
DATABENTO_API_KEY   # Pflicht für Live-Daten
DRY_RUN             # "true" (default) | "false"
INTERVAL_SECONDS    # Tick-Interval in Sekunden (default: 60)
```

### Strategien im Überblick

**Strategy 1 – Donchian Breakout**
- Signal: `close > rolling_max(high, N)` → Long; `close < rolling_min(low, N)` → Short
- SL/TP: ATR-Multiplikator (SL = 2×ATR, TP = 4×ATR → RR 1:2)
- Timeframes: H1, H4, Daily

**Strategy 2 – MTF RSI**
- H4 als Trend-Filter, M15 als Entry-Timeframe
- RSI-Pullback-Entry bei Übereinstimmung beider Timeframes

**Strategy 3 – Optimizer**
- Grid-Search über Parameter von Strategie 1+2
- Composite Score: gewichtet Sharpe Ratio + Profit Factor + SQN

---

## Bot2 – MNQ Futures Bot

**Paket:** `Bot2/trading_bots/`  
**Tests:** `Bot2/tests/` (pytest)  
**Skripte:** `Bot2/scripts/`

### Module

| Datei                       | Zweck                                                                 |
|-----------------------------|-----------------------------------------------------------------------|
| `config.py`                 | Konfigurationsdatenpunkte                                             |
| `databento_client.py`       | `create_databento_client()` – liest Key aus ENV, loggt ihn nie       |
| `market_data.py`            | `fetch_historical_bars()` – Validierung + Fehler-Wrapping             |
| `decision_engine.py`        | Regime-Erkennung + Signalbildung + Edge-Gate + Kill-Switch           |
| `execution.py`              | `build_entry_plan()` – limit bei engen, market bei weiten Spreads    |
| `backtest.py`               | `BacktestConfig`, `Trade`, Walk-Forward-Fenster, Kostenmodell        |
| `reporting.py`              | KPI: Win-Rate, Profit Factor, Max Drawdown, Sharpe                   |
| `apex_rules.py`             | Apex-Profile ($25k–$150k) + Compliance-Checks                        |
| `evaluation_pipeline.py`    | Kombinierter Report: Backtest + KPI + Apex → JSON + HTML             |
| `strategy_v1.py`            | Baseline-Strategie v1                                                 |
| `strategy_v2.py`            | Volume-Profile-Strategie (HVN/LVN), Short-Bias, Session-Filter       |
| `smoke.py`                  | Smoke-Tests für schnelle Validierung                                  |

### Decision Engine – Datenfluss

```
MarketSnapshot + RiskState
        ↓
   detect_regime()  →  "trend" | "range" | "risk_off"
        ↓
   Signalbildung (regelbasiert) + ml_prob_up (optional)
        ↓
   Edge-Gate: edge_bps > estimated_cost_bps + safety_buffer_bps ?
        ↓
   Kill-Switch: daily_pnl < max_daily_loss ?
        ↓
   TradeDecision(action, target_position, regime, signal_score, edge_bps, reason)
        ↓
   build_entry_plan()  →  OrderType(limit | market)
```

### Strategy V2 – Kernparameter (`StrategyV2Config`)

| Parameter                 | Default  | Bedeutung                                    |
|---------------------------|----------|----------------------------------------------|
| `bin_size`                | 1.0      | Volume-Profile Bin-Größe in Punkten          |
| `hvn_quantile`            | 0.70     | High Volume Node Schwellwert                 |
| `lvn_quantile`            | 0.30     | Low Volume Node Schwellwert                  |
| `max_spread_bps_for_entry`| 3.0      | Max. Spread für Entry                        |
| `short_only`              | True     | Nur Short-Trades (v2.1)                      |
| `min_entry_gap_bars`      | 20       | Mindestabstand zwischen Trades               |
| `session_start_utc_minute`| 810      | 13:30 UTC (NYSE Open)                        |
| `session_end_utc_minute`  | 1200     | 20:00 UTC                                    |

### Apex-Compliance-Checks

- **Trailing Threshold:** Equity darf nie unter `peak_equity - max_loss` fallen
- **Daily Loss Limit:** EOD-Konten: tagesweiser Verlust < `daily_loss_limit`
- **Max Contracts:** Kontraktlimit pro Kontogröße einhalten
- **Consistency Rule:** Kein einzelner Trade > 50% des Gesamtgewinns

### Scripts-Übersicht

| Script                                        | Zweck                                          |
|-----------------------------------------------|------------------------------------------------|
| `run_strategy_v1.py`                          | Strategie v1 ausführen                         |
| `run_strategy_v2.py`                          | Strategie v2 ausführen                         |
| `run_strategy_v2_3_walkforward.py`            | Walk-Forward v2.3                              |
| `run_strategy_v2_3b_walkforward_sensitivity.py`| Sensitivitätsanalyse                          |
| `run_strategy_v2_3c_walkforward_step10.py`    | Walk-Forward mit Step-Größe 10                 |
| `run_strategy_v2_3d_walkforward_step10_dedup.py`| Dedup-Variante                              |
| `run_strategy_v2_4_forward_oos.py`            | Forward Out-of-Sample Test                     |
| `make_trade_decision_images.py`               | Visualisierungen der Trade-Entscheidungen      |
| `make_trade_decision_profile_chart.py`        | Volume-Profile-Charts                          |
| `smoke_test_databento.py`                     | Verbindungstest Databento API                  |

---

## Gemeinsame Konventionen

- **Python 3.12**, type hints wo möglich, `dataclass(frozen=True)` für Konfigurationen
- **Keine echten Orders:** Bot2 hat noch keinen Live-Order-Router
- **Tests:** `pytest Bot2/tests/` – CI via GitHub Actions (`.github/workflows/ci.yml`)
- **Reports:** werden nach `Bot2/reports/` als JSON und HTML exportiert
- **Strategy Knowledge:** Domänenwissen in `Bot2/strategy_knowledge/` (AMT, Order Flow)

---

## Nächste Ausbaustufen

1. ML-Overlay (LightGBM) für Trade-Filterung in Bot2
2. RL-basiertes Position Sizing / Execution (Phase 3)
3. Intraday-Session-Filter + News-Filter
4. Live-Order-Router an Broker-API

---

## Synchronisierungspflicht

**Bei jeder Änderung an Projektstruktur, Modulen oder Architektur:**
1. `CODEX.md` (diese Datei) aktualisieren
2. `CLAUDE.md` parallel aktualisieren
3. Beide Dateien im selben Commit wie der Code-Change einchecken
