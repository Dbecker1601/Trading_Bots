from __future__ import annotations

from dataclasses import dataclass
import csv
import datetime as dt
import math
from pathlib import Path
from typing import Any

from trading_bots.backtest import BacktestConfig, Trade, walk_forward_windows
from trading_bots.evaluation_pipeline import evaluate_trades_for_apex, export_report_html, export_report_json


@dataclass(frozen=True)
class Bar:
    timestamp: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread_bps: float = 1.0


@dataclass(frozen=True)
class StrategyV1Config:
    ema_fast: int = 20
    ema_slow: int = 100
    breakout_lookback: int = 20
    pullback_lookback: int = 5
    pullback_atr_tolerance: float = 0.75
    range_lookback: int = 20
    range_zscore_entry: float = 1.2
    atr_period: int = 14
    vol_lookback: int = 30
    risk_off_vol_threshold: float = 0.0028
    trend_threshold_points: float = 6.0

    stop_atr_mult: float = 1.2
    tp1_r_multiple: float = 1.0
    trailing_atr_mult: float = 2.0
    min_hold_bars: int = 3
    max_hold_bars: int = 45

    session_start_utc_minute: int = 13 * 60 + 30
    session_end_utc_minute: int = 20 * 60
    no_new_entries_last_minutes: int = 10

    max_daily_loss: float = -500.0
    max_contracts: int = 5
    risk_per_trade: float = 0.003
    loss_streak_reduce_after: int = 2
    reduced_size_multiplier: float = 0.5

    estimated_cost_bps: float = 4.0
    safety_buffer_bps: float = 1.0
    max_spread_bps_for_entry: float = 3.0
    point_value: float = 2.0


@dataclass
class _Position:
    side: str
    entry_time: dt.datetime
    entry_price: float
    entry_atr: float
    contracts_open: int
    initial_contracts: int
    bars_held: int = 0
    tp1_taken: bool = False
    trail_stop: float | None = None
    lowest_close: float | None = None
    highest_close: float | None = None


def _ema(values: list[float], period: int) -> float:
    if period <= 1:
        return values[-1]
    alpha = 2.0 / (period + 1.0)
    ema = values[0]
    for v in values[1:]:
        ema = (alpha * v) + ((1.0 - alpha) * ema)
    return ema


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(var)


def _atr(bars: list[Bar]) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(bars)):
        cur = bars[i]
        prev_close = bars[i - 1].close
        tr = max(cur.high - cur.low, abs(cur.high - prev_close), abs(cur.low - prev_close))
        trs.append(tr)
    return _mean(trs) if trs else 0.0


def _minute_of_day(ts: dt.datetime) -> int:
    if ts.tzinfo is not None:
        ts = ts.astimezone(dt.timezone.utc)
    return ts.hour * 60 + ts.minute


def _in_session(ts: dt.datetime, cfg: StrategyV1Config) -> bool:
    m = _minute_of_day(ts)
    return cfg.session_start_utc_minute <= m < cfg.session_end_utc_minute


def _new_entries_allowed(ts: dt.datetime, cfg: StrategyV1Config) -> bool:
    m = _minute_of_day(ts)
    return cfg.session_start_utc_minute <= m < (cfg.session_end_utc_minute - cfg.no_new_entries_last_minutes)


def _regime(closes: list[float], cfg: StrategyV1Config) -> str:
    if len(closes) < max(cfg.ema_slow, cfg.vol_lookback) + 1:
        return "warmup"
    returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
    vol = _std(returns[-cfg.vol_lookback :])
    if vol >= cfg.risk_off_vol_threshold:
        return "risk_off"

    ema_fast = _ema(closes[-cfg.ema_fast :], cfg.ema_fast)
    ema_slow = _ema(closes[-cfg.ema_slow :], cfg.ema_slow)
    if abs(ema_fast - ema_slow) >= cfg.trend_threshold_points:
        return "trend"
    return "range"


def _edge_ok(signal_points: float, price: float, cfg: StrategyV1Config) -> bool:
    if price <= 0:
        return False
    edge_bps = abs(signal_points) / price * 10_000.0
    return edge_bps > (cfg.estimated_cost_bps + cfg.safety_buffer_bps)


def _contracts_for_trade(equity: float, atr: float, cfg: StrategyV1Config, consecutive_losses: int) -> int:
    risk_budget = max(0.0, equity * cfg.risk_per_trade)
    stop_points = max(atr * cfg.stop_atr_mult, 0.25)
    risk_per_contract = stop_points * cfg.point_value
    contracts = int(risk_budget / risk_per_contract) if risk_per_contract > 0 else 0
    contracts = max(1, min(cfg.max_contracts, contracts))
    if consecutive_losses >= cfg.loss_streak_reduce_after:
        contracts = max(1, int(math.floor(contracts * cfg.reduced_size_multiplier)))
    return contracts


