import unittest

from trading_bots.decision_engine import (
    DecisionConfig,
    MarketSnapshot,
    RiskState,
    compute_expected_edge_bps,
    detect_regime,
    generate_trade_decision,
    should_trade,
)


class TestDecisionEngine(unittest.TestCase):
    def test_detect_regime_returns_risk_off_when_vol_too_high(self) -> None:
        config = DecisionConfig()
        snapshot = MarketSnapshot(
            returns_1m=0.0005,
            returns_5m=0.001,
            ema_fast=20010,
            ema_slow=20000,
            realized_vol=0.03,
            atr_points=40,
            spread_bps=1.0,
            session_minute=90,
        )

        self.assertEqual(detect_regime(snapshot, config), "risk_off")

    def test_detect_regime_returns_trend_when_trend_strength_high(self) -> None:
        config = DecisionConfig()
        snapshot = MarketSnapshot(
            returns_1m=0.0005,
            returns_5m=0.002,
            ema_fast=20020,
            ema_slow=20000,
            realized_vol=0.01,
            atr_points=20,
            spread_bps=1.0,
            session_minute=120,
        )

        self.assertEqual(detect_regime(snapshot, config), "trend")

    def test_should_trade_respects_cost_and_buffer(self) -> None:
        self.assertFalse(should_trade(edge_bps=4.9, estimated_cost_bps=4.0, safety_buffer_bps=1.0))
        self.assertTrue(should_trade(edge_bps=6.0, estimated_cost_bps=4.0, safety_buffer_bps=1.0))

    def test_generate_trade_decision_stays_flat_after_daily_loss_limit(self) -> None:
        config = DecisionConfig(max_daily_loss=-300.0)
        snapshot = MarketSnapshot(
            returns_1m=0.001,
            returns_5m=0.003,
            ema_fast=20030,
            ema_slow=20000,
            realized_vol=0.008,
            atr_points=18,
            spread_bps=1.0,
            session_minute=80,
        )
        risk_state = RiskState(current_position=0, daily_pnl=-350.0)

        decision = generate_trade_decision(snapshot, risk_state, config, ml_prob_up=0.7)

        self.assertEqual(decision.action, "flat")
        self.assertEqual(decision.target_position, 0)

    def test_generate_trade_decision_goes_long_when_edge_is_sufficient(self) -> None:
        config = DecisionConfig(max_position=4)
        snapshot = MarketSnapshot(
            returns_1m=0.001,
            returns_5m=0.004,
            ema_fast=20050,
            ema_slow=20000,
            realized_vol=0.006,
            atr_points=14,
            spread_bps=1.2,
            session_minute=100,
        )
        risk_state = RiskState(current_position=0, daily_pnl=100.0)

        decision = generate_trade_decision(snapshot, risk_state, config, ml_prob_up=0.9)

        self.assertEqual(decision.action, "long")
        self.assertGreaterEqual(decision.target_position, 1)
        self.assertLessEqual(decision.target_position, 4)

    def test_compute_expected_edge_bps(self) -> None:
        edge = compute_expected_edge_bps(prob_up=0.6, payoff_win_bps=8.0, payoff_loss_bps=6.0)
        self.assertAlmostEqual(edge, 2.4)


if __name__ == "__main__":
    unittest.main()
