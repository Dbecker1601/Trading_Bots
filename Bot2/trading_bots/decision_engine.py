from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionConfig:
    trend_ema_diff_threshold: float = 8.0
    risk_off_vol_threshold: float = 0.02
    min_edge_bps: float = 5.0
    safety_buffer_bps: float = 1.0
    estimated_cost_bps: float = 4.0
    max_position: int = 3
    edge_for_max_size_bps: float = 12.0
    target_vol: float = 0.01
    max_daily_loss: float = -500.0


@dataclass(frozen=True)
class MarketSnapshot:
    returns_1m: float
    returns_5m: float
    ema_fast: float
    ema_slow: float
    realized_vol: float
    atr_points: float
    spread_bps: float
    session_minute: int


@dataclass(frozen=True)
class RiskState:
    current_position: int
    daily_pnl: float


@dataclass(frozen=True)
class TradeDecision:
    action: str
    target_position: int
    regime: str
    signal_score: float
    edge_bps: float
    reason: str


def detect_regime(snapshot: MarketSnapshot, config: DecisionConfig) -> str:
    if snapshot.realized_vol >= config.risk_off_vol_threshold:
        return "risk_off"

    trend_strength = snapshot.ema_fast - snapshot.ema_slow
    if abs(trend_strength) >= config.trend_ema_diff_threshold and snapshot.returns_5m * trend_strength > 0:
        return "trend"

    return "range"


def compute_expected_edge_bps(prob_up: float, payoff_win_bps: float, payoff_loss_bps: float) -> float:
    prob = min(max(prob_up, 0.0), 1.0)
    return (prob * payoff_win_bps) - ((1.0 - prob) * payoff_loss_bps)


def should_trade(edge_bps: float, estimated_cost_bps: float, safety_buffer_bps: float) -> bool:
    return edge_bps > (estimated_cost_bps + safety_buffer_bps)


def _base_signal(snapshot: MarketSnapshot, regime: str) -> float:
    momentum = snapshot.returns_5m * 10000.0
    trend_bias = (snapshot.ema_fast - snapshot.ema_slow) / 4.0

    if regime == "trend":
        return momentum + trend_bias

    # range / mean-reversion mode
    return -(snapshot.returns_1m * 10000.0) * 0.7


def _size_position(edge_bps: float, snapshot: MarketSnapshot, config: DecisionConfig) -> int:
    edge_scale = min(1.0, max(0.0, edge_bps / config.edge_for_max_size_bps))
    vol_scale = min(1.0, config.target_vol / max(snapshot.realized_vol, 1e-6))
    size = int(round(config.max_position * edge_scale * vol_scale))
    return max(0, min(config.max_position, size))


def generate_trade_decision(
    snapshot: MarketSnapshot,
    risk_state: RiskState,
    config: DecisionConfig,
    ml_prob_up: float | None = None,
) -> TradeDecision:
    if risk_state.daily_pnl <= config.max_daily_loss:
        return TradeDecision(
            action="flat",
            target_position=0,
            regime="kill_switch",
            signal_score=0.0,
            edge_bps=0.0,
            reason="daily_loss_limit_hit",
        )

    regime = detect_regime(snapshot, config)
    if regime == "risk_off":
        return TradeDecision(
            action="flat",
            target_position=0,
            regime=regime,
            signal_score=0.0,
            edge_bps=0.0,
            reason="risk_off_volatility",
        )

    rule_signal = _base_signal(snapshot, regime)
    prob_up = ml_prob_up if ml_prob_up is not None else (0.5 + max(min(rule_signal / 100.0, 0.2), -0.2))
    edge_bps = compute_expected_edge_bps(prob_up=prob_up, payoff_win_bps=8.0, payoff_loss_bps=6.0)

    if not should_trade(edge_bps=edge_bps, estimated_cost_bps=config.estimated_cost_bps, safety_buffer_bps=config.safety_buffer_bps):
        return TradeDecision(
            action="flat",
            target_position=0,
            regime=regime,
            signal_score=rule_signal,
            edge_bps=edge_bps,
            reason="edge_below_threshold",
        )

    size = _size_position(edge_bps=edge_bps, snapshot=snapshot, config=config)
    if size == 0:
        return TradeDecision(
            action="flat",
            target_position=0,
            regime=regime,
            signal_score=rule_signal,
            edge_bps=edge_bps,
            reason="size_reduced_to_zero",
        )

    action = "long" if rule_signal >= 0 else "short"
    target = size if action == "long" else -size
    return TradeDecision(
        action=action,
        target_position=target,
        regime=regime,
        signal_score=rule_signal,
        edge_bps=edge_bps,
        reason="trade_allowed",
    )
