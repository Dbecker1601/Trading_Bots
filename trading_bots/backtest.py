from dataclasses import dataclass
import datetime as dt
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Trade:
    timestamp: dt.datetime
    side: str
    contracts: int
    entry: float
    exit: float


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float
    fee_bps: float = 0.5
    slippage_bps: float = 0.5
    point_value: float = 2.0


@dataclass(frozen=True)
class BacktestResult:
    trade_pnls: list[float]
    equity_curve: list[float]


def apply_costs(gross_pnl: float, notional: float, fee_bps: float, slippage_bps: float) -> float:
    total_bps = fee_bps + slippage_bps
    cost = notional * (total_bps / 10_000.0)
    return gross_pnl - cost


def walk_forward_windows(
    items: Sequence[object],
    train_size: int,
    test_size: int,
    step: int,
) -> list[tuple[list[object], list[object]]]:
    if train_size <= 0 or test_size <= 0 or step <= 0:
        raise ValueError("train_size/test_size/step müssen > 0 sein")

    windows: list[tuple[list[object], list[object]]] = []
    start = 0
    n = len(items)
    while start + train_size + test_size <= n:
        train = list(items[start : start + train_size])
        test = list(items[start + train_size : start + train_size + test_size])
        windows.append((train, test))
        start += step
    return windows


def _gross_trade_pnl(trade: Trade, point_value: float) -> float:
    direction = 1.0 if trade.side.lower() == "long" else -1.0
    points = (trade.exit - trade.entry) * direction
    return points * point_value * trade.contracts


def run_backtest(trades: Iterable[Trade], config: BacktestConfig) -> BacktestResult:
    equity = config.initial_equity
    equity_curve = [equity]
    trade_pnls: list[float] = []

    for trade in trades:
        gross = _gross_trade_pnl(trade, config.point_value)
        notional = abs(trade.entry * trade.contracts * config.point_value)
        net = apply_costs(gross, notional, config.fee_bps, config.slippage_bps)
        trade_pnls.append(net)
        equity += net
        equity_curve.append(equity)

    return BacktestResult(trade_pnls=trade_pnls, equity_curve=equity_curve)
