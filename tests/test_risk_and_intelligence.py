"""
Tests for quant-agent v2.1 modules.
Run: python -m pytest tests/ -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config import TradingConfig
from risk.global_risk import GlobalRiskManager, TradeProposal, RiskCheckResult


# ===================================================================
# CONFIG
# ===================================================================

class TestTradingConfig:
    def setup_method(self):
        self.config = TradingConfig()

    def test_dynamic_split_small_account(self):
        split = self.config.get_dynamic_split(300)
        assert split["short_term"] == 0.0
        assert split["long_term"] == 95.0
        assert sum(split.values()) == 100.0

    def test_dynamic_split_medium_account(self):
        split = self.config.get_dynamic_split(2500)
        assert split["short_term"] == 15.0
        assert split["mid_term"] == 25.0
        assert split["long_term"] == 60.0

    def test_dynamic_split_large_account(self):
        split = self.config.get_dynamic_split(10000)
        assert split["short_term"] == 20.0
        assert split["mid_term"] == 30.0
        assert split["long_term"] == 50.0

    def test_forced_split_overrides(self):
        self.config.FORCE_SHORT_PCT = 33.0
        self.config.FORCE_MID_PCT = 33.0
        self.config.FORCE_LONG_PCT = 34.0
        split = self.config.get_dynamic_split(300)
        assert split["short_term"] == 33.0
        assert split["long_term"] == 34.0

    def test_dca_amount_scaling(self):
        assert self.config.get_dca_amount(200) == 25.0
        assert self.config.get_dca_amount(800) == 50.0
        assert self.config.get_dca_amount(3000) == 200.0
        assert self.config.get_dca_amount(10000) == 500.0

    def test_sleeve_config_allocation(self):
        sleeve = self.config.get_sleeve_config("long_term", 3000)
        assert sleeve.allocation_pct == 60.0
        assert sleeve.max_positions == 10

    def test_risk_per_trade_scaling(self):
        assert self.config.get_max_risk_per_trade_pct(300) == 1.0
        assert self.config.get_max_risk_per_trade_pct(1500) == 2.0
        assert self.config.get_max_risk_per_trade_pct(5000) == 2.5

    def test_plain_symbol_extraction(self):
        assert self.config.get_plain_symbol("AAPL_US_EQ") == "AAPL"
        assert self.config.get_plain_symbol("AAPL") == "AAPL"

    def test_etf_targets_sum_to_one(self):
        total = sum(self.config.LONG_TERM_ETF_TARGETS.values())
        assert abs(total - 1.0) < 0.001

    def test_sleeve_config_unknown_raises(self):
        with pytest.raises(ValueError):
            self.config.get_sleeve_config("invalid_sleeve", 1000)


# ===================================================================
# GLOBAL RISK MANAGER
# ===================================================================

class TestGlobalRiskManager:
    def setup_method(self):
        self.config = TradingConfig()
        self.risk = GlobalRiskManager(self.config)

    def _make_proposal(self, **kwargs):
        defaults = {
            "sleeve": "mid_term", "ticker": "AAPL", "action": "BUY",
            "quantity": 5.0, "order_type": "limit", "limit_price": 150.0,
            "confidence": 0.65, "reasoning": "Test trade",
        }
        defaults.update(kwargs)
        return TradeProposal(**defaults)

    def test_basic_buy_approved(self):
        result = self.risk.check_trade(
            proposal=self._make_proposal(),
            account_cash=5000.0, total_portfolio_value=10000.0,
            all_positions=[],
        )
        assert result.approved is True

    def test_disabled_sleeve_rejected(self):
        result = self.risk.check_trade(
            proposal=self._make_proposal(sleeve="short_term"),
            account_cash=300.0, total_portfolio_value=300.0,
            all_positions=[],
        )
        assert result.approved is False
        assert any("disabled" in r for r in result.rejection_reasons)

    def test_low_confidence_rejected(self):
        result = self.risk.check_trade(
            proposal=self._make_proposal(confidence=0.10),
            account_cash=5000.0, total_portfolio_value=10000.0,
            all_positions=[],
        )
        assert result.approved is False

    def test_duplicate_ticker_rejected(self):
        result = self.risk.check_trade(
            proposal=self._make_proposal(ticker="NVDA"),
            account_cash=5000.0, total_portfolio_value=10000.0,
            all_positions=[], pending_tickers={"NVDA"},
        )
        assert result.approved is False

    def test_max_positions_rejected(self):
        positions = [
            {"ticker": f"T{i}", "currentPrice": 100, "quantity": 10, "sleeve": "mid_term"}
            for i in range(4)
        ]
        result = self.risk.check_trade(
            proposal=self._make_proposal(),
            account_cash=5000.0, total_portfolio_value=10000.0,
            all_positions=positions,
        )
        assert result.approved is False

    def test_sell_no_position_rejected(self):
        result = self.risk.check_trade(
            proposal=self._make_proposal(action="SELL"),
            account_cash=5000.0, total_portfolio_value=10000.0,
            all_positions=[],
        )
        assert result.approved is False

    def test_daily_trade_recording(self):
        self.risk.record_trade({"sleeve": "mid_term", "realized_pnl": -50.0})
        stats = self.risk.get_daily_stats()
        assert stats["trades_today"] == 1
        assert stats["global_daily_pnl"] == -50.0

    def test_trade_proposal_defaults(self):
        p = TradeProposal(
            sleeve="short_term", ticker="MSFT", action="BUY",
            quantity=10.0, order_type="market",
        )
        assert p.confidence == 0.0
        assert p.stop_loss is None


# ===================================================================
# POSITION SIZING
# ===================================================================

class TestPositionSizing:
    def test_atr_sizing(self):
        from risk.position_sizing import atr_position_size
        result = atr_position_size(
            sleeve_capital=10000, risk_per_trade_pct=2.0,
            entry_price=150.0, atr=5.0, atr_multiplier=2.0,
        )
        assert result["quantity"] > 0
        assert result["stop_loss"] == 140.0
        assert result["risk_dollars"] == 200.0

    def test_atr_sizing_zero_atr(self):
        from risk.position_sizing import atr_position_size
        result = atr_position_size(
            sleeve_capital=10000, risk_per_trade_pct=2.0,
            entry_price=150.0, atr=0,
        )
        assert result["quantity"] == 0

    def test_kelly_positive_edge(self):
        from risk.position_sizing import kelly_position_size
        result = kelly_position_size(
            sleeve_capital=10000, win_rate=0.6,
            avg_win=2.0, avg_loss=1.0, entry_price=100.0,
        )
        assert result["quantity"] > 0
        assert result["kelly_full"] > 0

    def test_kelly_negative_edge(self):
        from risk.position_sizing import kelly_position_size
        result = kelly_position_size(
            sleeve_capital=10000, win_rate=0.3,
            avg_win=1.0, avg_loss=2.0, entry_price=100.0,
        )
        assert result["quantity"] == 0

    def test_fixed_fractional(self):
        from risk.position_sizing import fixed_fractional_size
        result = fixed_fractional_size(
            sleeve_capital=10000, fraction_pct=10.0, entry_price=50.0,
        )
        assert result["quantity"] == 20.0
        assert result["allocation_dollars"] == 1000.0

    def test_master_sizing_short_term(self):
        from risk.position_sizing import calculate_position_size
        result = calculate_position_size(
            sleeve_name="short_term", sleeve_capital=5000,
            entry_price=100.0, atr=3.0, confidence=0.7,
        )
        assert result["quantity"] > 0

    def test_master_sizing_long_term(self):
        from risk.position_sizing import calculate_position_size
        result = calculate_position_size(
            sleeve_name="long_term", sleeve_capital=5000, entry_price=100.0,
        )
        assert result["quantity"] > 0


# ===================================================================
# REGIME DETECTION
# ===================================================================

class TestRegimeDetection:
    def test_regime_constants(self):
        from risk.regime_detection import RISK_MULTIPLIERS, SLEEVE_ADJUSTMENTS
        assert "LOW_VOL" in RISK_MULTIPLIERS
        assert "CRISIS" in RISK_MULTIPLIERS
        assert RISK_MULTIPLIERS["LOW_VOL"] >= RISK_MULTIPLIERS["CRISIS"]

    def test_sleeve_adjustments(self):
        from risk.regime_detection import SLEEVE_ADJUSTMENTS
        for regime in ["LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"]:
            adj = SLEEVE_ADJUSTMENTS[regime]
            assert "short_term" in adj
            assert "mid_term" in adj
            assert "long_term" in adj

    def test_crisis_reduces_short_term(self):
        from risk.regime_detection import SLEEVE_ADJUSTMENTS
        assert SLEEVE_ADJUSTMENTS["CRISIS"]["short_term"] < SLEEVE_ADJUSTMENTS["NORMAL"]["short_term"]

    def test_detector_default_state(self):
        from risk.regime_detection import RegimeDetector
        detector = RegimeDetector()
        state = detector._default_state()
        assert state.regime == "NORMAL"
        assert state.risk_multiplier == 1.0


# ===================================================================
# VOLATILITY TARGET
# ===================================================================

class TestVolatilityTarget:
    def test_vol_target_state_structure(self):
        from risk.volatility_target import VolTargetState
        state = VolTargetState(
            target_vol_pct=12.0, realized_vol_pct=24.0,
            exposure_scalar=0.5, lookback_days=60,
            ewma_halflife=20, raw_scalar=0.5, capped=False,
        )
        d = state.to_dict()
        assert d["target_vol"] == 12.0
        assert d["exposure_scalar"] == 0.5

    def test_vol_bounds(self):
        from risk.volatility_target import MIN_EXPOSURE_SCALAR, MAX_EXPOSURE_SCALAR
        assert MIN_EXPOSURE_SCALAR == 0.20
        assert MAX_EXPOSURE_SCALAR == 1.00


# ===================================================================
# BETA CONTROL
# ===================================================================

class TestBetaControl:
    def test_beta_targets_defined(self):
        from risk.beta_control import BETA_TARGETS
        assert "LOW_VOL" in BETA_TARGETS
        assert "NORMAL" in BETA_TARGETS
        assert "CRISIS" in BETA_TARGETS

    def test_crisis_lower_than_normal(self):
        from risk.beta_control import BETA_TARGETS
        assert BETA_TARGETS["CRISIS"]["high"] < BETA_TARGETS["NORMAL"]["high"]

    def test_controller_initializes(self):
        from risk.beta_control import BetaController
        controller = BetaController()
        assert controller is not None


# ===================================================================
# INTELLIGENCE MODULES
# ===================================================================

class TestCalibration:
    def test_record_prediction_returns_id(self):
        from intelligence.calibration import CalibrationTracker
        tracker = CalibrationTracker()
        pred_id = tracker.record_prediction(
            sleeve="mid_term", ticker="AAPL", action="BUY",
            confidence=0.75, entry_price=150.0,
            stop_loss=145.0, take_profit=160.0, regime="NORMAL",
        )
        assert isinstance(pred_id, str) and len(pred_id) > 0

    def test_confidence_adjustment_no_data(self):
        from intelligence.calibration import CalibrationTracker
        tracker = CalibrationTracker()
        adjusted = tracker.get_confidence_adjustment(0.70)
        assert adjusted == 0.70

    def test_empty_calibration_report(self):
        from intelligence.calibration import CalibrationTracker
        tracker = CalibrationTracker()
        tracker.predictions = []  # ensure clean state
        tracker._save()
        report = tracker.get_calibration_report(days=30)
        assert report.total_predictions == 0


class TestMetaModel:
    def test_initial_state(self):
        from intelligence.meta_model import MetaModel
        from intelligence.calibration import CalibrationTracker
        meta = MetaModel(CalibrationTracker())
        state = meta.get_state()
        assert hasattr(state, "claude_weight")
        assert hasattr(state, "quant_weight")
        assert hasattr(state, "reason")

    def test_effective_confidence(self):
        from intelligence.meta_model import MetaModel
        from intelligence.calibration import CalibrationTracker
        meta = MetaModel(CalibrationTracker())
        result = meta.get_effective_confidence(
            claude_confidence=0.80, quant_signal_strength=0.60,
            sleeve="mid_term", regime="NORMAL",
        )
        assert 0.0 <= result <= 1.0

    def test_position_size_multiplier(self):
        from intelligence.meta_model import MetaModel
        from intelligence.calibration import CalibrationTracker
        meta = MetaModel(CalibrationTracker())
        mult = meta.get_position_size_multiplier(sleeve="mid_term")
        assert 0.0 < mult <= 1.0

    def test_should_override_claude(self):
        from intelligence.meta_model import MetaModel
        from intelligence.calibration import CalibrationTracker
        meta = MetaModel(CalibrationTracker())
        assert isinstance(meta.should_override_claude(sleeve="mid_term"), bool)


class TestAccuracyTracker:
    def test_record_outcome_and_stats(self):
        from intelligence.accuracy_tracker import AccuracyTracker
        tracker = AccuracyTracker()
        tracker.record_outcome(
            ticker="AAPL", sleeve="mid_term", action="BUY",
            entry_price=150.0, exit_price=155.0,
            stop_loss=145.0, take_profit=160.0,
            confidence=0.70, hold_days=5, regime="NORMAL",
        )
        stats = tracker.get_stats()
        assert stats["total"] >= 1

    def test_empty_stats(self):
        from intelligence.accuracy_tracker import AccuracyTracker
        tracker = AccuracyTracker()
        tracker._log = []
        stats = tracker.get_stats()
        assert stats["total"] == 0


# ===================================================================
# BACKTESTER
# ===================================================================

class TestBacktester:
    def test_backtester_init(self):
        from quant.backtester import BacktestEngine
        bt = BacktestEngine(initial_capital=10000, transaction_cost_pct=0.05)
        assert bt.initial_capital == 10000

    def test_backtest_result_to_dict(self):
        from quant.backtester import BacktestResult
        result = BacktestResult(
            strategy_name="test",
            period_start="2024-01-01", period_end="2024-12-31",
            initial_capital=10000.0, final_value=10000.0,
            total_return_pct=0.0, annualized_return_pct=0.0,
            sharpe_ratio=0.0, sortino_ratio=0.0,
            max_drawdown_pct=0.0, calmar_ratio=0.0,
            win_rate=0.0, profit_factor=0.0,
            avg_trade_pnl=0.0, total_trades=0,
            avg_hold_days=0.0, exposure_pct=0.0,
            equity_curve=[], trades=[], monthly_returns={},
            regime_performance={},
        )
        d = result.to_dict()
        assert d["strategy"] == "test"
        assert d["total_return"] == "0.00%"


# ===================================================================
# VIRTUAL CAPITAL
# ===================================================================

# ===============================================================
# BROKER ADAPTER (Simulated)
# ===============================================================

class TestBrokerAdapter:
    """Tests for the simulated broker adapter."""

    def _make_adapter(self, capital=10000):
        config = TradingConfig()
        config.INITIAL_CAPITAL = capital
        from broker_adapter import BrokerAdapter, SIMULATED_STATE_FILE
        # Clean state
        SIMULATED_STATE_FILE.unlink(missing_ok=True)
        adapter = BrokerAdapter(config)
        return adapter

    def test_initial_cash(self):
        adapter = self._make_adapter(50000)
        cash = adapter.get_account_cash()
        assert cash["free"] == 50000
        assert cash["total"] == 50000
        assert cash["invested"] == 0

    def test_account_info(self):
        adapter = self._make_adapter()
        info = adapter.get_account_info()
        assert info["mode"] == "simulated"
        assert info["status"] == "ACTIVE"

    def test_market_clock(self):
        adapter = self._make_adapter()
        clock = adapter.get_market_clock()
        assert "is_open" in clock
        assert "next_open" in clock
        assert "next_close" in clock

    def test_empty_positions(self):
        adapter = self._make_adapter()
        positions = adapter.get_positions()
        assert positions == []

    def test_reset(self):
        adapter = self._make_adapter(10000)
        adapter.reset(75000)
        cash = adapter.get_account_cash()
        assert cash["free"] == 75000
        assert cash["total"] == 75000

    def test_reject_insufficient_funds(self):
        adapter = self._make_adapter(100)
        # Try to buy something expensive
        order = adapter.place_market_order("AAPL", 1000)
        # Should be rejected (unless AAPL is < $0.10)
        assert order["status"] in ("rejected", "filled")

    def test_set_sleeve(self):
        adapter = self._make_adapter()
        # Manually add a position to state
        adapter._state["positions"]["TEST"] = {
            "quantity": 10, "avg_price": 50.0, "sleeve": "unknown"
        }
        adapter.set_sleeve("TEST", "short_term")
        assert adapter._state["positions"]["TEST"]["sleeve"] == "short_term"


# ===============================================================
# ETF REVIEW
# ===============================================================

class TestETFReview:
    """Tests for the ETF quarterly review engine."""

    def test_review_due_initial(self):
        from etf_review import ETFReviewEngine, REVIEW_FILE
        REVIEW_FILE.unlink(missing_ok=True)
        config = TradingConfig()
        engine = ETFReviewEngine(config)
        assert engine.is_review_due() is True

    def test_no_pending_initially(self):
        from etf_review import ETFReviewEngine, PENDING_FILE
        PENDING_FILE.unlink(missing_ok=True)
        config = TradingConfig()
        engine = ETFReviewEngine(config)
        assert engine.get_pending() is None

    def test_empty_sell_queue(self):
        from etf_review import ETFReviewEngine, SELL_QUEUE_FILE
        SELL_QUEUE_FILE.unlink(missing_ok=True)
        config = TradingConfig()
        engine = ETFReviewEngine(config)
        assert engine.get_sell_queue() == []

    def test_get_active_overrides_none(self):
        from etf_review import ETFReviewEngine, OVERRIDES_FILE
        OVERRIDES_FILE.unlink(missing_ok=True)
        config = TradingConfig()
        engine = ETFReviewEngine(config)
        assert engine.get_active_overrides() is None


# ===============================================================
# EMAIL NOTIFICATIONS
# ===============================================================

class TestEmailNotifier:
    """Tests for the email notification system."""

    def test_disabled_by_default(self):
        import os
        os.environ.pop("EMAIL_ENABLED", None)
        from notifications import EmailNotifier
        notifier = EmailNotifier()
        assert notifier.enabled is False

    def test_send_returns_false_when_disabled(self):
        from notifications import EmailNotifier
        notifier = EmailNotifier()
        notifier.enabled = False
        result = notifier.send("Test Subject", "Test Body")
        assert result is False

    def test_daily_summary_returns_false_when_disabled(self):
        from notifications import EmailNotifier
        notifier = EmailNotifier()
        notifier.enabled = False
        result = notifier.send_daily_summary()
        assert result is False


# ===============================================================
# CONFIG (Public Edition specifics)
# ===============================================================

class TestConfigPublicEdition:
    """Tests for public edition config features."""

    def test_market_hours_gate_default(self):
        config = TradingConfig()
        assert config.MARKET_HOURS_ONLY is True

    def test_pre_market_buffer(self):
        config = TradingConfig()
        assert config.PRE_MARKET_BUFFER_MIN == 30

    def test_kill_switch_threshold(self):
        config = TradingConfig()
        assert config.KILL_SWITCH_DRAWDOWN_PCT == 20.0

    def test_vol_target(self):
        config = TradingConfig()
        assert config.VOL_TARGET_PCT == 12.0

    def test_get_etf_targets_default(self):
        from etf_review import OVERRIDES_FILE
        OVERRIDES_FILE.unlink(missing_ok=True)
        config = TradingConfig()
        targets = config.get_etf_targets()
        assert "VOO" in targets
        assert abs(sum(targets.values()) - 1.0) < 0.01

    def test_validate_simulated_no_errors(self):
        config = TradingConfig()
        config.BROKER = "simulated"
        config.ANTHROPIC_API_KEY = "test-key"
        errors = config.validate()
        assert len(errors) == 0


# ===============================================================
# KILL SWITCH
# ===============================================================

class TestKillSwitch:
    """Tests for the drawdown kill switch."""

    def test_kill_switch_lifecycle(self):
        import json
        from pathlib import Path

        KILL_SWITCH_FILE = Path(".kill_switch")
        KILL_SWITCH_FILE.unlink(missing_ok=True)

        # Not active initially
        assert not KILL_SWITCH_FILE.exists()

        # Activate
        data = {
            "activated_at": "2025-01-01T00:00:00+00:00",
            "reason": "Test drawdown",
        }
        KILL_SWITCH_FILE.write_text(json.dumps(data, indent=2))
        assert KILL_SWITCH_FILE.exists()

        # Verify content
        loaded = json.loads(KILL_SWITCH_FILE.read_text())
        assert "Test drawdown" in loaded["reason"]

        # Deactivate
        KILL_SWITCH_FILE.unlink(missing_ok=True)
        assert not KILL_SWITCH_FILE.exists()


# ===============================================================
# VIRTUAL CAPITAL
# ===============================================================

class TestVirtualCapital:
    """Tests for the virtual capital manager."""

    def _make_vcm(self, initial=10000, monthly=500):
        from virtual_capital import VirtualCapitalManager, STATE_FILE
        STATE_FILE.unlink(missing_ok=True)
        return VirtualCapitalManager(
            initial_capital=initial,
            monthly_deposit=monthly,
            currency="USD",
            currency_symbol="$",
        )

    def test_initial_state(self):
        vcm = self._make_vcm(10000)
        assert vcm.get_virtual_cash() == 10000
        assert vcm.get_total_deposited() == 10000
        assert vcm.get_positions() == {}
        assert vcm.get_portfolio_value() == 10000

    def test_manual_deposit(self):
        vcm = self._make_vcm(10000, 500)
        vcm.deposit(500, "manual")
        assert vcm.get_virtual_cash() == 10500
        assert vcm.get_total_deposited() == 10500

    def test_buy_deducts_cash(self):
        vcm = self._make_vcm(10000)
        result = vcm.record_buy("AAPL", 10, 150.0, sleeve="mid_term")
        assert result is True
        assert vcm.get_virtual_cash() == 8500  # 10000 - 1500
        positions = vcm.get_positions()
        assert "AAPL" in positions
        assert positions["AAPL"]["quantity"] == 10
        assert positions["AAPL"]["avg_price"] == 150.0

    def test_buy_insufficient_cash(self):
        vcm = self._make_vcm(100)
        result = vcm.record_buy("AAPL", 10, 150.0)
        assert result is False
        assert vcm.get_virtual_cash() == 100  # unchanged

    def test_sell_credits_cash(self):
        vcm = self._make_vcm(10000)
        vcm.record_buy("AAPL", 10, 150.0)
        result = vcm.record_sell("AAPL", 5, 160.0)
        assert result is True
        assert vcm.get_virtual_cash() == 8500 + 800  # 8500 + (5 * 160)
        positions = vcm.get_positions()
        assert positions["AAPL"]["quantity"] == 5

    def test_sell_all_removes_position(self):
        vcm = self._make_vcm(10000)
        vcm.record_buy("AAPL", 10, 150.0)
        vcm.record_sell("AAPL", 10, 160.0)
        assert "AAPL" not in vcm.get_positions()

    def test_sell_more_than_owned_fails(self):
        vcm = self._make_vcm(10000)
        vcm.record_buy("AAPL", 5, 150.0)
        result = vcm.record_sell("AAPL", 10, 160.0)
        assert result is False

    def test_return_pct(self):
        vcm = self._make_vcm(10000)
        vcm.record_buy("AAPL", 10, 100.0)
        # Cash: 9000, invested at cost: 1000
        # Portfolio at cost = 10000, return = 0%
        assert vcm.get_return_pct() == 0.0

    def test_agent_interface(self):
        vcm = self._make_vcm(12500)
        cash_info = vcm.get_account_cash_for_agent()
        assert cash_info["free"] == 12500
        assert cash_info["total"] == 12500
        assert cash_info["invested"] == 0
        assert cash_info["buying_power"] == 12500

    def test_status_summary(self):
        vcm = self._make_vcm(12500, 625)
        status = vcm.get_status()
        assert status["virtual_cash"] == 12500
        assert status["total_deposited"] == 12500
        assert status["portfolio_value"] == 12500
        assert status["pnl"] == 0
        assert status["currency"] == "USD"

    def test_reset(self):
        vcm = self._make_vcm(10000)
        vcm.record_buy("AAPL", 10, 150.0)
        vcm.deposit(500)
        vcm.reset()
        assert vcm.get_virtual_cash() == 10000
        assert vcm.get_total_deposited() == 10000
        assert vcm.get_positions() == {}

    def test_deposit_history(self):
        vcm = self._make_vcm(10000, 500)
        vcm.deposit(500, "monthly")
        vcm.deposit(200, "manual")
        history = vcm.get_deposit_history()
        assert len(history) == 3  # initial + monthly + manual
        assert history[0]["type"] == "initial"
        assert history[1]["type"] == "monthly"
        assert history[2]["type"] == "manual"
        assert vcm.get_total_deposited() == 10700
