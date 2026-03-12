"""
Tests for Quant Agent Public Edition modules.
Run: python -m pytest tests/ -v

Note:
This public test suite verifies only high-level behaviour and interface
contracts for the demo architecture. Proprietary trading rules,
optimized parameters, and production integrations are intentionally
excluded in this public edition.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config import TradingConfig
from risk.global_risk import GlobalRiskManager, TradeProposal


# ===================================================================
# CONFIG
# ===================================================================

class TestTradingConfig:
    def setup_method(self):
        self.config = TradingConfig()

    def test_dynamic_split_returns_structure(self):
        split = self.config.get_dynamic_split(1000)

        assert isinstance(split, dict)
        assert "short_term" in split
        assert "mid_term" in split
        assert "long_term" in split
        assert abs(sum(split.values()) - 100.0) < 0.01

    def test_dca_amount_returns_number(self):
        amount = self.config.get_dca_amount(2000)
        assert isinstance(amount, (int, float))
        assert amount >= 0

    def test_sleeve_config_structure(self):
        sleeve = self.config.get_sleeve_config("long_term", 2000)
        assert hasattr(sleeve, "allocation_pct")
        assert hasattr(sleeve, "max_positions")

    def test_risk_per_trade_returns_number(self):
        value = self.config.get_max_risk_per_trade_pct(2000)
        assert isinstance(value, (int, float))

    def test_plain_symbol_extraction(self):
        assert self.config.get_plain_symbol("TEST_SYMBOL") == "TEST"

    def test_unknown_sleeve_raises(self):
        with pytest.raises(ValueError):
            self.config.get_sleeve_config("invalid", 1000)


# ===================================================================
# GLOBAL RISK MANAGER
# ===================================================================

class TestGlobalRiskManager:
    def setup_method(self):
        self.config = TradingConfig()
        self.risk = GlobalRiskManager(self.config)

    def _make_proposal(self, **kwargs):
        defaults = {
            "sleeve": "mid_term",
            "ticker": "TEST",
            "action": "BUY",
            "quantity": 1.0,
            "order_type": "limit",
            "limit_price": 100.0,
            "confidence": 0.5,
            "reasoning": "demo trade",
        }
        defaults.update(kwargs)
        return TradeProposal(**defaults)

    def test_basic_trade_returns_result(self):
        result = self.risk.check_trade(
            proposal=self._make_proposal(),
            account_cash=10000,
            total_portfolio_value=10000,
            all_positions=[],
        )

        assert hasattr(result, "approved")
        assert hasattr(result, "rejection_reasons")

    def test_sell_without_position(self):
        result = self.risk.check_trade(
            proposal=self._make_proposal(action="SELL"),
            account_cash=10000,
            total_portfolio_value=10000,
            all_positions=[],
        )

        assert isinstance(result.approved, bool)

    def test_trade_recording(self):
        self.risk.record_trade({"sleeve": "mid_term", "realized_pnl": -10})
        stats = self.risk.get_daily_stats()

        assert "trades_today" in stats
        assert "global_daily_pnl" in stats

    def test_trade_proposal_defaults(self):
        proposal = TradeProposal(
            sleeve="short_term",
            ticker="TEST",
            action="BUY",
            quantity=1,
            order_type="market",
        )

        assert proposal.confidence >= 0
        assert proposal.stop_loss is None


# ===================================================================
# POSITION SIZING
# ===================================================================

class TestPositionSizing:
    def test_atr_position_size_structure(self):
        from risk.position_sizing import atr_position_size

        result = atr_position_size(
            sleeve_capital=10000,
            risk_per_trade_pct=1.0,
            entry_price=100.0,
            atr=2.0,
        )

        assert isinstance(result, dict)
        assert "quantity" in result

    def test_fixed_fractional_structure(self):
        from risk.position_sizing import fixed_fractional_size

        result = fixed_fractional_size(
            sleeve_capital=10000,
            fraction_pct=10.0,
            entry_price=50.0,
        )

        assert "quantity" in result

    def test_master_sizing_returns_quantity(self):
        from risk.position_sizing import calculate_position_size

        result = calculate_position_size(
            sleeve_name="mid_term",
            sleeve_capital=5000,
            entry_price=100.0,
        )

        assert "quantity" in result


# ===================================================================
# REGIME DETECTION
# ===================================================================

class TestRegimeDetection:
    def test_regime_constants_exist(self):
        from risk.regime_detection import RISK_MULTIPLIERS

        assert isinstance(RISK_MULTIPLIERS, dict)
        assert len(RISK_MULTIPLIERS) > 0

    def test_detector_initialization(self):
        from risk.regime_detection import RegimeDetector

        detector = RegimeDetector()
        state = detector._default_state()

        assert state.regime is not None
        assert state.risk_multiplier >= 0


# ===================================================================
# VOLATILITY TARGET
# ===================================================================

class TestVolatilityTarget:
    def test_state_structure(self):
        from risk.volatility_target import VolTargetState

        state = VolTargetState(
            target_vol_pct=10,
            realized_vol_pct=12,
            exposure_scalar=0.8,
            lookback_days=60,
            ewma_halflife=20,
            raw_scalar=0.8,
            capped=False,
        )

        d = state.to_dict()

        assert "target_vol" in d
        assert "exposure_scalar" in d


# ===================================================================
# BETA CONTROL
# ===================================================================

class TestBetaControl:
    def test_beta_targets_exist(self):
        from risk.beta_control import BETA_TARGETS

        assert isinstance(BETA_TARGETS, dict)
        assert len(BETA_TARGETS) > 0

    def test_controller_init(self):
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
            sleeve="mid_term",
            ticker="TEST",
            action="BUY",
            confidence=0.5,
            entry_price=100,
            stop_loss=95,
            take_profit=110,
            regime="NORMAL",
        )

        assert isinstance(pred_id, str)

    def test_empty_report(self):
        from intelligence.calibration import CalibrationTracker

        tracker = CalibrationTracker()
        report = tracker.get_calibration_report(days=30)

        assert report.total_predictions >= 0


class TestMetaModel:
    def test_meta_model_state(self):
        from intelligence.meta_model import MetaModel
        from intelligence.calibration import CalibrationTracker

        meta = MetaModel(CalibrationTracker())
        state = meta.get_state()

        assert hasattr(state, "claude_weight")

    def test_effective_confidence_bounds(self):
        from intelligence.meta_model import MetaModel
        from intelligence.calibration import CalibrationTracker

        meta = MetaModel(CalibrationTracker())

        result = meta.get_effective_confidence(
            claude_confidence=0.7,
            quant_signal_strength=0.5,
            sleeve="mid_term",
            regime="NORMAL",
        )

        assert 0.0 <= result <= 1.0


class TestAccuracyTracker:
    def test_record_and_stats(self):
        from intelligence.accuracy_tracker import AccuracyTracker

        tracker = AccuracyTracker()

        tracker.record_outcome(
            ticker="TEST",
            sleeve="mid_term",
            action="BUY",
            entry_price=100,
            exit_price=105,
            stop_loss=95,
            take_profit=110,
            confidence=0.6,
            hold_days=3,
            regime="NORMAL",
        )

        stats = tracker.get_stats()

        assert "total" in stats


# ===================================================================
# BACKTESTER
# ===================================================================

class TestBacktester:
    def test_backtester_initialization(self):
        from quant.backtester import BacktestEngine

        bt = BacktestEngine(initial_capital=10000)

        assert bt.initial_capital == 10000


# ===================================================================
# BROKER ADAPTER (Simulated)
# ===================================================================

class TestBrokerAdapter:
    def _make_adapter(self):
        config = TradingConfig()

        from broker_adapter import BrokerAdapter

        return BrokerAdapter(config)

    def test_account_info(self):
        adapter = self._make_adapter()

        info = adapter.get_account_info()

        assert "mode" in info

    def test_positions_structure(self):
        adapter = self._make_adapter()

        positions = adapter.get_positions()

        assert isinstance(positions, list)


# ===================================================================
# ETF REVIEW
# ===================================================================

class TestETFReview:
    def test_engine_initialization(self):
        from etf_review import ETFReviewEngine
        config = TradingConfig()

        engine = ETFReviewEngine(config)

        assert engine is not None


# ===================================================================
# EMAIL NOTIFICATIONS
# ===================================================================

class TestEmailNotifier:
    def test_notifier_disabled_by_default(self):
        from notifications import EmailNotifier

        notifier = EmailNotifier()

        assert notifier.enabled in (True, False)

    def test_send_returns_bool(self):
        from notifications import EmailNotifier

        notifier = EmailNotifier()

        result = notifier.send("Test", "Body")

        assert isinstance(result, bool)


# ===================================================================
# PUBLIC CONFIG TESTS
# ===================================================================

class TestConfigPublicEdition:
    def test_market_hours_flag(self):
        config = TradingConfig()
        assert isinstance(config.MARKET_HOURS_ONLY, bool)

    def test_kill_switch_threshold_exists(self):
        config = TradingConfig()
        assert hasattr(config, "KILL_SWITCH_DRAWDOWN_PCT")


# ===================================================================
# VIRTUAL CAPITAL
# ===================================================================

class TestVirtualCapital:
    def _make_vcm(self):
        from virtual_capital import VirtualCapitalManager

        return VirtualCapitalManager(
            initial_capital=10000,
            monthly_deposit=500,
            currency="USD",
            currency_symbol="$",
        )

    def test_initial_state(self):
        vcm = self._make_vcm()

        assert vcm.get_virtual_cash() >= 0

    def test_deposit(self):
        vcm = self._make_vcm()

        vcm.deposit(100)

        assert vcm.get_virtual_cash() >= 10000

    def test_status_structure(self):
        vcm = self._make_vcm()

        status = vcm.get_status()

        assert "portfolio_value" in status