from dataclasses import dataclass
import datetime as dt
from typing import Iterable

from trading_bots.backtest import Trade


@dataclass(frozen=True)
class ApexAccountProfile:
    account_type: str
    account_size: int
    profit_target: float
    max_loss: float
    daily_loss_limit: float | None
    consistency_limit: float | None = None
    max_contracts: int = 0


@dataclass(frozen=True)
class ApexComplianceReport:
    passed: bool
    violations: list[str]
    reached_profit_target: bool
    trailing_threshold: float


# Intraday Evaluation values reflect Apex's public help-center table accessed 2026-05-17.
# EOD values remain configurable defaults and should be checked against the exact account.
_PROFILE_TABLE: dict[tuple[str, int], ApexAccountProfile] = {
    ("intraday", 25_000): ApexAccountProfile("intraday", 25_000, profit_target=1500.0, max_loss=1000.0, daily_loss_limit=None, max_contracts=4),
    ("intraday", 50_000): ApexAccountProfile("intraday", 50_000, profit_target=3000.0, max_loss=2000.0, daily_loss_limit=None, max_contracts=6),
    ("intraday", 100_000): ApexAccountProfile("intraday", 100_000, profit_target=6000.0, max_loss=3000.0, daily_loss_limit=None, max_contracts=8),
    ("intraday", 150_000): ApexAccountProfile("intraday", 150_000, profit_target=9000.0, max_loss=4000.0, daily_loss_limit=None, max_contracts=12),
    ("eod", 25_000): ApexAccountProfile("eod", 25_000, profit_target=1500.0, max_loss=1000.0, daily_loss_limit=500.0, consistency_limit=0.5, max_contracts=4),
    ("eod", 50_000): ApexAccountProfile("eod", 50_000, profit_target=3000.0, max_loss=2000.0, daily_loss_limit=1000.0, consistency_limit=0.5, max_contracts=10),
    ("eod", 100_000): ApexAccountProfile("eod", 100_000, profit_target=6000.0, max_loss=3000.0, daily_loss_limit=1500.0, consistency_limit=0.5, max_contracts=14),
    ("eod", 150_000): ApexAccountProfile("eod", 150_000, profit_target=9000.0, max_loss=4000.0, daily_loss_limit=2000.0, consistency_limit=0.5, max_contracts=17),
}


def get_apex_profile(account_type: str, account_size: int) -> ApexAccountProfile:
    key = (account_type.lower().strip(), int(account_size))
    if key not in _PROFILE_TABLE:
        raise ValueError(f"Unbekanntes Apex-Profil: {key}")
    return _PROFILE_TABLE[key]


def _daily_pnl_map(trades: list[Trade], trade_pnls: list[float]) -> dict[dt.date, float]:
    by_day: dict[dt.date, float] = {}
    for trade, pnl in zip(trades, trade_pnls):
        day = trade.timestamp.date()
        by_day[day] = by_day.get(day, 0.0) + pnl
    return by_day


def evaluate_apex_compliance(
    profile: ApexAccountProfile,
    trade_pnls: Iterable[float],
    equity_curve: Iterable[float],
    trades: Iterable[Trade] | None = None,
) -> ApexComplianceReport:
    pnls = list(trade_pnls)
    equity = list(equity_curve)
    trade_list = list(trades) if trades is not None else []

    if not equity:
        raise ValueError("equity_curve darf nicht leer sein")

    violations: list[str] = []

    trailing_threshold = profile.account_size - profile.max_loss
    for value in equity:
        if value <= trailing_threshold:
            violations.append("max_loss")
            break
        trailing_threshold = max(trailing_threshold, value - profile.max_loss)

    if profile.max_contracts > 0 and trade_list:
        if any(t.contracts > profile.max_contracts for t in trade_list):
            violations.append("max_contracts")

    if profile.daily_loss_limit is not None:
        if trade_list and len(trade_list) == len(pnls):
            day_pnls = _daily_pnl_map(trade_list, pnls)
            worst_day = min([0.0] + list(day_pnls.values()))
        else:
            worst_day = min([0.0] + pnls)
        if abs(worst_day) > profile.daily_loss_limit:
            violations.append("daily_loss_limit")

    positive_days = [p for p in pnls if p > 0]
    if profile.consistency_limit is not None and positive_days:
        largest_positive = max(positive_days)
        total_positive = sum(positive_days)
        if total_positive > 0 and largest_positive > profile.consistency_limit * total_positive:
            violations.append("consistency_rule")

    reached_profit_target = (equity[-1] - profile.account_size) >= profile.profit_target
    return ApexComplianceReport(
        passed=len(violations) == 0,
        violations=violations,
        reached_profit_target=reached_profit_target,
        trailing_threshold=trailing_threshold,
    )
