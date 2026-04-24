from dataclasses import asdict
import json
from pathlib import Path
from typing import Iterable

from trading_bots.apex_rules import evaluate_apex_compliance, get_apex_profile
from trading_bots.backtest import BacktestConfig, Trade, run_backtest
from trading_bots.reporting import compute_kpis


def evaluate_trades_for_apex(
    trades: Iterable[Trade],
    backtest_config: BacktestConfig,
    account_type: str,
    account_size: int,
) -> dict:
    trades_list = list(trades)
    profile = get_apex_profile(account_type=account_type, account_size=account_size)
    bt = run_backtest(trades_list, backtest_config)
    kpis = compute_kpis(bt.trade_pnls, bt.equity_curve)
    apex = evaluate_apex_compliance(profile, bt.trade_pnls, bt.equity_curve, trades=trades_list)

    return {
        "account": {
            "type": profile.account_type,
            "size": profile.account_size,
            "profit_target": profile.profit_target,
            "max_loss": profile.max_loss,
            "daily_loss_limit": profile.daily_loss_limit,
            "consistency_limit": profile.consistency_limit,
            "max_contracts": profile.max_contracts,
        },
        "kpis": asdict(kpis),
        "apex": asdict(apex),
        "equity_curve": bt.equity_curve,
        "trade_pnls": bt.trade_pnls,
        "trade_count": len(trades_list),
    }


def export_report_json(report: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def export_report_html(report: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    account = report.get("account", {})
    kpis = report.get("kpis", {})
    apex = report.get("apex", {})

    html = f"""<!doctype html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Trading Bot Report</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; background:#0b1020; color:#e8ecff; margin:0; padding:24px; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
    .card {{ background:#121933; border:1px solid #23305f; border-radius:12px; padding:16px; }}
    h1,h2 {{ margin:0 0 12px 0; }}
    table {{ width:100%; border-collapse:collapse; }}
    td {{ padding:6px 0; border-bottom:1px solid #23305f; }}
    .ok {{ color:#5be37d; font-weight:700; }}
    .bad {{ color:#ff6b6b; font-weight:700; }}
    code {{ color:#9ad1ff; }}
  </style>
</head>
<body>
  <h1>Trading Report</h1>
  <div class=\"grid\">
    <section class=\"card\">
      <h2>Account</h2>
      <table>
        <tr><td>Type</td><td>{account.get('type')}</td></tr>
        <tr><td>Size</td><td>{account.get('size')}</td></tr>
        <tr><td>Profit Target</td><td>{account.get('profit_target')}</td></tr>
        <tr><td>Max Loss</td><td>{account.get('max_loss')}</td></tr>
        <tr><td>Daily Loss Limit</td><td>{account.get('daily_loss_limit')}</td></tr>
        <tr><td>Max Contracts</td><td>{account.get('max_contracts')}</td></tr>
      </table>
    </section>

    <section class=\"card\">
      <h2>KPI Summary</h2>
      <table>
        <tr><td>Total PnL</td><td>{kpis.get('total_pnl')}</td></tr>
        <tr><td>Win Rate</td><td>{kpis.get('win_rate')}</td></tr>
        <tr><td>Profit Factor</td><td>{kpis.get('profit_factor')}</td></tr>
        <tr><td>Max Drawdown</td><td>{kpis.get('max_drawdown')}</td></tr>
        <tr><td>Sharpe-like</td><td>{kpis.get('sharpe_like')}</td></tr>
      </table>
    </section>

    <section class=\"card\">
      <h2>Apex Compliance</h2>
      <p class=\"{'ok' if apex.get('passed') else 'bad'}\">Passed: {apex.get('passed')}</p>
      <p>Violations: <code>{', '.join(apex.get('violations', [])) or 'none'}</code></p>
      <p>Reached Profit Target: {apex.get('reached_profit_target')}</p>
      <p>Trailing Threshold: {apex.get('trailing_threshold')}</p>
    </section>
  </div>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path
