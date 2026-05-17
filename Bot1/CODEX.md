# CODEX.md – Bot1: Forex Strategies

> **Pflicht:** Bei jeder Änderung an Strategie-Logik, Parametern, Modulen oder Abhängigkeiten
> diese Datei UND `CLAUDE.md` im selben Commit aktualisieren.

---

## Purpose

Bot1 implements **rule-based Forex trading strategies** optimized for Prop-Firm challenges
and validated via walk-forward testing. Backtest engine: **VectorBT Pro**.
Data source: **Databento API** (Yahoo Finance as fallback for development).

---

## File Map

| File | Role |
|------|------|
| `main.py` | Production bot loop, Docker entry point |
| `Dockerfile` / `docker-compose.yml` | Container deployment |
| `requirements.txt` | vectorbt[full], ta-lib, pandas, numpy, databento, python-dotenv |
| `benchmark.py` | Runs all strategies, writes `logs/benchmark_results.csv` |
| `forex_strategies/config.py` | Constants: `SYMBOL`, `FEES`, `INIT_CASH` |
| `forex_strategies/prop_firm_score.py` | Scoring fn + dashboard printer |
| `forex_strategies/strategy1_donchian.py` | Donchian Channel Breakout |
| `forex_strategies/strategy2_mtf_rsi.py` | Multi-Timeframe RSI Pullback |
| `forex_strategies/strategy3_optimizer.py` | Grid-search optimizer |
| `forex_strategies/walk_forward.py` | Walk-forward validation |

---

## Strategy 1 – Donchian Channel Breakout

**Entry logic:**
```python
long_entry  = close > rolling_max(high, N=20).shift(1)   # breakout above N-bar high
short_entry = close < rolling_min(low,  N=20).shift(1)   # breakdown below N-bar low
```

**Exit logic:**
```python
sl_stop = ATR(14) * 2.0 / close    # Stop-Loss
tp_stop = ATR(14) * 4.0 / close    # Take-Profit  (RR = 1:2)
# Cross-exit: long exits on short signal, short exits on long signal
```

**Key parameters:** `channel_window=20`, `atr_period=14`, `sl_mult=2.0`, `tp_mult=4.0`

**Run:** `python forex_strategies/strategy1_donchian.py`

---

## Strategy 2 – Multi-Timeframe RSI Pullback

**Timeframes:** H4 (trend filter) + M15 (entry)

**Entry logic:**
```python
# H4 trend detection
trend_up   = EMA(H4_close, 20) > EMA(H4_close, 50)   # forwarded to M15 index
trend_down = EMA(H4_close, 20) < EMA(H4_close, 50)

# M15 entry
long_entry  = trend_up   & (RSI(M15, 14) < 35)   # oversold pullback in uptrend
short_entry = trend_down & (RSI(M15, 14) > 65)   # overbought pullback in downtrend

# M15 exit
long_exit  = (RSI > 55) | short_entry
short_exit = (RSI < 45) | long_entry
```

**Tune function** (`tune(data_h4, data_m15)`): Grid search over EMA and RSI params, returns sorted DataFrame.

**Key parameters:** `ema_fast=20`, `ema_slow=50`, `rsi_os=35`, `rsi_ob=65`, `sl_mult=1.5`, `tp_mult=3.0`

**Run:** `python forex_strategies/strategy2_mtf_rsi.py`

---

## Strategy 3 – Composite Score Optimizer

**Signal:** EMA crossover (same as Strategy 1 skeleton). Grid searches 5 parameters:
```python
PARAM_GRID = {
    "fast_ema":   [8, 10, 15, 20, 25],
    "slow_ema":   [30, 40, 50, 60, 80],
    "atr_period": [10, 14, 20],
    "sl_mult":    [1.5, 2.0, 2.5],
    "rr_ratio":   [2.0, 2.5, 3.0],
}
```

**Scoring:** `prop_firm_score(portfolio)` → composite of Sharpe + PF + SQN.
Disqualified if `max_drawdown > 8%` or `profit_factor < 1.0` or `trade_count < 10`.

**Output:** Sorted results DataFrame + `optimizer_results.png` (heatmap, scatter, histogram).

**Run:** `python forex_strategies/strategy3_optimizer.py`

---

## Walk-Forward Validation

**Split scheme (rolling windows):**
```
Train 70% | Test 15% |
           Train 70% | Test 15% |   Step: 10%
```

**Pass criteria:**
- Profitable splits ≥ 60%
- Mean OOS Sharpe ≥ 0.5

**Before running:** Set best parameters from optimizer in `walk_forward.py`:
```python
BEST_FAST = 15; BEST_SLOW = 50; BEST_ATR_P = 14; BEST_SL_MULT = 2.0; BEST_RR = 2.5
```

**Run:** `python forex_strategies/walk_forward.py`

---

## Prop-Firm Scoring Logic

```python
def prop_firm_score(pf) -> float:
    # Disqualifiers
    if abs(pf.max_drawdown()) > 0.08: return 0.0
    if pf.trades.profit_factor() < 1.0: return 0.0
    if pf.trades.count() < 10: return 0.0
    # Weighted composite
    return (
        0.40 * min(pf.sharpe_ratio() / 2.0, 1.0) +
        0.35 * min((pf.trades.profit_factor() - 1.0) / 1.5, 1.0) +
        0.25 * min(pf.trades.sqn() / 3.0, 1.0)
    )
```

---

## Global Config (`config.py`)

```python
SYMBOL    = "EURUSD=X"   # Yahoo Finance ticker (Databento for production)
FEES      = 0.00005      # ~0.5 pip per trade (one-way portion)
INIT_CASH = 10_000       # Backtest starting capital
```

---

## ENV Variables (Bot Loop)

```
DATABENTO_API_KEY   required – live market data
DRY_RUN             "true" (default) | "false"
INTERVAL_SECONDS    tick interval, default 60
```

---

## Docker

```bash
docker-compose up -d          # start bot container
docker-compose logs -f        # stream logs
docker-compose down           # stop
```

---

## Sync Rule

**On every change to strategy logic, parameters, modules, or dependencies:**
1. Update this file (`CODEX.md`)
2. Update `CLAUDE.md` in the same commit
3. Update root `CLAUDE.md` + root `CODEX.md` if project structure changed
