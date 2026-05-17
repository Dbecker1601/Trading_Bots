# Trading_Bots

## Databento API Key sicher hinterlegen

Lokale Entwicklung (optional):
1. Kopiere die Vorlage:
   cp .env.example .env
2. Trage deinen echten Key in `.env` ein:
   DATABENTO_API_KEY=dein_e..._key

GitHub Actions (empfohlen, damit kein `.env` im Repo nötig ist):
1. Öffne das Repo auf GitHub.
2. Gehe zu: Settings -> Secrets and variables -> Actions.
3. Klicke auf "New repository secret".
4. Name: `DATABENTO_API_KEY`
5. Value: dein echter Databento-Key

Danach nutzt der Workflow den Key automatisch über:
- `${{ secrets.DATABENTO_API_KEY }}` -> Environment-Variable `DATABENTO_API_KEY`

Wichtig:
- `.env` ist in `.gitignore` und wird nicht ins Repo gepusht.
- Lege niemals echte Keys in `README.md`, `.env.example` oder Source-Code ab.

## Python-Nutzung (ENV-only, ohne Key-Logging)

```python
from trading_bots.databento_client import create_databento_client

client = create_databento_client()
# client jetzt für Historical-Requests verwenden
```

Hinweise:
- `create_databento_client()` liest den Key intern über `DATABENTO_API_KEY`.
- Der Key wird nicht aus dem Code gelesen und nicht geloggt.
- Falls das Databento-SDK fehlt: `pip install databento`.

## Beispiel: Historische MNQ-Bars abrufen

```python
import datetime as dt

from trading_bots.databento_client import create_databento_client
from trading_bots.market_data import fetch_historical_bars

client = create_databento_client()

bars = fetch_historical_bars(
    client=client,
    symbols=["MNQ.c.0"],
    start=dt.datetime(2026, 4, 1, 9, 30),
    end=dt.datetime(2026, 4, 1, 16, 0),
)
```

## Ziel-Architektur (Hybrid: Regeln + ML-Overlay + Risiko + Execution)

1) Decision Engine (`trading_bots/decision_engine.py`)
- Regime-Erkennung: `trend`, `range`, `risk_off`
- Signalbildung (regelbasiert) + optionales ML-Overlay (`ml_prob_up`)
- Edge-Gate: Trade nur wenn erwarteter Edge > Kosten + Sicherheitspuffer
- Kill-Switch: kein Trade bei Tagesverlust-Limit

2) Execution (`trading_bots/execution.py`)
- Enge Spreads -> bevorzugt `limit`
- Weite Spreads -> `market`
- Ausgangspunkt für spätere RL-Execution-Optimierung

3) Markt-Daten (`trading_bots/market_data.py`)
- Historische Bars via Databento
- Validierung + Fehler-Wrapping

## Schnelles Entscheidungsbeispiel

```python
from trading_bots.decision_engine import DecisionConfig, MarketSnapshot, RiskState, generate_trade_decision
from trading_bots.execution import build_entry_plan

config = DecisionConfig()
snapshot = MarketSnapshot(
    returns_1m=0.0008,
    returns_5m=0.0030,
    ema_fast=20040,
    ema_slow=20000,
    realized_vol=0.008,
    atr_points=18,
    spread_bps=1.2,
    session_minute=95,
)
risk_state = RiskState(current_position=0, daily_pnl=120.0)

decision = generate_trade_decision(snapshot, risk_state, config, ml_prob_up=0.62)
if decision.action in {"long", "short"}:
    entry_plan = build_entry_plan(decision.action, spread_bps=snapshot.spread_bps)
    # hier Order-Router aufrufen
```

## Walk-forward Backtest + KPI + Apex-Regelcheck

Neue Module:
- `trading_bots/backtest.py` → Kostenmodell, Trade-Simulation, Walk-forward-Fenster
- `trading_bots/reporting.py` → KPI-Berechnung (Win-Rate, Profit Factor, Max Drawdown, Sharpe-like)
- `trading_bots/apex_rules.py` → Apex-Profile + Regelprüfung (Trailing Threshold, Daily Loss per Handelstag, Max Contracts, Consistency)
- `trading_bots/evaluation_pipeline.py` → kombinierter Report (Backtest + KPI + Apex Compliance) + JSON/HTML Export

Beispiel:

```python
import datetime as dt

from trading_bots.backtest import BacktestConfig, Trade
from trading_bots.evaluation_pipeline import evaluate_trades_for_apex, export_report_json, export_report_html

trades = [
    Trade(timestamp=dt.datetime(2026, 4, 1, 9, 31), side="long", contracts=1, entry=20000.0, exit=20003.0),
    Trade(timestamp=dt.datetime(2026, 4, 1, 10, 0), side="short", contracts=1, entry=20005.0, exit=20000.0),
]

report = evaluate_trades_for_apex(
    trades=trades,
    backtest_config=BacktestConfig(initial_equity=50_000.0, fee_bps=0.5, slippage_bps=0.5, point_value=2.0),
    account_type="intraday",
    account_size=50_000,
)

json_path = export_report_json(report, "reports/report.json")
html_path = export_report_html(report, "reports/report.html")
print(json_path, html_path)
```

Apex-Hinweis:
- Offizielle Apex-Seiten waren aus dieser Runtime durch Cloudflare geblockt.
- Die Default-Werte in `apex_rules.py` basieren auf öffentlich sichtbaren Aggregator-Daten (PropFirmApp, Stand Abruf 2026-04-24).
- Bitte vor Live-Nutzung die Werte mit deinen exakten Apex-Konto-Regeln abgleichen.

## Nächste sinnvolle Ausbaustufen

- ML-Overlay (z. B. LightGBM) für bessere Trade-Filterung
- RL erst als Phase 3: Position Sizing / Execution, nicht primär Richtungsvorhersage
- Intraday-Session-Filter + News-Filter + Contract-Limit pro Konto

