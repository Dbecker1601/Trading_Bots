from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class KpiReport:
    total_pnl: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_like: float


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        dd = (value - peak)
        if dd < max_dd:
            max_dd = dd
    return max_dd


def compute_kpis(trade_pnls: Iterable[float], equity_curve: Iterable[float]) -> KpiReport:
    pnls = list(trade_pnls)
    eq = list(equity_curve)
    if not eq:
        raise ValueError("equity_curve darf nicht leer sein")

    total_pnl = sum(pnls)
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    win_rate = (len(wins) / len(pnls)) if pnls else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else math.inf

    max_drawdown = _max_drawdown(eq)

    if len(pnls) >= 2:
        mean = total_pnl / len(pnls)
        var = sum((x - mean) ** 2 for x in pnls) / (len(pnls) - 1)
        std = math.sqrt(var)
        sharpe_like = (mean / std) if std > 0 else 0.0
    else:
        sharpe_like = 0.0

    return KpiReport(
        total_pnl=total_pnl,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        sharpe_like=sharpe_like,
    )
