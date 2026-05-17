# CODEX.md – Bot2: MNQ Futures Bot

> **Pflicht:** Bei jeder Änderung an Modulen, Strategien, Parametern oder Architektur
> diese Datei UND `CLAUDE.md` im selben Commit aktualisieren.

---

## Purpose

Bot2 is an **intraday trading system for MNQ (Micro Nasdaq Futures)**.
Core: rule-based Decision Engine + Volume Profile strategy + Apex Prop-Firm compliance checking.
Data: **Databento API**. Tests: **pytest**. CI: **GitHub Actions**.

---

## Package Structure

```
trading_bots/
├── config.py              # Config datapoints
├── databento_client.py    # create_databento_client() – reads key from ENV only
├── market_data.py         # fetch_historical_bars() – validation + error wrapping
├── decision_engine.py     # Regime detection + signal + edge gate + kill switch
├── execution.py           # build_entry_plan() – limit vs market order type
├── backtest.py            # BacktestConfig, Trade, walk_forward_windows()
├── reporting.py           # KPI: Sharpe, Win Rate, Profit Factor, Max DD, SQN
├── apex_rules.py          # Apex account profiles + compliance checks
├── evaluation_pipeline.py # Full report pipeline → JSON + HTML export
├── strategy_v1.py         # Strategy V1: EMA Breakout + Pullback + Range
├── strategy_v2.py         # Strategy V2: Volume Profile HVN/LVN
└── smoke.py               # Smoke tests
```

---

## Decision Engine Data Flow

```
MarketSnapshot + RiskState
        │
        ▼
detect_regime()
  realized_vol >= 0.02            → "risk_off"  (no trading)
  |ema_fast - ema_slow| >= 8.0
    AND returns_5m aligned        → "trend"
  else                            → "range"
        │
        ▼
Signal scoring (rule-based) [0.0 – 1.0]
  + optional ml_prob_up overlay
        │
        ▼
Edge Gate: edge_bps = signal × max_edge_bps
  Trade only if: edge_bps > 4.0 (costs) + 1.0 (buffer) = 5.0 bps
        │
        ▼
Kill Switch: daily_pnl < -500 → action = "hold"
        │
        ▼
Position sizing: vol_target=0.01, scale 1→3 contracts with edge
        │
        ▼
TradeDecision(action, target_position, regime, signal_score, edge_bps, reason)
        │
        ▼
build_entry_plan()
  spread_bps <= 2.0 → limit order
  spread_bps >  2.0 → market order
```

---

## Strategy V1 – Baseline

**Three setup types:**

| Setup | Signal | Entry Condition |
|-------|--------|-----------------|
| Breakout | Trend | close > rolling_max(high, 20) → Long |
| Pullback | Trend | after breakout, price returns ≤ 0.75×ATR to EMA |
| Range | Mean-reversion | Z-Score(close vs range-mean) > 1.2, Vol ≤ threshold |

**Position management:**
- TP1 at 1.0×R → partial close + trail to break-even
- Trailing stop: 2.0×ATR
- Min hold: 3 bars, Max hold: 45 bars
- Loss streak: after 2 consecutive losses → 50% size reduction

**Key config fields (`StrategyV1Config`):**
```python
ema_fast=20, ema_slow=100            # trend EMAs
breakout_lookback=20                 # N-bar high/low
stop_atr_mult=1.2, tp1_r_multiple=1.0, trailing_atr_mult=2.0
max_hold_bars=45, min_hold_bars=3
risk_per_trade=0.003                 # 0.3% of equity
max_daily_loss=-500.0                # kill switch
session_start_utc_minute=810         # 13:30 UTC
session_end_utc_minute=1200          # 20:00 UTC
point_value=2.0                      # $ per point per MNQ contract
max_spread_bps_for_entry=3.0
```

---

## Strategy V2 – Volume Profile

**Core concept:** Build daily volume profile from 1-min bars.
- **HVN** (High Volume Node ≥ 70th pct): Support/resistance zones
- **LVN** (Low Volume Node ≤ 30th pct): Fast transit zones

**Volume profile construction:**
```python
# 1. Bin prices into 1.0-point bins
# 2. Accumulate volume per bin (close-volume pairs)
# 3. Apply 3-bar moving average smoothing
# 4. Threshold: hvn_quantile=0.70, lvn_quantile=0.30
# 5. Extract contiguous regions → edges
```

