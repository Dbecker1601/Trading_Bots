from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from config import INIT_CASH
from funding_profiles import (
    FundingTrade,
    evaluate_funding_rules,
    evaluate_strategy_quality,
    get_profile,
    profile_to_dict,
)


def _to_series(value: Any) -> pd.Series:
    if hasattr(value, "to_pandas"):
        value = value.to_pandas()
    if isinstance(value, pd.DataFrame):
        if value.shape[1] == 0:
            return pd.Series(dtype=float)
        return value.iloc[:, 0]
    if isinstance(value, pd.Series):
        return value
    return pd.Series(value)


def extract_trade_pnls(portfolio: Any) -> list[float]:
    """Extract closed-trade PnL from VectorBT/VectorBT Pro portfolios."""
    try:
        return [float(x) for x in _to_series(portfolio.trades.pnl).dropna().tolist()]
    except Exception:
        pass
    try:
        return [float(x) for x in portfolio.trades.records["pnl"]]
    except Exception:
        pass
    try:
        records = portfolio.trades.records_readable
        pnl_col = next((c for c in ("PnL", "pnl", "Profit", "profit") if c in records.columns), None)
        if pnl_col:
            return [float(x) for x in records[pnl_col].dropna().tolist()]
    except Exception:
        pass
    return []


def extract_equity_curve(portfolio: Any) -> list[float]:
    """Extract portfolio equity values from VectorBT/VectorBT Pro portfolios."""
    try:
        values = _to_series(portfolio.value()).dropna().astype(float)
        if not values.empty:
            return values.tolist()
    except Exception:
        pass
    try:
        values = _to_series(portfolio.asset_value()).dropna().astype(float)
        if not values.empty:
            return values.tolist()
    except Exception:
        pass
    pnls = extract_trade_pnls(portfolio)
    equity = INIT_CASH
    curve = [equity]
    for pnl in pnls:
        equity += pnl
        curve.append(equity)
    return curve


def _extract_trade_timestamps(portfolio: Any, count: int) -> list[pd.Timestamp]:
    try:
        records = portfolio.trades.records_readable
        for col in ("Exit Timestamp", "Exit time", "Exit Time", "exit_timestamp", "Timestamp"):
            if col in records.columns:
                return list(pd.to_datetime(records[col], utc=True).dropna())[:count]
    except Exception:
        pass
    try:
        index = _to_series(portfolio.value()).index
        if len(index) >= count:
            positions = pd.Series(range(len(index))).iloc[-count:]
            return [pd.Timestamp(index[int(pos)]) for pos in positions]
    except Exception:
        pass
    base = pd.Timestamp("1970-01-01", tz="UTC")
    return [base + pd.Timedelta(days=i) for i in range(count)]


def _scale_to_profile(values: list[float], initial_value: float, account_size: float) -> list[float]:
    if initial_value == 0:
        return values
    scale = account_size / initial_value
    return [account_size + ((value - initial_value) * scale) for value in values]


def evaluate_portfolio_for_funding(
    portfolio: Any,
    profile_key: str,
    strategy_name: str,
    symbol: str,
    min_trades: int = 100,
    min_profit_factor: float = 1.4,
    min_sqn: float = 2.0,
    drawdown_buffer_ratio: float = 0.70,
) -> dict[str, Any]:
    """Evaluate a VectorBT portfolio against strategy-quality and funding gates."""
    profile = get_profile(profile_key)
    raw_pnls = extract_trade_pnls(portfolio)
    raw_equity = extract_equity_curve(portfolio)
    initial_value = raw_equity[0] if raw_equity else INIT_CASH
    scale = profile.account_size / initial_value if initial_value else 1.0

    trade_pnls = [round(pnl * scale, 2) for pnl in raw_pnls]
    equity_curve = [round(v, 2) for v in _scale_to_profile(raw_equity, initial_value, profile.account_size)]
    timestamps = _extract_trade_timestamps(portfolio, len(trade_pnls))
    trades = [
        FundingTrade(timestamp=ts.to_pydatetime(), pnl=pnl, contracts=1)
        for ts, pnl in zip(timestamps, trade_pnls)
    ]

    quality = evaluate_strategy_quality(
        trade_pnls,
        equity_curve,
        min_trades=min_trades,
        min_profit_factor=min_profit_factor,
        min_sqn=min_sqn,
        max_drawdown_buffer=profile.max_loss * drawdown_buffer_ratio,
    )
    funding = evaluate_funding_rules(profile, trade_pnls, equity_curve, trades=trades)

    return {
        "strategy": strategy_name,
        "symbol": symbol,
        "profile": profile_to_dict(profile),
        "quality": asdict(quality),
        "funding": asdict(funding),
        "funding_ready": bool(
            quality.passed_quality_gate
            and funding.passed_rules
            and funding.reached_profit_target
        ),
        "scaling": {
            "raw_initial_equity": round(initial_value, 2),
            "profile_account_size": profile.account_size,
            "scale_factor": round(scale, 6),
        },
        "equity_curve": equity_curve,
        "trade_pnls": trade_pnls,
    }


def export_report_json(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def export_report_html(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = report["profile"]
    quality = report["quality"]
    funding = report["funding"]

    html = f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Funding Evaluation</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #17202a; }}
    table {{ border-collapse: collapse; min-width: 420px; }}
    td, th {{ border-bottom: 1px solid #d7dde5; padding: 8px 10px; text-align: left; }}
    .ok {{ color: #117a37; font-weight: 700; }}
    .bad {{ color: #b42318; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>{report["strategy"]} - {report["symbol"]}</h1>
  <p class="{'ok' if report['funding_ready'] else 'bad'}">Funding Ready: {report['funding_ready']}</p>
  <h2>Profile</h2>
  <table>
    <tr><td>Firm</td><td>{profile['firm']}</td></tr>
    <tr><td>Account</td><td>{profile['account_size']}</td></tr>
    <tr><td>Profit Target</td><td>{profile['profit_target']}</td></tr>
    <tr><td>Max Loss</td><td>{profile['max_loss']}</td></tr>
  </table>
  <h2>Quality</h2>
  <table>
    <tr><td>Trades</td><td>{quality['trade_count']}</td></tr>
    <tr><td>Total PnL</td><td>{quality['total_pnl']}</td></tr>
    <tr><td>Profit Factor</td><td>{quality['profit_factor']}</td></tr>
    <tr><td>SQN</td><td>{quality['sqn']}</td></tr>
    <tr><td>Max Drawdown</td><td>{quality['max_drawdown']}</td></tr>
    <tr><td>Violations</td><td>{', '.join(quality['quality_violations']) or 'none'}</td></tr>
  </table>
  <h2>Funding Rules</h2>
  <table>
    <tr><td>Passed Rules</td><td>{funding['passed_rules']}</td></tr>
    <tr><td>Reached Target</td><td>{funding['reached_profit_target']}</td></tr>
    <tr><td>Trading Days</td><td>{funding['trading_days']}</td></tr>
    <tr><td>Trailing Threshold</td><td>{funding['trailing_threshold']}</td></tr>
    <tr><td>Violations</td><td>{', '.join(funding['violations']) or 'none'}</td></tr>
  </table>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path
