from dataclasses import asdict
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
    profile = get_apex_profile(account_type=account_type, account_size=account_size)
    bt = run_backtest(trades, backtest_config)
    kpis = compute_kpis(bt.trade_pnls, bt.equity_curve)
    apex = evaluate_apex_compliance(profile, bt.trade_pnls, bt.equity_curve)

    return {
        "kpis": asdict(kpis),
        "apex": asdict(apex),
        "equity_curve": bt.equity_curve,
        "trade_pnls": bt.trade_pnls,
    }
