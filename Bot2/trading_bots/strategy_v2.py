from __future__ import annotations

from dataclasses import dataclass
import csv
import datetime as dt
import gzip
from pathlib import Path
from typing import Any

from trading_bots.backtest import BacktestConfig, Trade
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
class StrategyV2Config:
    bin_size: float = 1.0
    hvn_quantile: float = 0.70
    lvn_quantile: float = 0.30
    edge_tolerance_points: float = 2.0
    lvn_tolerance_points: float = 1.5
    vol_lookback: int = 30
    volz_edge_threshold: float = 0.5
    volz_lvn_threshold: float = 0.8
    max_spread_bps_for_entry: float = 3.0
    hold_bars_edge: int = 12
    hold_bars_lvn: int = 15
    session_start_utc_minute: int = 13 * 60 + 30
    session_end_utc_minute: int = 20 * 60

    # v2.1 filters
    short_only: bool = True
    allow_longs: bool = False
    use_edge_setup: bool = True
    use_lvn_setup: bool = True
    min_entry_gap_bars: int = 20
    allowed_short_hours_utc: tuple[int, ...] = (14, 15, 17, 19)
    allowed_long_hours_utc: tuple[int, ...] = (13, 16, 18, 19)
    daily_bias_lookback_bars: int = 30


def _minute_of_day(ts: dt.datetime) -> int:
    if ts.tzinfo is not None:
        ts = ts.astimezone(dt.timezone.utc)
    return ts.hour * 60 + ts.minute


def _in_session(ts: dt.datetime, cfg: StrategyV2Config) -> bool:
    m = _minute_of_day(ts)
    return cfg.session_start_utc_minute <= m < cfg.session_end_utc_minute


def _profile_levels(day_bars: list[Bar], cfg: StrategyV2Config) -> tuple[list[float], list[float]]:
    lows = [b.low for b in day_bars]
    highs = [b.high for b in day_bars]
    closes = [b.close for b in day_bars]
    vols = [b.volume for b in day_bars]
    lo = float(int(min(lows)))
    hi = float(int(max(highs) + 1))
    if hi - lo < cfg.bin_size * 2:
        return [], []

    # build simple close-volume histogram by price bin
    bins: list[float] = []
    x = lo
    while x <= hi + cfg.bin_size:
        bins.append(x)
        x += cfg.bin_size
    hist = [0.0 for _ in range(max(1, len(bins) - 1))]
    for c, v in zip(closes, vols):
        idx = int((c - lo) / cfg.bin_size)
        idx = max(0, min(len(hist) - 1, idx))
        hist[idx] += float(v)

    # light smoothing
    smooth = []
    for i in range(len(hist)):
        left = hist[max(0, i - 1)]
        mid = hist[i]
        right = hist[min(len(hist) - 1, i + 1)]
        smooth.append((left + mid + right) / 3.0)

    sorted_s = sorted(smooth)
    qh = sorted_s[int((len(sorted_s) - 1) * cfg.hvn_quantile)]
    ql = sorted_s[int((len(sorted_s) - 1) * cfg.lvn_quantile)]

    prices = [lo + (i + 0.5) * cfg.bin_size for i in range(len(smooth))]

    # HVN edges: edges of contiguous high-density regions
    high_mask = [v >= qh for v in smooth]
    hvn_edges: list[float] = []
    i = 0
    while i < len(high_mask):
        if high_mask[i]:
            j = i
            while j + 1 < len(high_mask) and high_mask[j + 1]:
                j += 1
            hvn_edges.append(prices[i])
            hvn_edges.append(prices[j])
            i = j + 1
        else:
            i += 1

    # LVN local minima below quantile
    lvn_levels: list[float] = []
    for i in range(len(smooth)):
        left = smooth[i - 1] if i > 0 else smooth[i]
        right = smooth[i + 1] if i + 1 < len(smooth) else smooth[i]
        if smooth[i] <= left and smooth[i] <= right and smooth[i] <= ql:
            lvn_levels.append(prices[i])

    return hvn_edges, lvn_levels


