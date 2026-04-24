# MNQ Hybrid-Bot Architektur (Umsetzungsv1)

Ziel: robuste, erweiterbare Trading-Architektur mit klarer Trennung von Signal, Risiko, Execution und Daten.

## Komponenten

- `trading_bots/decision_engine.py`
  - Regime-Erkennung (`trend`, `range`, `risk_off`)
  - Signal + optionales ML-Overlay (`ml_prob_up`)
  - Edge-Filter (Kosten + Puffer)
  - Kill-Switch (Tagesverlust)

- `trading_bots/execution.py`
  - Entry-Planung: `limit` bei engem Spread, sonst `market`

- `trading_bots/market_data.py`
  - Historische Databento-Bars mit Validierung

## Risikoprinzipien

- Kein Trade bei `risk_off` Volatilität
- Kein Trade wenn Tagesverlust-Limit überschritten
- Positionsgröße durch Edge + Volatilitäts-Adjustierung begrenzt

## Erweiterungen (nächste Schritte)

1. Walk-forward Backtest Engine (rolling windows)
2. Realistisches Kostenmodell (Fees + Slippage + Spread)
3. Supervised ML-Overlay (LightGBM/XGBoost)
4. RL als Add-on nur für Sizing/Execution

## Akzeptanzkriterien für nächste Phase

- OOS Sharpe > 1.0
- Profit Factor > 1.2
- Stabilität über mehrere Marktregime
- Drawdown-Grenzen eingehalten