def generate_trades_v1(bars: list[Bar], cfg: StrategyV1Config, return_decisions: bool = False) -> dict[str, Any]:
    if len(bars) < 3:
        return {"trades": [], "decisions": []}

    trades: list[Trade] = []
    decisions: list[str] = []

    equity_for_sizing = 50_000.0
    position: _Position | None = None
    daily_realized: dict[dt.date, float] = {}
    consecutive_losses = 0

    for i in range(1, len(bars) - 1):
        current = bars[i]
        next_bar = bars[i + 1]
        history = bars[: i + 1]
        closes = [b.close for b in history]

        day = current.timestamp.date()
        day_pnl = daily_realized.get(day, 0.0)
        kill_switch = day_pnl <= cfg.max_daily_loss

        atr = _atr(history[-cfg.atr_period - 1 :])
        regime = _regime(closes, cfg)

        if position is not None:
            position.bars_held += 1
            position.highest_close = current.close if position.highest_close is None else max(position.highest_close, current.close)
            position.lowest_close = current.close if position.lowest_close is None else min(position.lowest_close, current.close)

            direction = 1.0 if position.side == "long" else -1.0
            risk_points = max(position.entry_atr * cfg.stop_atr_mult, 0.25)
            pnl_points = (current.close - position.entry_price) * direction

            if position.side == "long":
                stop_price = position.entry_price - risk_points
                if position.trail_stop is None:
                    position.trail_stop = stop_price
                else:
                    position.trail_stop = max(position.trail_stop, position.highest_close - cfg.trailing_atr_mult * max(atr, 0.25))

                if (not position.tp1_taken) and pnl_points >= (cfg.tp1_r_multiple * risk_points) and position.contracts_open > 1:
                    close_qty = max(1, position.contracts_open // 2)
                    trades.append(
                        Trade(
                            timestamp=next_bar.timestamp,
                            side="long",
                            contracts=close_qty,
                            entry=position.entry_price,
                            exit=next_bar.open,
                        )
                    )
                    realized = (next_bar.open - position.entry_price) * cfg.point_value * close_qty
                    daily_realized[day] = daily_realized.get(day, 0.0) + realized
                    equity_for_sizing += realized
                    position.contracts_open -= close_qty
                    position.tp1_taken = True

                should_close = (
                    current.close <= position.trail_stop
                    or position.bars_held >= cfg.max_hold_bars
                    or not _in_session(current.timestamp, cfg)
                )
            else:
                stop_price = position.entry_price + risk_points
                if position.trail_stop is None:
                    position.trail_stop = stop_price
                else:
                    position.trail_stop = min(position.trail_stop, position.lowest_close + cfg.trailing_atr_mult * max(atr, 0.25))

                if (not position.tp1_taken) and pnl_points >= (cfg.tp1_r_multiple * risk_points) and position.contracts_open > 1:
                    close_qty = max(1, position.contracts_open // 2)
                    trades.append(
                        Trade(
                            timestamp=next_bar.timestamp,
                            side="short",
                            contracts=close_qty,
                            entry=position.entry_price,
                            exit=next_bar.open,
                        )
                    )
                    realized = (position.entry_price - next_bar.open) * cfg.point_value * close_qty
                    daily_realized[day] = daily_realized.get(day, 0.0) + realized
                    equity_for_sizing += realized
                    position.contracts_open -= close_qty
                    position.tp1_taken = True

                should_close = (
                    current.close >= position.trail_stop
                    or position.bars_held >= cfg.max_hold_bars
                    or not _in_session(current.timestamp, cfg)
                )

            if should_close and position.contracts_open > 0 and position.bars_held >= cfg.min_hold_bars:
                trades.append(
                    Trade(
                        timestamp=next_bar.timestamp,
                        side=position.side,
                        contracts=position.contracts_open,
                        entry=position.entry_price,
                        exit=next_bar.open,
                    )
                )
                if position.side == "long":
                    realized = (next_bar.open - position.entry_price) * cfg.point_value * position.contracts_open
                else:
                    realized = (position.entry_price - next_bar.open) * cfg.point_value * position.contracts_open
                daily_realized[day] = daily_realized.get(day, 0.0) + realized
                equity_for_sizing += realized
                if realized < 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0
                position = None

        decision = "hold"
        if position is None:
            if kill_switch:
                decision = "kill_switch"
            elif not _new_entries_allowed(current.timestamp, cfg):
                decision = "session_block"
            elif regime == "risk_off":
                decision = "risk_off"
            elif current.spread_bps > cfg.max_spread_bps_for_entry:
                decision = "spread_block"
            else:
                entry_side: str | None = None
                signal_points = 0.0

                if regime == "trend" and len(history) >= cfg.breakout_lookback + 2:
                    prev_closes = [b.close for b in history[-cfg.breakout_lookback - 1 : -1]]
                    breakout_high = max(prev_closes)
                    breakout_low = min(prev_closes)
                    ema_fast = _ema(closes[-cfg.ema_fast :], cfg.ema_fast)
                    close_now = current.close
                    close_prev = history[-2].close

                    pullback_ok = abs(close_prev - ema_fast) <= max(atr * cfg.pullback_atr_tolerance, 0.5)
                    if close_now > breakout_high and pullback_ok:
                        entry_side = "long"
                        signal_points = close_now - breakout_high
                    elif close_now < breakout_low and pullback_ok:
                        entry_side = "short"
                        signal_points = breakout_low - close_now

                if entry_side is None and regime == "range" and len(history) >= cfg.range_lookback:
                    look = closes[-cfg.range_lookback :]
                    mean = _mean(look)
                    std = _std(look)
                    if std > 0:
                        z = (current.close - mean) / std
                        if z <= -cfg.range_zscore_entry:
                            entry_side = "long"
                            signal_points = abs(current.close - mean)
                        elif z >= cfg.range_zscore_entry:
                            entry_side = "short"
                            signal_points = abs(current.close - mean)

                if entry_side and _edge_ok(signal_points, current.close, cfg):
                    contracts = _contracts_for_trade(equity_for_sizing, max(atr, 0.25), cfg, consecutive_losses)
                    position = _Position(
                        side=entry_side,
                        entry_time=next_bar.timestamp,
                        entry_price=next_bar.open,
                        entry_atr=max(atr, 0.25),
                        contracts_open=contracts,
                        initial_contracts=contracts,
                    )
                    decision = f"enter_{entry_side}"
                else:
                    decision = "no_edge"

        decisions.append(decision)

    return {"trades": trades, "decisions": decisions if return_decisions else []}


def run_walk_forward_evaluation(
    bars: list[Bar],
    strategy_config: StrategyV1Config,
    backtest_config: BacktestConfig,
    account_type: str,
    account_size: int,
    train_size: int,
    test_size: int,
    step: int,
) -> dict[str, Any]:
    windows = walk_forward_windows(bars, train_size=train_size, test_size=test_size, step=step)
    if not windows:
        raise ValueError("Keine Walk-Forward Fenster erzeugt")

    all_test_trades: list[Trade] = []
    wf_windows: list[dict[str, Any]] = []

    for idx, (train, test) in enumerate(windows):
        combined = list(train) + list(test)
        strat = generate_trades_v1(combined, strategy_config, return_decisions=False)
        window_trades: list[Trade] = []
        test_start = test[0].timestamp
        test_end = test[-1].timestamp
        for t in strat["trades"]:
            if test_start <= t.timestamp <= test_end:
                window_trades.append(t)
        all_test_trades.extend(window_trades)
        wf_windows.append(
            {
                "window": idx,
                "train_start": train[0].timestamp.isoformat(),
                "train_end": train[-1].timestamp.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
                "test_trade_count": len(window_trades),
            }
        )

    report = evaluate_trades_for_apex(
        trades=all_test_trades,
        backtest_config=backtest_config,
        account_type=account_type,
        account_size=account_size,
    )
    report["strategy"] = "v1_regime_breakout_reversion"
    report["strategy_config"] = strategy_config.__dict__.copy()
    report["walk_forward"] = {
        "train_size": train_size,
        "test_size": test_size,
        "step": step,
        "windows": wf_windows,
    }
    return report


def load_bars_from_csv(csv_path: str | Path) -> list[Bar]:
    path = Path(csv_path)
    bars: list[Bar] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_raw = (row.get("ts_event") or "").strip()
            if not ts_raw:
                continue
            ts = dt.datetime.fromisoformat(ts_raw)
            bars.append(
                Bar(
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                    spread_bps=1.0,
                )
            )
    if not bars:
        raise ValueError(f"Keine Bars aus CSV geladen: {path}")
    return bars


def evaluate_strategy_v1_csv(
    csv_path: str | Path,
    output_prefix: str | Path,
    strategy_config: StrategyV1Config,
    backtest_config: BacktestConfig,
    account_type: str,
    account_size: int,
    train_size: int,
    test_size: int,
    step: int,
) -> dict[str, Any]:
    bars = load_bars_from_csv(csv_path)
    report = run_walk_forward_evaluation(
        bars=bars,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        account_type=account_type,
        account_size=account_size,
        train_size=train_size,
        test_size=test_size,
        step=step,
    )

    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = export_report_json(report, prefix.with_suffix(".json"))
    html_path = export_report_html(report, prefix.with_suffix(".html"))
    report["report_json_path"] = str(json_path)
    report["report_html_path"] = str(html_path)
    return report
