from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class FundingProfile:
    key: str
    firm: str
    market: str
    account_type: str
    account_size: float
    profit_target: float
    verification_target: float | None
    max_loss: float
    daily_loss_limit: float | None
    min_trading_days: int
    max_contracts: int | None = None
    consistency_limit: float | None = None
    trailing_mode: str = "static"
    access_days: int | None = None


@dataclass(frozen=True)
class FundingTrade:
    timestamp: dt.datetime
    pnl: float
    contracts: int = 1


@dataclass(frozen=True)
class FundingRuleReport:
    passed_rules: bool
    reached_profit_target: bool
    violations: list[str]
    trailing_threshold: float | None
    trading_days: int


@dataclass(frozen=True)
class StrategyQualityReport:
    trade_count: int
    total_pnl: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sqn: float
    passed_quality_gate: bool
    quality_violations: list[str]


PROFILES: dict[str, FundingProfile] = {
    "APEX_50K_INTRADAY": FundingProfile(
        key="APEX_50K_INTRADAY",
        firm="Apex Trader Funding",
        market="6E",
        account_type="intraday_evaluation",
        account_size=50_000.0,
        profit_target=3_000.0,
        verification_target=None,
        max_loss=2_000.0,
        daily_loss_limit=None,
        min_trading_days=0,
        max_contracts=6,
        consistency_limit=None,
        trailing_mode="intraday_trailing",
        access_days=30,
    ),
    "FTMO_100K_2STEP": FundingProfile(
        key="FTMO_100K_2STEP",
        firm="FTMO",
        market="EURUSD",
        account_type="two_step_challenge",
        account_size=100_000.0,
        profit_target=10_000.0,
        verification_target=5_000.0,
        max_loss=10_000.0,
        daily_loss_limit=5_000.0,
        min_trading_days=4,
        max_contracts=None,
        consistency_limit=None,
        trailing_mode="static",
        access_days=None,
    ),
    "FTMO_25K_2STEP": FundingProfile(
        key="FTMO_25K_2STEP",
        firm="FTMO",
        market="EURUSD",
        account_type="two_step_challenge",
        account_size=25_000.0,
        profit_target=2_500.0,
        verification_target=1_250.0,
        max_loss=2_500.0,
        daily_loss_limit=1_250.0,
        min_trading_days=4,
        max_contracts=None,
        consistency_limit=None,
        trailing_mode="static",
        access_days=None,
    ),
}


def get_profile(key: str) -> FundingProfile:
    try:
        return PROFILES[key.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown funding profile: {key}") from exc


def _max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return max_dd


def _profit_factor(pnls: list[float]) -> float:
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    if gross_loss == 0:
        return math.inf if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def compute_sqn(pnls: Iterable[float]) -> float:
    values = list(pnls)
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((p - mean) ** 2 for p in values) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return math.sqrt(n) * mean / std


def evaluate_strategy_quality(
    trade_pnls: Iterable[float],
    equity_curve: Iterable[float],
    min_trades: int = 100,
    min_profit_factor: float = 1.4,
    min_sqn: float = 2.0,
    max_drawdown_buffer: float | None = None,
) -> StrategyQualityReport:
    pnls = list(trade_pnls)
    equity = list(equity_curve)
    wins = [p for p in pnls if p > 0]

    total_pnl = sum(pnls)
    win_rate = len(wins) / len(pnls) if pnls else 0.0
    profit_factor = _profit_factor(pnls)
    max_dd = _max_drawdown(equity)
    sqn = compute_sqn(pnls)

    violations: list[str] = []
    if len(pnls) < min_trades:
        violations.append("min_trades")
    if profit_factor < min_profit_factor:
        violations.append("profit_factor")
    if sqn < min_sqn:
        violations.append("sqn")
    if max_drawdown_buffer is not None and abs(max_dd) > max_drawdown_buffer:
        violations.append("drawdown_buffer")

    return StrategyQualityReport(
        trade_count=len(pnls),
        total_pnl=round(total_pnl, 2),
        win_rate=round(win_rate, 4),
        profit_factor=round(profit_factor, 4) if math.isfinite(profit_factor) else math.inf,
        max_drawdown=round(max_dd, 2),
        sqn=round(sqn, 4),
        passed_quality_gate=not violations,
        quality_violations=violations,
    )


def evaluate_funding_rules(
    profile: FundingProfile,
    trade_pnls: Iterable[float],
    equity_curve: Iterable[float],
    trades: Iterable[FundingTrade] | None = None,
) -> FundingRuleReport:
    pnls = list(trade_pnls)
    equity = list(equity_curve)
    trade_list = list(trades) if trades is not None else []
    if not equity:
        raise ValueError("equity_curve must not be empty")

    violations: list[str] = []
    initial = profile.account_size
    trailing_threshold: float | None = None

    if profile.trailing_mode == "intraday_trailing":
        trailing_threshold = initial - profile.max_loss
        for value in equity:
            if value <= trailing_threshold:
                violations.append("max_loss")
                break
            trailing_threshold = max(trailing_threshold, value - profile.max_loss)
    else:
        threshold = initial - profile.max_loss
        trailing_threshold = threshold
        if min(equity) <= threshold:
            violations.append("max_loss")

    if profile.daily_loss_limit is not None and trade_list:
        daily_pnl: dict[dt.date, float] = {}
        for trade in trade_list:
            daily_pnl[trade.timestamp.date()] = daily_pnl.get(trade.timestamp.date(), 0.0) + trade.pnl
        if daily_pnl and min(daily_pnl.values()) <= -profile.daily_loss_limit:
            violations.append("daily_loss_limit")

    if profile.max_contracts is not None and trade_list:
        if any(trade.contracts > profile.max_contracts for trade in trade_list):
            violations.append("max_contracts")

    trading_days = len({trade.timestamp.date() for trade in trade_list})
    if profile.min_trading_days and trading_days < profile.min_trading_days:
        violations.append("min_trading_days")

    if profile.consistency_limit is not None and trade_list:
        daily_profit: dict[dt.date, float] = {}
        for trade in trade_list:
            day = trade.timestamp.date()
            daily_profit[day] = daily_profit.get(day, 0.0) + trade.pnl
        positive_days = [p for p in daily_profit.values() if p > 0]
        total_positive = sum(positive_days)
        if total_positive > 0 and max(positive_days) > profile.consistency_limit * total_positive:
            violations.append("consistency_rule")

    reached_profit_target = (equity[-1] - initial) >= profile.profit_target
    return FundingRuleReport(
        passed_rules=not violations,
        reached_profit_target=reached_profit_target,
        violations=violations,
        trailing_threshold=round(trailing_threshold, 2) if trailing_threshold is not None else None,
        trading_days=trading_days,
    )


def profile_to_dict(profile: FundingProfile) -> dict:
    return asdict(profile)
