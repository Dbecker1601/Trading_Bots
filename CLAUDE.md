# CLAUDE.md – Projektkontext für Claude Code

> **Pflicht:** Diese Datei UND `CODEX.md` müssen bei jeder strukturellen Änderung am Projekt
> (neue Module, neue Bots, geänderte Architektur, neue Abhängigkeiten) sofort aktualisiert werden.
> Kein Commit, der die Projektstruktur ändert, ohne beide Dateien zu synchronisieren.

---

## Projektübersicht

**Trading_Bots** ist ein algorithmisches Trading-System, das aus zwei unabhängigen Bots besteht:

| Bot   | Markt              | Ansatz                                    | Stack                        |
|-------|--------------------|-------------------------------------------|------------------------------|
| Bot1  | Forex (EUR/USD etc.)| Regelbasierte Strategien, Prop-Firm-Scoring | Python, VectorBT Pro, Databento |
| Bot2  | MNQ Futures (Micro Nasdaq) | Decision Engine + Volume Profile + Apex Compliance | Python, Databento, pytest |

Datenquelle für beide Bots: **Databento API** (`DATABENTO_API_KEY` via Env-Variable).
API-Key niemals in Code oder Commits – nur über `.env` (lokal, in `.gitignore`) oder GitHub Secrets.

---

## Bot1 – Forex Strategies

**Pfad:** `Bot1/`

### Zweck
Prop-Firm-kompatible Forex-Strategien, die per Walk-Forward validiert und mit VectorBT Pro gebacktestet werden.

### Struktur
```
Bot1/
├── main.py                          # Bot-Loop (dry_run, Interval via ENV)
├── Dockerfile / docker-compose.yml  # Container-Deployment
├── requirements.txt
├── benchmark.py                     # Strategie-Benchmarking
├── logs/                            # bot.log, benchmark_results.csv
└── forex_strategies/
    ├── config.py                    # Symbol, Fees, Startkapital
    ├── prop_firm_score.py           # Prop-Firm-Scoring + Dashboard
    ├── strategy1_donchian.py        # Donchian-Channel Breakout (H1, ATR SL/TP)
    ├── strategy2_mtf_rsi.py         # Multi-Timeframe RSI Pullback (M15/H4)
    ├── strategy3_optimizer.py       # Composite Score Optimizer (Grid-Search)
    └── walk_forward.py              # Walk-Forward-Validierung
```

### Strategien
- **Strategy 1 – Donchian Breakout:** Preis > N-Perioden-Hoch → Long, ATR-basierter SL/TP (RR 1:2)
- **Strategy 2 – MTF RSI:** H4-Trend-Filter + M15-RSI-Pullback-Entry
- **Strategy 3 – Optimizer:** Grid-Search über beide Strategien, Composite-Score (Sharpe + Profit Factor + SQN)

### Prop-Firm-Mindestanforderungen
```
Sharpe Ratio  > 1.0
Max Drawdown  < 8%
Profit Factor > 1.4
SQN           > 2.0
Trades        > 100
Walk-Forward  > 60% profitable Splits
```

### Deployment
```bash
docker-compose up -d   # startet Bot1 als Container
```
ENV-Variablen: `DATABENTO_API_KEY`, `DRY_RUN` (default: true), `INTERVAL_SECONDS` (default: 60)

---

## Bot2 – MNQ Futures Bot

**Pfad:** `Bot2/`

### Zweck
Intraday-Trading auf MNQ (Micro Nasdaq Futures) mit regelbasierter Decision Engine, Volume-Profile-Analysen und automatischem Apex Prop-Firm-Compliance-Check.

