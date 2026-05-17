# Algorithmische Forex-Strategien mit VectorBT Pro
### Prop-Firm-kompatibel | Backtestbar | Walk-Forward-validiert

---

## Projektstruktur

```
forex_strategies/
├── config.py              # Globale Einstellungen (Symbol, Fees, Kapital)
├── prop_firm_score.py     # Scoring-Funktion + Report-Dashboard
├── strategy1_donchian.py  # Volatility Breakout (Donchian)
├── strategy2_mtf_rsi.py   # Multi-Timeframe Trend + RSI Pullback
├── strategy3_optimizer.py # Composite Score Optimizer
└── walk_forward.py        # Walk-Forward Validation
```

## Datenquelle: Databento API

Alle Marktdaten werden über die **Databento API** bezogen. Yahoo Finance dient nur als Fallback für erste Tests.

```bash
pip install databento vectorbt[full] ta-lib pandas numpy matplotlib
```

```python
import databento as db

client = db.Historical(api_key="YOUR_API_KEY")

# Beispiel: EURUSD Stundendaten
data = client.timeseries.get_range(
    dataset="FXSPOT",
    symbols=["EUR/USD"],
    schema="ohlcv-1h",
    start="2020-01-01",
    end="2024-01-01",
)
df = data.to_df()
```

Databento-Datasets für Forex:

| Dataset      | Inhalt                        |
|--------------|-------------------------------|
| `FXSPOT`     | Spot-Kurse Major-Pairs        |
| `GLBX.MDP3`  | CME FX Futures (tick-genau)   |
| `IFUS.IMPACT`| ICE FX Futures                |

API-Key in Umgebungsvariable setzen:

```bash
export DATABENTO_API_KEY="your-key-here"
```

## Workflow

1. **Baseline** – Strategie 1 als Referenzpunkt testen
2. **MTF-Filter** – Strategie 2 implementieren und mit Baseline vergleichen
3. **Optimizer** – Strategie 3 auf H4 EUR/USD 2019–2023 (Training) laufen lassen
4. **Walk-Forward** – Beste Parameter auf 2023–2024 (Out-of-Sample) validieren
5. **Report** – Prop-Firm-Eignung entscheiden

```bash
python strategy1_donchian.py
python strategy2_mtf_rsi.py
python strategy3_optimizer.py   # speichert optimizer_results.png
python walk_forward.py          # BEST_* Parameter in walk_forward.py eintragen
```

---

## Verfügbare Forex-Symbole (Yahoo Finance)

| Symbol     | Paar    |
|------------|---------|
| `EURUSD=X` | EUR/USD |
| `GBPUSD=X` | GBP/USD |
| `USDJPY=X` | USD/JPY |
| `AUDUSD=X` | AUD/USD |
| `USDCHF=X` | USD/CHF |
| `NZDUSD=X` | NZD/USD |
| `USDCAD=X` | USD/CAD |

---

## Performance-Benchmarks

| Metrik           | Schwach | Akzeptabel | Gut       | Sehr gut |
|------------------|---------|------------|-----------|----------|
| **Sharpe Ratio** | < 0.5   | 0.5 – 1.0  | 1.0 – 2.0 | > 2.0    |
| **Sortino**      | < 0.8   | 0.8 – 1.5  | 1.5 – 3.0 | > 3.0    |
| **Calmar**       | < 0.5   | 0.5 – 1.0  | 1.0 – 3.0 | > 3.0    |
| **Max Drawdown** | > 30%   | 15 – 30%   | 5 – 15%   | < 5%     |
| **Profit Factor**| < 1.3   | 1.3 – 1.5  | 1.5 – 2.5 | > 2.5    |
| **Win Rate**     | < 35%   | 35 – 45%   | 45 – 60%  | > 60%    |
| **SQN**          | < 2.0   | 2.0 – 2.5  | 2.5 – 3.0 | > 3.0    |

## Win Rate vs. Risk/Reward (Break-Even)

| Win Rate | Benötigtes RR | Systemtyp              |
|----------|---------------|------------------------|
| 30%      | 2.33 : 1      | Trend-Following        |
| 40%      | 1.50 : 1      | Breakout-Systeme       |
| 50%      | 1.00 : 1      | Break-Even             |
| 60%      | 0.67 : 1      | Mean Reversion         |

## Prop-Firm Vergleich

| Firma       | Max DD (gesamt) | Max DD (täglich) | Profit-Ziel |
|-------------|-----------------|------------------|-------------|
| FTMO        | 10%             | 5%               | 10%         |
| The5%ers    | 8%              | –                | 10%         |
| MyFundedFx  | 12%             | 4%               | 10%         |
| E8 Funding  | 8%              | 4%               | 8%          |

## Mindest-Anforderungen Prop-Firm Eignung

```
Sharpe Ratio      > 1.0
Max Drawdown      < 8%
Profit Factor     > 1.4
SQN               > 2.0
Trades (Backtest) > 100
Walk-Forward      > 60% profitable Splits
```

## Typische Ergebnisse

### Strategie 1 – Donchian H1 EUR/USD 2020–2024

| Metrik        | Erwarteter Wert |
|---------------|-----------------|
| Sharpe Ratio  | 0.6 – 1.1       |
| Max Drawdown  | 8 – 18%         |
| Win Rate      | 35 – 45%        |
| Profit Factor | 1.3 – 1.8       |
| SQN           | 1.8 – 2.5       |

### Strategie 2 – MTF RSI M15/H4 EUR/USD 2020–2024

| Metrik        | Erwarteter Wert |
|---------------|-----------------|
| Sharpe Ratio  | 0.9 – 1.4       |
| Max Drawdown  | 6 – 14%         |
| Win Rate      | 50 – 60%        |
| Profit Factor | 1.5 – 2.2       |
| SQN           | 2.2 – 3.0       |
