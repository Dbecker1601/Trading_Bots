from __future__ import annotations
from pathlib import Path
import sys
import datetime as dt

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path('/opt/workspace/Trading_Bots')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bots.strategy_v2 import (
    StrategyV2Config,
    load_bars_from_csv,
    generate_trades_v2,
    _in_session,
    _profile_levels,
)

cfg = StrategyV2Config(
    short_only=True,
    use_edge_setup=True,
    use_lvn_setup=True,
    volz_edge_threshold=1.1,
    volz_lvn_threshold=1.4,
    hold_bars_edge=16,
    hold_bars_lvn=12,
    min_entry_gap_bars=40,
)

csv_path = ROOT / 'reports' / 'cache' / 'mnq_1m_2025-10-29_to_2026-04-27.csv.gz'
bars = load_bars_from_csv(csv_path)
res = generate_trades_v2(bars, cfg)
trades = res['trades']
shorts = [t for t in trades if t.side == 'short']
if not shorts:
    raise RuntimeError('Keine Short-Trades gefunden')
trade = shorts[len(shorts)//2]

# group session bars by day
by_day = {}
for b in bars:
    if _in_session(b.timestamp, cfg):
        by_day.setdefault(b.timestamp.date(), []).append(b)

days = sorted(by_day.keys())
trade_day = trade.timestamp.date()
if trade_day not in by_day:
    raise RuntimeError('Trade day fehlt')
di = days.index(trade_day)
if di == 0:
    raise RuntimeError('Kein Vortag vorhanden')
prev_day = days[di - 1]

trade_day_bars = by_day[trade_day]
prev_day_bars = by_day[prev_day]
hvn_edges, lvn_levels = _profile_levels(prev_day_bars, cfg)

# find entry index in trade day
entry_idx = None
for i, b in enumerate(trade_day_bars):
    if b.timestamp == trade.timestamp:
        entry_idx = i
        break
if entry_idx is None:
    raise RuntimeError('Entry index nicht gefunden')

# compute decision proxies on trade day
volumes = [b.volume for b in trade_day_bars]

def volz(idx: int) -> float:
    start = max(0, idx - cfg.vol_lookback + 1)
    w = volumes[start:idx+1]
    if len(w) < 5:
        return 0.0
    m = sum(w) / len(w)
    var = sum((x - m) ** 2 for x in w) / max(1, len(w) - 1)
    sd = var ** 0.5
    return 0.0 if sd == 0 else (volumes[idx] - m) / sd

rf_vals, flow_vals, z_vals = [], [], []
for i in range(len(trade_day_bars)):
    if i == 0:
        rf = 0
        flow = 0.0
    else:
        cur = trade_day_bars[i]
        prev = trade_day_bars[i-1]
        rf = 0
        rf += 1 if cur.high > prev.high else (-1 if cur.high < prev.high else 0)
        rf += 1 if cur.low > prev.low else (-1 if cur.low < prev.low else 0)
        flow = cur.close - cur.open
    rf_vals.append(rf)
    flow_vals.append(flow)
    z_vals.append(volz(i))

# window around entry
start_i = max(0, entry_idx - 40)
end_i = min(len(trade_day_bars), entry_idx + 40)
window = trade_day_bars[start_i:end_i]
x = list(range(len(window)))
entry_local = entry_idx - start_i
exit_local = min(len(window)-1, entry_local + cfg.hold_bars_edge)

# market profile histogram from previous day
bin_size = cfg.bin_size
lo = float(int(min(b.low for b in prev_day_bars)))
hi = float(int(max(b.high for b in prev_day_bars) + 1))
bins = []
b = lo
while b <= hi + bin_size:
    bins.append(b)
    b += bin_size
hist = [0.0 for _ in range(max(1, len(bins)-1))]
for pb in prev_day_bars:
    idx = int((pb.close - lo) / bin_size)
    idx = max(0, min(len(hist)-1, idx))
    hist[idx] += float(pb.volume)
prices = [lo + (i + 0.5)*bin_size for i in range(len(hist))]
maxh = max(hist) if hist else 1.0

# plot
fig = plt.figure(figsize=(16, 9))
gs = fig.add_gridspec(2, 1, height_ratios=[3.0, 1.2], hspace=0.08)
ax = fig.add_subplot(gs[0])
ax2 = fig.add_subplot(gs[1], sharex=ax)

# candlesticks
for i, bar in enumerate(window):
    up = bar.close >= bar.open
    color = '#1f9d55' if up else '#d64545'
    ax.vlines(i, bar.low, bar.high, color=color, linewidth=1)
    body_low = min(bar.open, bar.close)
    body_h = max(abs(bar.close - bar.open), 0.05)
    ax.add_patch(Rectangle((i-0.32, body_low), 0.64, body_h, facecolor=color, edgecolor=color, alpha=0.85))

# levels near window price range
pmin = min(b.low for b in window)
pmax = max(b.high for b in window)
for lvl in hvn_edges:
    if pmin - 25 <= lvl <= pmax + 25:
        ax.axhline(lvl, color='red', linestyle='--', linewidth=1.3, alpha=0.75)
for lvl in lvn_levels:
    if pmin - 25 <= lvl <= pmax + 25:
        ax.axhline(lvl, color='royalblue', linestyle=':', linewidth=1.2, alpha=0.7)

# entry/exit
entry_price = window[entry_local].open
ax.scatter([entry_local], [entry_price], color='red', s=120, zorder=6, label='Entry SHORT')
ax.scatter([exit_local], [trade.exit], color='purple', s=120, zorder=6, label='Exit (hold)')
ax.annotate(f"Entry SHORT\n{trade.timestamp.strftime('%H:%M UTC')}\n{trade.entry:.2f}",
            xy=(entry_local, entry_price), xytext=(entry_local+2, entry_price+18),
            arrowprops=dict(arrowstyle='->', color='red'), color='red', fontsize=10)
ax.annotate(f"Exit\n{trade.exit:.2f}",
            xy=(exit_local, trade.exit), xytext=(max(0, exit_local-12), trade.exit-20),
            arrowprops=dict(arrowstyle='->', color='purple'), color='purple', fontsize=10)

ax.set_title(f"v2.2 Entscheidungs-Chart mit Market Profile | Trade {trade.timestamp.isoformat()} (SHORT)")
ax.set_ylabel('Preis')
ax.grid(alpha=0.2)
ax.legend(loc='upper left')

# inset market profile on right side
ins = ax.inset_axes([0.79, 0.08, 0.2, 0.84])
for p, h in zip(prices, hist):
    width = (h / maxh) if maxh > 0 else 0
    ins.barh(p, width, height=bin_size*0.9, color='gray', alpha=0.35)
for lvl in hvn_edges:
    ins.axhline(lvl, color='red', linestyle='--', linewidth=1.0, alpha=0.8)
for lvl in lvn_levels:
    ins.axhline(lvl, color='royalblue', linestyle=':', linewidth=1.0, alpha=0.8)
ins.axhline(entry_price, color='red', linewidth=1.2, alpha=0.9)
ins.set_xlim(0, 1.05)
ins.set_xticks([0, 0.5, 1.0])
ins.set_xticklabels(['0', '0.5', '1.0'])
ins.set_title('Market Profile\n(Vortag, normiert)', fontsize=9)
ins.tick_params(axis='y', labelsize=8)

# score panel
wx = list(range(len(window)))
rf_w = rf_vals[start_i:end_i]
flow_w = flow_vals[start_i:end_i]
z_w = z_vals[start_i:end_i]

ax2.plot(wx, rf_w, label='rf (high/low Richtung)', color='black', linewidth=1.4)
ax2.plot(wx, flow_w, label='flow (close-open)', color='darkorange', linewidth=1.2)
ax2.plot(wx, z_w, label='vol-z', color='teal', linewidth=1.4)
ax2.axhline(cfg.volz_edge_threshold, color='teal', linestyle='--', alpha=0.7, label=f'vol-z edge thr={cfg.volz_edge_threshold}')
ax2.axhline(0, color='gray', linewidth=1)
ax2.axvline(entry_local, color='red', linestyle='--', alpha=0.8)
ax2.set_ylabel('Score')
ax2.set_xlabel('Bars um Entry')
ax2.grid(alpha=0.2)
ax2.legend(loc='upper left', ncol=2, fontsize=9)

out = ROOT / 'reports' / 'strategy_v2_trade_decision_real_with_profile_and_scores.png'
fig.tight_layout()
fig.savefig(out, dpi=180)
print(out)
print(f"trade_ts={trade.timestamp.isoformat()} side={trade.side} entry={trade.entry} exit={trade.exit} day={trade_day} prev_day={prev_day}")