**Two setups:**

**Setup A – HVN Edge:**
```python
# Price approaches HVN edge within edge_tolerance_points=2.0
# AND vol_z_score >= volz_edge_threshold=0.5
→ Short at HVN top edge, Long at HVN bottom edge
hold_bars = 12
```

**Setup B – LVN Rejection:**
```python
# Price touches LVN within lvn_tolerance_points=1.5
# AND rejection candle (close < open for short)
# AND vol_z_score >= volz_lvn_threshold=0.8
→ Short above LVN (rejection), Long below LVN
hold_bars = 15
```

**V2.1 filters:**
```python
short_only = True                              # only short trades (default)
allowed_short_hours_utc = (14, 15, 17, 19)    # restricted entry hours
min_entry_gap_bars = 20                        # cooldown between trades
max_spread_bps_for_entry = 3.0               # spread filter
daily_bias_lookback_bars = 30                  # trend bias window
```

**Key config (`StrategyV2Config`):**
```python
bin_size=1.0, hvn_quantile=0.70, lvn_quantile=0.30
edge_tolerance_points=2.0, lvn_tolerance_points=1.5
volz_edge_threshold=0.5, volz_lvn_threshold=0.8
hold_bars_edge=12, hold_bars_lvn=15
session_start_utc_minute=810, session_end_utc_minute=1200
```

---

## Apex Compliance (`apex_rules.py`)

Current implementation notes:
- `env.py` loads the repo `.env` without logging secret values.
- Apex 50k Intraday Evaluation uses `max_contracts=6`.
- Intraday trailing drawdown is evaluated dynamically from the equity peak.
- Consistency is profile-specific and is not applied to Intraday Evaluation profiles.

**Account profiles** (PropFirmApp data, 2026-04-24 – verify before live use):

```python
("intraday", 50_000): profit_target=3000, max_loss=2000, daily_loss=None,  max_contracts=6
("eod",      50_000): profit_target=3000, max_loss=2000, daily_loss=1000,  max_contracts=10
```

**Compliance checks:**
```python
def check_apex_compliance(trades, equity_curve, profile) -> ApexComplianceReport:
    # 1. Trailing threshold: min(equity) >= peak_equity - max_loss
    # 2. Daily loss limit (eod only): no day below daily_loss_limit
    # 3. Max contracts: no trade exceeds max_contracts
    # 4. Consistency: configurable; not applied to Intraday Evaluation profiles
    return ApexComplianceReport(passed, violations, reached_profit_target, trailing_threshold)
```

---

## Backtest Pipeline

```python
from trading_bots.backtest import BacktestConfig, Trade
from trading_bots.evaluation_pipeline import evaluate_trades_for_apex, export_report_json, export_report_html

config = BacktestConfig(
    initial_equity=50_000.0,
    fee_bps=0.5,           # one-way commission
    slippage_bps=0.5,      # estimated slippage
    point_value=2.0,       # $ per MNQ point
)
report = evaluate_trades_for_apex(trades, config, account_type="intraday", account_size=50_000)
export_report_json(report, "reports/report.json")
export_report_html(report, "reports/report.html")
```

---

## Scripts Quick Reference

```bash
# Run strategies
python scripts/run_strategy_v1.py
python scripts/run_strategy_v2.py

# Walk-forward testing
python scripts/run_strategy_v2_3_walkforward.py
python scripts/run_strategy_v2_3d_walkforward_step10_dedup.py   # most refined

# Forward OOS (final validation)
python scripts/run_strategy_v2_4_forward_oos.py

# Visualizations
python scripts/make_trade_decision_profile_chart.py

# API health check
python scripts/smoke_test_databento.py
```

---

## Test Suite

```bash
pytest tests/ -v                          # all tests
pytest tests/test_strategy_v2.py -v      # V2 unit tests
pytest tests/test_apex_rules.py -v       # compliance tests
pytest tests/test_decision_engine.py -v  # engine tests
```

**CI:** `ci.yml` runs on every push. `databento-smoke.yml` validates API access.

---

## ENV Variables

```
DATABENTO_API_KEY   required – never log, never commit
```

---

## Sync Rule

**On every change to modules, strategies, parameters, or architecture:**
1. Update this file (`CODEX.md`)
2. Update `CLAUDE.md` in the same commit
3. Update root `CLAUDE.md` + root `CODEX.md` if project structure changed
