from __future__ import annotations
import datetime as dt
from pathlib import Path
import sys

import matplotlib.pyplot as plt

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

OUT_DIR = ROOT / 'reports'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- 1) Theoretisches Bild ----------
fig, ax = plt.subplots(figsize=(14, 7))
# synthetic price path
x = list(range(40))
price = [100 + 0.2*i + (1.5 if 10 < i < 15 else 0) - (2.0 if 22 < i < 28 else 0) for i in x]
ax.plot(x, price, color='black', linewidth=2, label='Preisverlauf (schematisch)')

hvn_upper = 106.0
hvn_lower = 102.0
lvn_gate = 99.5
ax.axhline(hvn_upper, color='red', linestyle='--', linewidth=2, label='HVN obere Kante')
ax.axhline(hvn_lower, color='green', linestyle='--', linewidth=2, label='HVN untere Kante')
ax.axhline(lvn_gate, color='blue', linestyle=':', linewidth=2, label='LVN Gate')

# mark decision point for short rejection near upper edge
entry_x = 17
entry_y = price[entry_x]
exit_x = 30
exit_y = price[exit_x]
ax.scatter([entry_x], [entry_y], color='red', s=120, zorder=5)
ax.scatter([exit_x], [exit_y], color='purple', s=120, zorder=5)
ax.annotate('Entry SHORT\nBedingungen:\n- Nähe HVN-Edge\n- rf < 0\n- flow < 0\n- vol-z > Schwelle',
            xy=(entry_x, entry_y), xytext=(entry_x+2, entry_y+3),
            arrowprops=dict(arrowstyle='->', color='red'), fontsize=10, color='red')
ax.annotate('Exit nach hold_bars',
            xy=(exit_x, exit_y), xytext=(exit_x-8, exit_y-3),
            arrowprops=dict(arrowstyle='->', color='purple'), fontsize=10, color='purple')

ax.set_title('Theorie: Trade-Entscheidung v2.2 (HVN-Edge Rejection / LVN-Kontext)')
ax.set_xlabel('Bar-Index (schematisch)')
ax.set_ylabel('Preis')
ax.legend(loc='upper left')
ax.grid(alpha=0.25)

theory_path = OUT_DIR / 'strategy_v2_trade_decision_theory.png'
fig.tight_layout()
fig.savefig(theory_path, dpi=170)
plt.close(fig)

# ---------- 2) Echtes Beispiel aus v2.2 ----------
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
if not trades:
    raise RuntimeError('Keine Trades gefunden')

# pick a short trade somewhere in middle for context
short_trades = [t for t in trades if t.side == 'short']
trade = short_trades[len(short_trades)//2]

# group bars by day in session
by_day = {}
for b in bars:
    if _in_session(b.timestamp, cfg):
        by_day.setdefault(b.timestamp.date(), []).append(b)

days = sorted(by_day.keys())
trade_day = trade.timestamp.date()
if trade_day not in by_day:
    raise RuntimeError('Trade day nicht in Sessiondaten')

trade_day_bars = by_day[trade_day]
# find entry bar index
entry_idx = None
for i, b in enumerate(trade_day_bars):
    if b.timestamp == trade.timestamp and abs(b.open - trade.entry) < 1e-9:
        entry_idx = i
        break
if entry_idx is None:
    # fallback by timestamp only
    for i, b in enumerate(trade_day_bars):
        if b.timestamp == trade.timestamp:
            entry_idx = i
            break
if entry_idx is None:
    raise RuntimeError('Entry-Index nicht gefunden')

# prev day profile levels
di = days.index(trade_day)
prev_day = days[di-1]
hvn_edges, lvn_levels = _profile_levels(by_day[prev_day], cfg)

start_i = max(0, entry_idx - 35)
end_i = min(len(trade_day_bars), entry_idx + 45)
window = trade_day_bars[start_i:end_i]
wx = list(range(len(window)))
wclose = [b.close for b in window]

entry_local = entry_idx - start_i
# approximate exit timestamp match
exit_local = None
for j, b in enumerate(window):
    if abs(b.close - trade.exit) < 1e-8 and b.timestamp > trade.timestamp:
        exit_local = j
        break
if exit_local is None:
    exit_local = min(len(window)-1, entry_local + 16)

fig, ax = plt.subplots(figsize=(15, 8))
ax.plot(wx, wclose, color='black', linewidth=1.8, label='MNQ Close (real)')

# draw nearest few profile levels around price
ref_price = window[entry_local].close
hvn_show = sorted(hvn_edges, key=lambda p: abs(p-ref_price))[:3]
lvn_show = sorted(lvn_levels, key=lambda p: abs(p-ref_price))[:2]
for p in hvn_show:
    ax.axhline(p, color='red', linestyle='--', alpha=0.8)
for p in lvn_show:
    ax.axhline(p, color='blue', linestyle=':', alpha=0.8)

ax.scatter([entry_local], [window[entry_local].open], color='red', s=140, zorder=5, label='Entry SHORT')
ax.scatter([exit_local], [trade.exit], color='purple', s=140, zorder=5, label='Exit')

ax.annotate(
    f"Entry SHORT\n{trade.timestamp.isoformat()}\nentry={trade.entry:.2f}",
    xy=(entry_local, window[entry_local].open),
    xytext=(entry_local+3, window[entry_local].open + 18),
    arrowprops=dict(arrowstyle='->', color='red'),
    fontsize=10,
    color='red'
)
ax.annotate(
    f"Exit\nexit={trade.exit:.2f}",
    xy=(exit_local, trade.exit),
    xytext=(max(0, exit_local-14), trade.exit - 20),
    arrowprops=dict(arrowstyle='->', color='purple'),
    fontsize=10,
    color='purple'
)

ax.set_title(f"Echtes Beispiel v2.2 Trade-Entscheidung ({trade_day})")
ax.set_xlabel('Bar-Index im Fenster um Entry')
ax.set_ylabel('Preis')
ax.grid(alpha=0.25)
ax.legend(loc='best')

real_path = OUT_DIR / 'strategy_v2_trade_decision_real_example.png'
fig.tight_layout()
fig.savefig(real_path, dpi=170)
plt.close(fig)

print(theory_path)
print(real_path)
print(f"example_trade_ts={trade.timestamp.isoformat()} side={trade.side} entry={trade.entry} exit={trade.exit}")