### Struktur
```
Bot2/
├── trading_bots/
│   ├── config.py              # Konfigurationsdatenpunkte
│   ├── databento_client.py    # create_databento_client() – Key via ENV
│   ├── market_data.py         # fetch_historical_bars() – Validierung + Wrapping
│   ├── decision_engine.py     # Regime-Erkennung + Signalbildung + Edge-Gate
│   ├── execution.py           # build_entry_plan() – limit vs. market
│   ├── backtest.py            # BacktestConfig, Trade, Walk-Forward-Fenster
│   ├── reporting.py           # KPI: Win-Rate, Profit Factor, Max DD, Sharpe
│   ├── apex_rules.py          # Apex-Profile + Compliance-Check
│   ├── evaluation_pipeline.py # kombinierter Report + JSON/HTML Export
│   ├── strategy_v1.py         # Strategie v1 (Baseline)
│   ├── strategy_v2.py         # Strategie v2 (Volume Profile, HVN/LVN)
│   └── smoke.py               # Smoke-Tests
├── scripts/
│   ├── run_strategy_v1.py
│   ├── run_strategy_v2.py
│   ├── run_strategy_v2_3_walkforward.py        # Walk-Forward v2.3
│   ├── run_strategy_v2_3b_walkforward_sensitivity.py
│   ├── run_strategy_v2_3c_walkforward_step10.py
│   ├── run_strategy_v2_3d_walkforward_step10_dedup.py
│   ├── run_strategy_v2_4_forward_oos.py        # Out-of-Sample Forward Test
│   ├── smoke_test_databento.py
│   ├── make_trade_decision_images.py
│   └── make_trade_decision_profile_chart.py
├── strategy_knowledge/
│   ├── intraday_amt_priceaction_strategy.md    # AMT + Price Action Wissen
│   └── orderflow_edge_setups_v1.md             # Order Flow Edge Setups
├── tests/                     # pytest-Suite (Apex, Backtest, Decision Engine, ...)
├── docs/plans/                # Architektur-Entscheidungen
├── reports/                   # latest-report.json / .html
├── .github/workflows/
│   ├── ci.yml                 # CI-Pipeline
│   └── databento-smoke.yml    # Databento Smoke Test
└── .env.example
```

### Kernkomponenten

**Decision Engine** (`decision_engine.py`)
- Regime-Erkennung: `trend` | `range` | `risk_off`
- Signalbildung (regelbasiert) + optionales ML-Overlay (`ml_prob_up`)
- Edge-Gate: Trade nur wenn Edge > Kosten + Sicherheitspuffer
- Kill-Switch bei Tagesverlust-Limit

**Strategy V2** (`strategy_v2.py`)
- Volume-Profile-basiert: HVN (High Volume Node) und LVN (Low Volume Node)
- Kurz-Bias (`short_only` default), erlaubte Session-Stunden konfigurierbar
- Min Entry Gap zwischen Trades, Spread-Filter, Vol-Z-Score-Filter

**Apex Compliance** (`apex_rules.py`)
- Profile für `intraday` und `eod` Konten: $25k / $50k / $100k / $150k
- Checks: Trailing Threshold, Daily Loss Limit, Max Contracts, Consistency Rule

**Backtest & Reporting**
- Walk-Forward-Validierung über mehrere Fenster
- KPI: Sharpe, Sortino, Calmar, Win Rate, Profit Factor, Max Drawdown, SQN
- Export: JSON + HTML Reports nach `reports/`

### Tests ausführen
```bash
cd Bot2
pip install -r requirements.txt   # falls noch nicht installiert
pytest tests/
```

### Apex-Kontogrößen (Stand: 2026-04-24, PropFirmApp-Daten)
| Typ       | Größe    | Profit-Ziel | Max Loss | Daily Loss | Max Contracts |
|-----------|----------|-------------|----------|------------|---------------|
| intraday  | $25.000  | $1.500      | $1.000   | –          | 4             |
| intraday  | $50.000  | $3.000      | $2.000   | –          | 10            |
| intraday  | $100.000 | $6.000      | $3.000   | –          | 14            |
| eod       | $50.000  | $3.000      | $2.000   | $1.000     | 10            |

*Werte vor Live-Nutzung mit offiziellem Apex-Konto abgleichen.*

---

## Gemeinsame Regeln

- **API-Key:** Immer nur via `DATABENTO_API_KEY` ENV-Variable. Nie in Code, nie committen.
- **DRY_RUN:** Bot1-Loop läuft defaultmäßig im Dry-Run-Modus.
- **Python:** 3.12 (Bot1: `cpython-312` im `__pycache__`). Alle Dateien ohne Typ-Annotationen wo möglich typisieren.
- **Keine echten Orders:** Bot2 hat noch keinen Live-Order-Router. `execution.py` gibt nur den Plan zurück.

---

## Nächste Ausbaustufen

1. ML-Overlay (LightGBM) für bessere Trade-Filterung in Bot2
2. RL-basiertes Position Sizing / Execution Optimierung (Phase 3)
3. Intraday-Session-Filter + News-Filter für Bot2
4. Live-Order-Router an Broker-API anbinden

---

## Synchronisierungspflicht

**Bei jeder Änderung an Projektstruktur, Modulen oder Architektur:**
1. Diese Datei (`CLAUDE.md`) aktualisieren
2. `CODEX.md` parallel aktualisieren
3. Beide Dateien im selben Commit wie der Code-Change einchecken
