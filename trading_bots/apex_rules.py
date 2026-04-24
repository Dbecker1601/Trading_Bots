from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ApexAccountProfile:
    account_type: str
    account_size: int
    profit_target: float
    max_loss: float
    daily_loss_limit: float | None
    consistency_limit: float = 0.5


@dataclass(frozen=True)
class ApexComplianceReport:
    passed: bool
    violations: list[str]
    reached_profit_target: bool
    trailing_threshold: float


# Based on publicly visible aggregation data (PropFirmApp, accessed 2026-04-24).
# Official Apex pages were Cloudflare-blocked from this runtime, so keep this configurable.
_PROFILE_TABLE: dict[tuple[str, int], ApexAccountProfile] = {
    ("intraday", 25_000): ApexAccountProfile("intraday", 25_000, profit_target=1500.0, max_loss=1000.0, daily_loss_limit=None),
    ("intraday", 50_000): ApexAccountProfile("intraday", 50_000, profit_target=3000.0, max_loss=2000.0, daily_loss_limit=None),
    ("intraday", 100_000): ApexAccountProfile("intraday", 100_000, profit_target=6000.0, max_loss=3000.0, daily_loss_limit=None),
    ("intraday", 150_000): ApexAccountProfile("intraday", 150_000, profit_target=9000.0, max_loss=4000.0, daily_loss_limit=None),
    ("eod", 25_000): ApexAccountProfile("eod", 25_000, profit_target=1500.0, max_loss=1000.0, daily_loss_limit=500.0),
    ("eod", 50_000): ApexAccountProfile("eod", 50_000, profit_target=3000.0, max_loss=2000.0, daily_loss_limit=1000.0),
    ("eod", 100_000): ApexAccountProfile("eod", 100_000, profit_target=6000.0, max_loss=3000.0, daily_loss_limit=1500.0),
    ("eod", 150_000): ApexAccountProfile("eod", 150_000, profit_target=9000.0, max_loss=4000.0, daily_loss_limit=2000.0),
}


def get_apex_profile(account_type: str, account_size: int) -> ApexAccountProfile:
    key = (account_type.lower().strip(), int(account_size))
    if key not in _PROFILE_TABLE:
        raise ValueError(f"Unbekanntes Apex-Profil: {key}")
    return _PROFILE_TABLE[key]


def evaluate_apex_compliance(
    profile: ApexAccountProfile,
    trade_pnls: Iterable[float],
    equity_curve: Iterable[float],
) -> ApexComplianceReport:
    pnls = list(trade_pnls)
    equity = list(equity_curve)
    if not equity:
        raise ValueError("equity_curve darf nicht leer sein")

    violations: list[str] = []

    trailing_threshold = profile.account_size - profile.max_loss
    if min(equity) < trailing_threshold:
        violations.append("max_loss")

    if profile.daily_loss_limit is not None:
        worst_single_day = min([0.0] + pnls)
        if abs(worst_single_day) > profile.daily_loss_limit:
            violations.append("daily_loss_limit")

    positive_days = [p for p in pnls if p > 0]
    if positive_days:
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