def generate_trades_v2(bars: list[Bar], cfg: StrategyV2Config) -> dict[str, Any]:
    if len(bars) < 100:
        return {"trades": []}

    # group bars by date
    by_day: dict[dt.date, list[Bar]] = {}
    for b in bars:
        if _in_session(b.timestamp, cfg):
            by_day.setdefault(b.timestamp.date(), []).append(b)
    days = sorted(by_day.keys())

    profiles: dict[dt.date, tuple[list[float], list[float]]] = {}
    for d in days:
        profiles[d] = _profile_levels(by_day[d], cfg)

    trades: list[Trade] = []

    for di in range(1, len(days)):
        d = days[di]
        prev = days[di - 1]
        hvn_edges, lvn_levels = profiles.get(prev, ([], []))
        day = by_day[d]
        if len(day) < 40:
            continue

        volumes = [b.volume for b in day]

        def volz(idx: int) -> float:
            start = max(0, idx - cfg.vol_lookback + 1)
            w = volumes[start : idx + 1]
            if len(w) < 5:
                return 0.0
            m = sum(w) / len(w)
            var = sum((x - m) ** 2 for x in w) / max(1, len(w) - 1)
            sd = var ** 0.5
            return 0.0 if sd == 0 else (volumes[idx] - m) / sd

        last_entry_i = -10_000
        for i in range(3, len(day) - max(cfg.hold_bars_edge, cfg.hold_bars_lvn) - 1):
            cur = day[i]
            prev_bar = day[i - 1]
            nxt = day[i + 1]
            if cur.spread_bps > cfg.max_spread_bps_for_entry:
                continue
            if i - last_entry_i < cfg.min_entry_gap_bars:
                continue

            # rf-like directional proxy from bar-to-bar highs/lows
            rf = 0
            rf += 1 if cur.high > prev_bar.high else (-1 if cur.high < prev_bar.high else 0)
            rf += 1 if cur.low > prev_bar.low else (-1 if cur.low < prev_bar.low else 0)
            flow = (cur.close - cur.open)
            z = volz(i)
            hour = cur.timestamp.astimezone(dt.timezone.utc).hour if cur.timestamp.tzinfo else cur.timestamp.hour

            # simple daily bias: first N bars mean vs prev day last close
            look_n = min(cfg.daily_bias_lookback_bars, len(day))
            day_bias = 0
            if look_n >= 5:
                first_mean = sum(b.close for b in day[:look_n]) / look_n
                prev_close = by_day[prev][-1].close if by_day.get(prev) else first_mean
                day_bias = 1 if first_mean >= prev_close else -1

            # Setup A: inside-HVN edge rejection
            if cfg.use_edge_setup and hvn_edges:
                nearest_edge = min(hvn_edges, key=lambda x: abs(cur.close - x))
                dist = cur.close - nearest_edge
                if abs(dist) <= cfg.edge_tolerance_points and z > cfg.volz_edge_threshold:
                    # upper-edge rejection -> short
                    if (
                        dist > 0
                        and rf < 0
                        and cur.close < prev_bar.close
                        and flow < 0
                        and hour in cfg.allowed_short_hours_utc
                    ):
                        exit_bar = day[i + cfg.hold_bars_edge]
                        trades.append(Trade(timestamp=nxt.timestamp, side="short", contracts=1, entry=nxt.open, exit=exit_bar.close))
                        last_entry_i = i
                        continue
                    # lower-edge rejection -> long (optional)
                    if (
                        (not cfg.short_only)
                        and cfg.allow_longs
                        and dist < 0
                        and rf > 0
                        and cur.close > prev_bar.close
                        and flow > 0
                        and day_bias >= 0
                        and hour in cfg.allowed_long_hours_utc
                    ):
                        exit_bar = day[i + cfg.hold_bars_edge]
                        trades.append(Trade(timestamp=nxt.timestamp, side="long", contracts=1, entry=nxt.open, exit=exit_bar.close))
                        last_entry_i = i
                        continue

            # Setup B: LVN acceptance pass-through
            if cfg.use_lvn_setup and lvn_levels:
                nearest_lvn = min(lvn_levels, key=lambda x: abs(cur.close - x))
                if abs(cur.close - nearest_lvn) <= cfg.lvn_tolerance_points and z > cfg.volz_lvn_threshold:
                    if (
                        (not cfg.short_only)
                        and cfg.allow_longs
                        and rf > 0
                        and flow > 0
                        and cur.close > prev_bar.close
                        and day_bias >= 0
                        and hour in cfg.allowed_long_hours_utc
                    ):
                        exit_bar = day[i + cfg.hold_bars_lvn]
                        trades.append(Trade(timestamp=nxt.timestamp, side="long", contracts=1, entry=nxt.open, exit=exit_bar.close))
                        last_entry_i = i
                        continue
                    if (
                        rf < 0
                        and flow < 0
                        and cur.close < prev_bar.close
                        and day_bias <= 0
                        and hour in cfg.allowed_short_hours_utc
                    ):
                        exit_bar = day[i + cfg.hold_bars_lvn]
                        trades.append(Trade(timestamp=nxt.timestamp, side="short", contracts=1, entry=nxt.open, exit=exit_bar.close))
                        last_entry_i = i
                        continue

    return {"trades": trades}


def load_bars_from_csv(csv_path: str | Path) -> list[Bar]:
    path = Path(csv_path)
    bars: list[Bar] = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_raw = (row.get("ts_event") or row.get("timestamp") or row.get("datetime") or "").strip()
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


def evaluate_strategy_v2_csv(
    csv_path: str | Path,
    output_prefix: str | Path,
    strategy_config: StrategyV2Config,
    backtest_config: BacktestConfig,
    account_type: str,
    account_size: int,
) -> dict[str, Any]:
    bars = load_bars_from_csv(csv_path)
    strat = generate_trades_v2(bars, strategy_config)
    report = evaluate_trades_for_apex(
        trades=strat["trades"],
        backtest_config=backtest_config,
        account_type=account_type,
        account_size=account_size,
    )
    report["strategy"] = "v2_profile_edge_orderflow"
    report["strategy_config"] = strategy_config.__dict__.copy()

    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = export_report_json(report, prefix.with_suffix(".json"))
    html_path = export_report_html(report, prefix.with_suffix(".html"))
    report["report_json_path"] = str(json_path)
    report["report_html_path"] = str(html_path)
    return report
