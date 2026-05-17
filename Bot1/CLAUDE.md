# CLAUDE.md – Bot1: Forex Strategies

> **Pflicht:** Bei jeder Änderung an Strategie-Logik, Parametern, Modulen oder Abhängigkeiten
> diese Datei UND `CODEX.md` im selben Commit aktualisieren.
> Gleiches gilt für das Root-`CLAUDE.md` bei strukturellen Änderungen.

---

## Zweck

Bot1 implementiert **regelbasierte Forex-Strategien**, die für Prop-Firm-Challenges
(FTMO, The5%ers, MyFundedFx, E8 Funding) optimiert und per Walk-Forward validiert werden.
Backtest-Engine: **VectorBT Pro**. Datenquelle: **Databento API** (Yahoo Finance als Fallback).

---

## Verzeichnisstruktur

```
Bot1/
├── main.py                          # Produktions-Bot-Loop (läuft als Docker-Container)
├── Dockerfile                       # Python 3.12 Image, kopiert forex_strategies/
├── docker-compose.yml               # Service-Definition, ENV-Variablen-Mounting
├── requirements.txt                 # vectorbt[full], ta-lib, pandas, databento, python-dotenv
├── benchmark.py                     # Führt alle Strategien aus, schreibt logs/benchmark_results.csv
├── logs/
│   ├── bot.log                      # Runtime-Log des Bot-Loops
│   └── benchmark_results.csv        # Benchmark-Ergebnisse (gitignored)
└── forex_strategies/
    ├── config.py                    # Globale Konstanten: SYMBOL, FEES, INIT_CASH
    ├── prop_firm_score.py           # Scoring-Funktion + Dashboard-Print
    ├── strategy1_donchian.py        # Strategie 1: Donchian Breakout
    ├── strategy2_mtf_rsi.py         # Strategie 2: MTF Trend + RSI Pullback
    ├── strategy3_optimizer.py       # Strategie 3: Composite Score Grid-Search
    └── walk_forward.py              # Walk-Forward Validation Framework
```

---

## Strategien im Detail

### Strategie 1 – Donchian Channel Breakout (`strategy1_donchian.py`)

**Konzept:** Klassisches Volatility-Breakout-System. Preis bricht über/unter das
N-Perioden-Hoch/Tief → Trend-Following-Entry.

**Signal-Logik:**
```
long_entry  = close > rolling_max(high, channel_window=20).shift(1)
short_entry = close < rolling_min(low,  channel_window=20).shift(1)
```

**Exit-Logik:**
- Stop-Loss:   ATR × 2.0 (gegenteilig zur Entryrichtung)
- Take-Profit: ATR × 4.0 → Risk/Reward = 1:2
- Cross-Exit:  Long-Exit bei Short-Signal (und umgekehrt)

**Parameter:**
| Parameter       | Default | Beschreibung                     |
|-----------------|---------|----------------------------------|
| `channel_window`| 20      | Perioden für Donchian-Kanal      |
| `atr_period`    | 14      | ATR-Berechnungsperiode           |
| `sl_mult`       | 2.0     | ATR-Multiplikator für Stop-Loss  |
| `tp_mult`       | 4.0     | ATR-Multiplikator für Take-Profit|

**Typische Performance (H1 EUR/USD 2020–2024):**
- Sharpe: 0.6–1.1 | Max DD: 8–18% | Win Rate: 35–45% | Profit Factor: 1.3–1.8

**Ausführen:**
```bash
cd Bot1/forex_strategies && python strategy1_donchian.py
```

---

### Strategie 2 – Multi-Timeframe RSI Pullback (`strategy2_mtf_rsi.py`)

**Konzept:** H4-EMA-Crossover definiert Trendrichtung, M15-RSI bestimmt Entry.
Höhere Trefferquote durch Alignment beider Timeframes.

**Signal-Logik:**
```
# H4-Trend-Filter
trend_up   = EMA(H4, fast=20) > EMA(H4, slow=50)  → auf M15 geforwarded
trend_down = EMA(H4, fast=20) < EMA(H4, slow=50)

# M15-Entry
long_entry  = trend_up   AND RSI(M15, 14) < 35  (Oversold-Pullback im Aufwärtstrend)
short_entry = trend_down AND RSI(M15, 14) > 65  (Overbought-Pullback im Abwärtstrend)
```

**Exit-Logik:**
- Long-Exit:  RSI > 55 ODER Short-Signal
- Short-Exit: RSI < 45 ODER Long-Signal
- SL: 1.5×ATR | TP: 3.0×ATR → RR 1:2

**Tune-Funktion** (`tune()`): Grid-Search über EMA-Perioden [10,15,20,25]×[40,50,60,80]
und RSI-Schwellwerte [30,35,40]×[60,65,70].

**Typische Performance (M15/H4 EUR/USD 2020–2024):**
- Sharpe: 0.9–1.4 | Max DD: 6–14% | Win Rate: 50–60% | Profit Factor: 1.5–2.2

