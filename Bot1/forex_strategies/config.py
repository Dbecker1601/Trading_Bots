"""Global configuration for Bot1 – 6E (Euro FX Futures) / EURUSD strategies."""
import os

# ── Data Sources ──────────────────────────────────────────────────────────────
DATABENTO_DATASET  = "GLBX.MDP3"           # CME Globex
DATABENTO_SYMBOL   = "6E.c.0"              # 6E continuous front-month
DATABENTO_STYPE    = "continuous"
YAHOO_SYMBOL       = "EURUSD=X"            # fallback

# ── Backtest Defaults ─────────────────────────────────────────────────────────
FEES       = 0.00010   # ~1 pip round-trip (commission ≈ $5 + 0.5-pip spread)
INIT_CASH  = 10_000    # USD – prop-firm simulation capital
RISK_PCT   = 0.01      # 1 % risk per trade (for live sizing)

# ── 6E Contract Reference (informational) ─────────────────────────────────────
TICK_SIZE      = 0.00005    # minimum price move (0.5 pip)
TICK_VALUE_USD = 6.25       # USD per tick per contract
CONTRACT_SIZE  = 125_000    # EUR per contract

# ── Active Trading Session (UTC) ──────────────────────────────────────────────
SESSION_START_H = 7     # 07:00 UTC  – European open
SESSION_END_H   = 17    # 17:00 UTC  – US afternoon close

# ── SQN Rating Tiers (Van Tharp) ──────────────────────────────────────────────
SQN_TIERS = {
    "poor":      1.6,
    "average":   2.0,
    "good":      2.5,
    "excellent": 3.0,
    "superb":    5.0,
}

# ── Prop Firm Profiles ────────────────────────────────────────────────────────
# All percentages are of the initial funded balance.
PROP_FIRMS = {
    "FTMO_25k": {
        "label":                 "FTMO Challenge $25k",
        "balance":               25_000,
        "profit_target_pct":     10.0,   # Phase 1 target
        "verify_target_pct":      5.0,   # Phase 2 target
        "max_daily_loss_pct":     5.0,
        "max_loss_pct":          10.0,
        "min_trading_days":      10,
        "consistency_rule":      False,
    },
    "FTMO_100k": {
        "label":                 "FTMO Challenge $100k",
        "balance":               100_000,
        "profit_target_pct":     10.0,
        "verify_target_pct":      5.0,
        "max_daily_loss_pct":     5.0,
        "max_loss_pct":          10.0,
        "min_trading_days":      10,
        "consistency_rule":      False,
    },
    "E8_25k": {
        "label":                 "E8 Funding $25k",
        "balance":               25_000,
        "profit_target_pct":      8.0,
        "verify_target_pct":      4.0,
        "max_daily_loss_pct":     3.0,
        "max_loss_pct":           8.0,
        "min_trading_days":       5,
        "consistency_rule":      False,
    },
    "MyFundedFx_25k": {
        "label":                 "MyFundedFx $25k",
        "balance":               25_000,
        "profit_target_pct":     10.0,
        "verify_target_pct":      5.0,
        "max_daily_loss_pct":     5.0,
        "max_loss_pct":          10.0,
        "min_trading_days":       5,
        "consistency_rule":      False,
    },
    "Apex_50k": {
        "label":                 "Apex Intraday $50k",
        "balance":               50_000,
        "profit_target_pct":      6.0,   # $3,000
        "verify_target_pct":      0.0,   # no verification phase
        "max_daily_loss_pct":     0.0,   # no daily loss limit (intraday)
        "max_loss_pct":           4.0,   # $2,000 trailing threshold
        "min_trading_days":       0,
        "consistency_rule":      False,
    },
}