**Ausführen:**
```bash
cd Bot1/forex_strategies && python strategy2_mtf_rsi.py
```

---

### Strategie 3 – Composite Score Optimizer (`strategy3_optimizer.py`)

**Konzept:** EMA-Crossover-System (ähnlich S1) mit vollständigem Grid-Search über 5 Parameter.
Jede Kombination wird mit dem `prop_firm_score()` bewertet – Parametersätze die DD > 8%
verursachen werden disqualifiziert.

**Parameter-Grid:**
```python
PARAM_GRID = {
    "fast_ema":   [8, 10, 15, 20, 25],
    "slow_ema":   [30, 40, 50, 60, 80],
    "atr_period": [10, 14, 20],
    "sl_mult":    [1.5, 2.0, 2.5],
    "rr_ratio":   [2.0, 2.5, 3.0],
}
# → bis zu 5×5×3×3×3 = 675 Kombinationen (minus fast >= slow)
```

**Composite Score** (`prop_firm_score()`):
- Gewichtet: Sharpe Ratio + Profit Factor + SQN
- Disqualifiziert bei: Max DD > 8%, Profit Factor < 1.0, Trade-Anzahl < 10

**Output:** Sortierte DataFrame + `optimizer_results.png` (Heatmap + Scatter + Histogramm)

**Ausführen:**
```bash
cd Bot1/forex_strategies && python strategy3_optimizer.py  # schreibt optimizer_results.png
```

---

### Walk-Forward Validation (`walk_forward.py`)

**Konzept:** Rollierende Train/Test-Splits um Over-Fitting zu erkennen.
Testet ob Parameter aus dem Optimizer auf ungesehenen Daten (OOS) funktionieren.

**Split-Schema:**
```
|─── Train 70% ───|─ Test 15% ─|
        |─── Train 70% ───|─ Test 15% ─|   (Step: 10%)
```

**Beste Parameter eintragen** (aus S3-Optimizer):
```python
BEST_FAST    = 15
BEST_SLOW    = 50
BEST_ATR_P   = 14
BEST_SL_MULT = 2.0
BEST_RR      = 2.5
```

**Bestehens-Kriterien:**
- Profitable Splits ≥ 60%
- Durchschnittlicher OOS-Sharpe ≥ 0.5

**Ausführen:**
```bash
cd Bot1/forex_strategies && python walk_forward.py
```

---

## Prop-Firm-Scoring (`prop_firm_score.py`)

Bewertet jede Strategie gegen Prop-Firm-Mindestanforderungen:

| Metrik        | Disqualifiziert | Akzeptabel | Gut   | Sehr gut |
|---------------|-----------------|------------|-------|----------|
| Sharpe Ratio  | < 0.5           | 0.5–1.0    | 1–2   | > 2.0    |
| Max Drawdown  | > 10%           | 8–10%      | 5–8%  | < 5%     |
| Profit Factor | < 1.3           | 1.3–1.5    | 1.5–2 | > 2.5    |
| SQN           | < 2.0           | 2.0–2.5    | 2.5–3 | > 3.0    |
| Win Rate      | < 35%           | 35–45%     | 45–60%| > 60%    |

---

## Globale Konfiguration (`config.py`)

```python
SYMBOL    = "EURUSD=X"   # Yahoo Finance Symbol (Fallback)
FEES      = 0.00005      # 0.5 Pips pro Trade (round-trip anteilig)
INIT_CASH = 10_000       # Startkapital für Backtests
```

---

## Bot-Loop (`main.py`)

```
ENV laden → Logging setup → DATABENTO_API_KEY prüfen
→ while True:
    tick()   ← Trading-Logik hier einbauen
    sleep(INTERVAL_SECONDS)
```

ENV-Variablen:
- `DATABENTO_API_KEY` – Pflicht für Live-Daten
- `DRY_RUN=true` – kein echtes Trading (Standard)
- `INTERVAL_SECONDS=60` – Tick-Intervall

---

## Docker-Deployment

```bash
# Bauen und starten
docker-compose up -d

# Logs ansehen
docker-compose logs -f

# Container neu starten
docker-compose restart
```

Die `.env`-Datei (Root oder Bot1/) wird automatisch per `docker-compose.yml` eingebunden.

---

## Vollständiger Workflow (Neue Strategie entwickeln)

```bash
# 1. Baseline
python strategy1_donchian.py

# 2. MTF-Filter testen
python strategy2_mtf_rsi.py

# 3. Optimizer auf Train-Daten (H4, 2019–2023)
python strategy3_optimizer.py   # → optimizer_results.png

# 4. Beste Parameter in walk_forward.py eintragen
# 5. Walk-Forward auf 2018–2024
python walk_forward.py

# 6. Prop-Firm-Eignung prüfen (Output von walk_forward.py)
```
