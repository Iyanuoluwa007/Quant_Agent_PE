"""
Quant Agent v2.1 -- Main Orchestrator (Public Edition)
Multi-strategy AI trading agent with:
  - Market hours gate (skips when closed to save API costs)
  - Regime-aware risk management
  - Volatility targeting + portfolio beta control
  - Claude confidence calibration + meta-model weighting
  - Quarterly ETF review with approval workflow
  - Three independent strategy sleeves
  - Email notifications

Architecture:
  Screener -> Regime Detection -> Strategy Sleeves -> Risk Engine
  -> Intelligence Layer -> Execution -> Dashboard + Notifications

Usage:
  python run.py              # Continuous mode
  python run.py --once       # Single cycle
  python run.py --status     # Check status
  python run.py --backtest   # Run backtests
"""
import json
import time
import logging
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import TradingConfig
from market_data import MarketDataService
from screener import MarketScreener
from strategies.short_term import ShortTermStrategy
from strategies.mid_term import MidTermStrategy
from strategies.long_term import LongTermStrategy
from risk.global_risk import GlobalRiskManager, TradeProposal
from risk.regime_detection import RegimeDetector
from risk.volatility_target import VolatilityTargeter
from risk.beta_control import BetaController
from intelligence.calibration import CalibrationTracker
from intelligence.meta_model import MetaModel
from intelligence.accuracy_tracker import AccuracyTracker
from etf_review import ETFReviewEngine
from notifications import EmailNotifier
from virtual_capital import VirtualCapitalManager


# ===================================================================
# LOGGING
# ===================================================================

def setup_logging(config: TradingConfig):
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(log_format))
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=log_format,
        handlers=[file_handler, console_handler],
    )

logger = logging.getLogger(__name__)


# ===================================================================
# TRADE LOGGER
# ===================================================================

class TradeLogger:
    """Persists trade decisions to JSON for dashboard and analysis."""

    def __init__(self, filepath: str = "trades.json"):
        self.filepath = Path(filepath)
        self._trades = self._load()

    def _load(self) -> list[dict]:
        if self.filepath.exists():
            try:
                return json.loads(self.filepath.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save(self):
        self.filepath.write_text(json.dumps(self._trades, indent=2), encoding="utf-8")

    def log(self, trade: dict):
        trade["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._trades.append(trade)
        self._save()

    def get_recent(self, n: int = 50) -> list[dict]:
        return self._trades[-n:]


# ===================================================================
# BROKER FACTORY
# ===================================================================

def create_broker(config: TradingConfig):
    """Create the appropriate broker client based on config."""
    if config.BROKER == "alpaca":
        from alpaca_client import AlpacaClient
        return AlpacaClient(config)
    else:
        from broker_adapter import BrokerAdapter
        return BrokerAdapter(config)


# ===================================================================
# KILL SWITCH
# ===================================================================

KILL_SWITCH_FILE = Path(".kill_switch")


def is_kill_switch_active() -> bool:
    return KILL_SWITCH_FILE.exists()


def activate_kill_switch(reason: str):
    data = {
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    KILL_SWITCH_FILE.write_text(json.dumps(data, indent=2))
    logger.critical(f"[KILL SWITCH] ACTIVATED: {reason}")


def deactivate_kill_switch():
    KILL_SWITCH_FILE.unlink(missing_ok=True)
    logger.info("[KILL SWITCH] Deactivated")


# ===================================================================
# MARKET HOURS GATE
# ===================================================================

def is_market_open_or_near(broker, config: TradingConfig) -> tuple[bool, str]:
    """
    Check if US market is open or about to open.
    Returns (should_run, reason).
    """
    if not config.MARKET_HOURS_ONLY:
        return True, "Market hours gate disabled"

    try:
        clock = broker.get_market_clock()
        is_open = clock.get("is_open", False)

        if is_open:
            return True, "Market is open"

        # Check if within pre-market buffer
        next_open_str = clock.get("next_open", "")
        if next_open_str and next_open_str != "unknown (fallback mode)":
            try:
                next_open = datetime.fromisoformat(
                    next_open_str.replace("Z", "+00:00")
                )
                now = datetime.now(timezone.utc)
                minutes_until = (next_open - now).total_seconds() / 60

                if minutes_until <= config.PRE_MARKET_BUFFER_MIN:
                    return True, f"Pre-market: {minutes_until:.0f}min to open"
            except Exception:
                pass

        return False, f"Market closed. Next open: {next_open_str}"

    except Exception as e:
        logger.warning(f"Market clock check failed: {e}. Proceeding anyway.")
        return True, "Clock check failed, proceeding"


# ===================================================================
# MAIN AGENT
# ===================================================================

class TradingAgent:
    """
    Main orchestrator. Each cycle:
    1. Check market hours (skip if closed)
    2. Check kill switch (halt if active)
    3. Detect market regime
    4. Compute volatility scalar
    5. Check portfolio beta
    6. Get meta-model state
    7. Run strategy sleeves (with screener pre-filter)
    8. Apply risk checks to all proposals
    9. Execute approved trades
    10. Record predictions for calibration
    11. Check ETF quarterly review
    12. Send notifications
    """

    def __init__(self, config: TradingConfig):
        self.config = config
        self.broker = create_broker(config)
        self.market_data = MarketDataService()
        self.screener = MarketScreener()
        self.risk_manager = GlobalRiskManager(config)
        self.trade_logger = TradeLogger(config.TRADE_LOG_FILE)

        # Strategy sleeves
        self.short_term = ShortTermStrategy(config)
        self.mid_term = MidTermStrategy(config)
        self.long_term = LongTermStrategy(config)

        # Quant modules
        self.regime_detector = RegimeDetector()
        self.vol_targeter = VolatilityTargeter(target_vol_pct=config.VOL_TARGET_PCT)
        self.beta_controller = BetaController()

        # Intelligence modules
        self.calibration = CalibrationTracker()
        self.meta_model = MetaModel(self.calibration)
        self.accuracy_tracker = AccuracyTracker()

        # ETF review
        self.etf_review = ETFReviewEngine(config)

        # Email notifications
        self.notifier = EmailNotifier(config)

        # Virtual capital (tracks agent's allocation within broker account)
        if config.VIRTUAL_CAPITAL_ENABLED:
            self.vcm = VirtualCapitalManager(
                initial_capital=config.VIRTUAL_INITIAL_CAPITAL,
                monthly_deposit=config.VIRTUAL_MONTHLY_DEPOSIT,
                deposit_day=config.VIRTUAL_DEPOSIT_DAY,
                currency=config.CURRENCY,
                currency_symbol=config.CURRENCY_SYMBOL,
            )
        else:
            self.vcm = None

        # Timing
        self._last_short = datetime.min
        self._last_mid = datetime.min
        self._last_long = datetime.min

        logger.info("[AGENT] Initialized -- Public Edition v2.1")

    def run_once(self):
        """Execute a single analysis + trading cycle."""
        now = datetime.now(timezone.utc)

        # ── Gate 1: Kill switch ─────────────────────────────────────
        if is_kill_switch_active():
            logger.warning("[AGENT] Kill switch is active. Skipping cycle.")
            return

        # ── Gate 2: Market hours ────────────────────────────────────
        should_run, reason = is_market_open_or_near(self.broker, self.config)
        if not should_run:
            logger.info(f"[AGENT] Skipping cycle: {reason}")
            return

        logger.info(f"[AGENT] Starting cycle ({reason})")

        # ── Step 1: Get account state ───────────────────────────────
        try:
            broker_cash_info = self.broker.get_account_cash()
            all_positions = self.broker.get_positions()
            pending_orders = self.broker.get_pending_orders()
        except Exception as e:
            logger.error(f"[AGENT] Broker connection failed: {e}")
            self.notifier.send_error_alert(f"Broker connection failed: {e}")
            return

        # Virtual capital overlay: agent uses its allocation, not full broker
        if self.vcm:
            # Check monthly deposit
            deposit = self.vcm.check_monthly_deposit()
            if deposit:
                logger.info(
                    f"[AGENT] Monthly deposit credited: "
                    f"{self.config.CURRENCY_SYMBOL}{deposit:,.2f}"
                )

            cash_info = self.vcm.get_account_cash_for_agent()
        else:
            cash_info = broker_cash_info

        total_value = cash_info.get("total", 0)
        account_cash = cash_info.get("free", 0)
        pending_tickers = {
            self.config.get_plain_symbol(o.get("ticker", ""))
            for o in pending_orders
        }

        split = self.config.get_dynamic_split(total_value)
        sym = self.config.CURRENCY_SYMBOL
        logger.info(
            f"[AGENT] Portfolio: {sym}{total_value:,.2f} | "
            f"Cash: {sym}{account_cash:,.2f} | "
            f"Positions: {len(all_positions)} | "
            f"Split: {split['short_term']:.0f}/{split['mid_term']:.0f}/{split['long_term']:.0f}"
            + (f" | Deposited: {sym}{self.vcm.get_total_deposited():,.2f}" if self.vcm else "")
        )

        # ── Step 2: Drawdown check ─────────────────────────────────
        # Use total deposited (not INITIAL_CAPITAL) as the baseline
        initial = self.vcm.get_total_deposited() if self.vcm else self.config.INITIAL_CAPITAL
        if initial > 0:
            drawdown_pct = ((total_value - initial) / initial) * 100
            if drawdown_pct <= -self.config.KILL_SWITCH_DRAWDOWN_PCT:
                activate_kill_switch(
                    f"Drawdown {drawdown_pct:.1f}% exceeds "
                    f"-{self.config.KILL_SWITCH_DRAWDOWN_PCT}% threshold"
                )
                self.notifier.send_kill_switch_alert(drawdown_pct)
                return

        # ── Step 3: Regime detection ────────────────────────────────
        try:
            regime_state = self.regime_detector.detect()
            regime = regime_state.regime
            risk_mult = regime_state.risk_multiplier
            sleeve_adj = regime_state.sleeve_adjustments
        except Exception as e:
            logger.warning(f"[AGENT] Regime detection failed: {e}. Using NORMAL.")
            regime = "NORMAL"
            risk_mult = 1.0
            sleeve_adj = {"short_term": 1.0, "mid_term": 1.0, "long_term": 1.0}

        logger.info(
            f"[AGENT] Regime: {regime} | Risk mult: {risk_mult:.2f} | "
            f"VIX: {getattr(regime_state, 'vix_level', '?')}"
        )

        # ── Step 4: Volatility targeting ────────────────────────────
        try:
            vol_state = self.vol_targeter.compute()
            vol_scalar = vol_state.exposure_scalar
        except Exception as e:
            logger.warning(f"[AGENT] Vol targeting failed: {e}. Using 1.0.")
            vol_scalar = 1.0

        logger.info(f"[AGENT] Vol scalar: {vol_scalar:.3f}")

        # ── Step 5: Beta check ──────────────────────────────────────
        try:
            beta_state = self.beta_controller.analyze(all_positions, regime)
            if not beta_state.in_range:
                logger.warning(
                    f"[AGENT] Portfolio beta {beta_state.portfolio_beta:.2f} "
                    f"out of range [{beta_state.target_beta_low:.1f}-"
                    f"{beta_state.target_beta_high:.1f}]: "
                    f"{beta_state.suggested_adjustment}"
                )
        except Exception as e:
            logger.warning(f"[AGENT] Beta check failed: {e}")

        # ── Step 6: Meta-model state ────────────────────────────────
        try:
            meta_state = self.meta_model.get_state(regime)
            logger.info(
                f"[AGENT] Meta-model: weight={meta_state.claude_weight:.2f} | "
                f"reason={meta_state.reason}"
            )
        except Exception as e:
            logger.warning(f"[AGENT] Meta-model failed: {e}")

        # ── Step 7: Apply regime adjustments to sleeve allocation ───
        adjusted_split = {}
        for sleeve, base_pct in split.items():
            adj = sleeve_adj.get(sleeve, 1.0)
            adjusted_split[sleeve] = base_pct * adj

        # Normalize to 100%
        total_pct = sum(adjusted_split.values())
        if total_pct > 0:
            adjusted_split = {
                k: (v / total_pct) * 100 for k, v in adjusted_split.items()
            }

        # ── Step 8: Classify existing positions by sleeve ───────────
        sleeve_positions = {
            "short_term": [], "mid_term": [], "long_term": []
        }
        etf_tickers = set(self.config.get_etf_targets().keys())
        trade_history = self.trade_logger.get_recent(200)

        for p in all_positions:
            ticker = self.config.get_plain_symbol(p.get("ticker", ""))
            # Try to find sleeve from trade history
            sleeve = "unknown"
            for t in reversed(trade_history):
                if (self.config.get_plain_symbol(t.get("ticker", "")) == ticker
                        and t.get("status") == "EXECUTED"
                        and t.get("action") == "BUY"):
                    sleeve = t.get("sleeve", "unknown")
                    break

            if sleeve == "unknown":
                sleeve = "long_term" if ticker in etf_tickers else "mid_term"

            p["sleeve"] = sleeve
            if sleeve in sleeve_positions:
                sleeve_positions[sleeve].append(p)

        # ── Step 9: Run strategy sleeves ────────────────────────────
        all_proposals = []

        # Short-term (momentum)
        short_interval = timedelta(minutes=self.config.SHORT_TERM_INTERVAL_MIN)
        if (now - self._last_short >= short_interval
                and adjusted_split.get("short_term", 0) > 0):
            self._last_short = now
            short_capital = total_value * (adjusted_split["short_term"] / 100)

            try:
                screened = self.screener.scan_momentum(top_n=12)
                tickers = [s.ticker for s in screened]
                market_data = {}
                for t in tickers[:10]:
                    data = self.market_data.format_for_claude(t)
                    if data:
                        market_data[t] = data

                screener_summary = self.screener.format_momentum_summary(screened)
                proposals = self.short_term.analyze(
                    market_data=market_data,
                    sleeve_positions=sleeve_positions["short_term"],
                    sleeve_capital=short_capital,
                    pending_tickers=pending_tickers,
                    screener_summary=screener_summary,
                )
                all_proposals.extend(proposals)
            except Exception as e:
                logger.error(f"[AGENT] Short-term analysis failed: {e}")

        # Mid-term (trend)
        mid_interval = timedelta(minutes=self.config.MID_TERM_INTERVAL_MIN)
        if (now - self._last_mid >= mid_interval
                and adjusted_split.get("mid_term", 0) > 0):
            self._last_mid = now
            mid_capital = total_value * (adjusted_split["mid_term"] / 100)

            try:
                screened = self.screener.scan_trend(top_n=12)
                tickers = [s.ticker for s in screened]
                market_data = {}
                for t in tickers[:10]:
                    data = self.market_data.format_for_claude(t)
                    if data:
                        market_data[t] = data

                screener_summary = self.screener.format_trend_summary(screened)
                proposals = self.mid_term.analyze(
                    market_data=market_data,
                    sleeve_positions=sleeve_positions["mid_term"],
                    sleeve_capital=mid_capital,
                    pending_tickers=pending_tickers,
                    screener_summary=screener_summary,
                )
                all_proposals.extend(proposals)
            except Exception as e:
                logger.error(f"[AGENT] Mid-term analysis failed: {e}")

        # Long-term (ETF DCA + rebalance)
        long_interval = timedelta(minutes=self.config.LONG_TERM_INTERVAL_MIN)
        if (now - self._last_long >= long_interval
                and adjusted_split.get("long_term", 0) > 0):
            self._last_long = now
            long_capital = total_value * (adjusted_split["long_term"] / 100)

            try:
                proposals = self.long_term.analyze(
                    sleeve_positions=sleeve_positions["long_term"],
                    sleeve_capital=long_capital,
                    account_cash=account_cash,
                    pending_tickers=pending_tickers,
                    total_portfolio_value=total_value,
                )
                all_proposals.extend(proposals)
            except Exception as e:
                logger.error(f"[AGENT] Long-term analysis failed: {e}")

            # ETF quarterly review
            try:
                if self.etf_review.is_review_due():
                    logger.info("[AGENT] Running quarterly ETF review...")
                    review = self.etf_review.run_review()
                    if review and review.get("changes_proposed", 0) > 0:
                        self.notifier.send_etf_review_alert(
                            review["changes_proposed"]
                        )
            except Exception as e:
                logger.error(f"[AGENT] ETF review failed: {e}")

            # Process ETF sell queue (from approved swaps)
            try:
                sell_queue = self.etf_review.get_sell_queue()
                for item in sell_queue:
                    ticker = item["ticker"]
                    pos = next(
                        (p for p in sleeve_positions["long_term"]
                         if self.config.get_plain_symbol(p.get("ticker", "")) == ticker),
                        None
                    )
                    if pos:
                        all_proposals.append(TradeProposal(
                            sleeve="long_term",
                            ticker=ticker,
                            action="SELL",
                            quantity=abs(pos.get("quantity", 0)),
                            order_type="market",
                            confidence=0.95,
                            reasoning=f"ETF swap approved: {item.get('reason', 'N/A')}",
                        ))
                        self.etf_review.clear_sell_queue_item(ticker)
            except Exception as e:
                logger.error(f"[AGENT] ETF sell queue processing failed: {e}")

        # ── Step 10: Risk check + execute ───────────────────────────
        executed_count = 0
        rejected_count = 0

        for proposal in all_proposals:
            # Apply intelligence adjustments for BUY proposals
            if proposal.action == "BUY":
                # Calibrate confidence via meta-model
                try:
                    effective_conf = self.meta_model.get_effective_confidence(
                        claude_confidence=proposal.confidence,
                        quant_signal_strength=0.5,
                        sleeve=proposal.sleeve,
                        regime=regime,
                    )
                    proposal.confidence = effective_conf

                    # Apply vol targeting scalar to quantity
                    proposal.quantity = round(proposal.quantity * vol_scalar, 4)

                    # Apply meta-model position size multiplier
                    pos_mult = self.meta_model.get_position_size_multiplier(
                        sleeve=proposal.sleeve
                    )
                    proposal.quantity = round(proposal.quantity * pos_mult, 4)

                except Exception as e:
                    logger.warning(f"[AGENT] Intelligence adjustment failed: {e}")

            # Risk check
            result = self.risk_manager.check_trade(
                proposal=proposal,
                account_cash=account_cash,
                total_portfolio_value=total_value,
                all_positions=all_positions,
                pending_tickers=pending_tickers,
            )

            final_qty = result.adjusted_quantity or proposal.quantity

            if result.approved:
                # Execute trade
                try:
                    order = self._execute_order(proposal, final_qty)

                    trade_record = {
                        "sleeve": proposal.sleeve,
                        "ticker": proposal.ticker,
                        "action": proposal.action,
                        "quantity": final_qty,
                        "order_type": proposal.order_type,
                        "confidence": proposal.confidence,
                        "reasoning": proposal.reasoning[:200],
                        "regime": regime,
                        "vol_scalar": vol_scalar,
                        "status": "EXECUTED",
                        "order_id": order.get("id", ""),
                        "fill_price": order.get("fillPrice"),
                    }
                    self.trade_logger.log(trade_record)
                    self.risk_manager.record_trade(trade_record)

                    # Record in virtual capital
                    if self.vcm:
                        fill = order.get("fillPrice", 0)
                        if proposal.action == "BUY" and fill > 0:
                            self.vcm.record_buy(
                                proposal.ticker, final_qty, fill,
                                sleeve=proposal.sleeve,
                            )
                        elif proposal.action == "SELL" and fill > 0:
                            self.vcm.record_sell(
                                proposal.ticker, final_qty, fill,
                            )

                    # Record prediction for calibration
                    if proposal.action == "BUY":
                        try:
                            self.calibration.record_prediction(
                                sleeve=proposal.sleeve,
                                ticker=proposal.ticker,
                                action=proposal.action,
                                confidence=proposal.confidence,
                                entry_price=order.get("fillPrice", 0),
                                stop_loss=proposal.stop_loss,
                                take_profit=proposal.take_profit,
                                regime=regime,
                            )
                        except Exception:
                            pass

                    # Tag position with sleeve
                    if hasattr(self.broker, 'set_sleeve'):
                        self.broker.set_sleeve(
                            self.config.get_plain_symbol(proposal.ticker),
                            proposal.sleeve
                        )

                    pending_tickers.add(
                        self.config.get_plain_symbol(proposal.ticker)
                    )
                    account_cash -= final_qty * (
                        proposal.limit_price or proposal.stop_price or 0
                    )
                    executed_count += 1

                except Exception as e:
                    logger.error(
                        f"[AGENT] Execution failed for "
                        f"{proposal.action} {proposal.ticker}: {e}"
                    )
                    self.trade_logger.log({
                        "sleeve": proposal.sleeve,
                        "ticker": proposal.ticker,
                        "action": proposal.action,
                        "quantity": final_qty,
                        "status": "FAILED",
                        "error": str(e),
                    })
            else:
                self.trade_logger.log({
                    "sleeve": proposal.sleeve,
                    "ticker": proposal.ticker,
                    "action": proposal.action,
                    "quantity": proposal.quantity,
                    "status": "REJECTED",
                    "reasons": result.rejection_reasons,
                })
                rejected_count += 1

        # ── Step 11: Daily summary email ────────────────────────────
        try:
            self.notifier.send_daily_summary(broker_data=cash_info)
        except Exception:
            pass

        logger.info(
            f"[AGENT] Cycle complete: {executed_count} executed, "
            f"{rejected_count} rejected, "
            f"{len(all_proposals)} total proposals"
        )

    def _execute_order(self, proposal: TradeProposal, quantity: float) -> dict:
        """Execute a trade order through the broker."""
        symbol = self.config.get_broker_symbol(proposal.ticker)
        qty = quantity if proposal.action == "BUY" else -quantity

        if proposal.order_type == "market":
            return self.broker.place_market_order(symbol, qty)
        elif proposal.order_type == "limit" and proposal.limit_price:
            return self.broker.place_limit_order(
                symbol, qty, proposal.limit_price
            )
        elif proposal.order_type == "stop" and proposal.stop_price:
            return self.broker.place_stop_order(
                symbol, qty, proposal.stop_price
            )
        elif proposal.order_type == "stop_limit" and proposal.stop_price and proposal.limit_price:
            return self.broker.place_stop_limit_order(
                symbol, qty, proposal.stop_price, proposal.limit_price
            )
        else:
            return self.broker.place_market_order(symbol, qty)

    def run_continuous(self):
        """Run in continuous loop with sleep between cycles."""
        logger.info("[AGENT] Starting continuous mode...")

        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                logger.info("[AGENT] Interrupted. Shutting down.")
                break
            except Exception as e:
                logger.error(f"[AGENT] Cycle error: {e}", exc_info=True)
                self.notifier.send_error_alert(str(e))

            # Sleep until next cycle
            interval = self.config.SHORT_TERM_INTERVAL_MIN * 60
            logger.info(
                f"[AGENT] Sleeping {self.config.SHORT_TERM_INTERVAL_MIN} min..."
            )
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("[AGENT] Interrupted during sleep. Shutting down.")
                break

    def get_status(self) -> dict:
        """Get current agent status."""
        try:
            broker_cash = self.broker.get_account_cash()
            positions = self.broker.get_positions()
            clock = self.broker.get_market_clock()
        except Exception as e:
            return {"error": str(e)}

        # Virtual capital overlay
        if self.vcm:
            vcap = self.vcm.get_status()
            total = vcap["portfolio_value"]
            cash = vcap["virtual_cash"]
        else:
            total = broker_cash.get("total", 0)
            cash = broker_cash.get("free", 0)

        split = self.config.get_dynamic_split(total)
        sym = self.config.CURRENCY_SYMBOL

        status = {
            "portfolio_value": total,
            "cash": cash,
            "positions": len(positions),
            "sleeve_split": split,
            "market_open": clock.get("is_open", False),
            "kill_switch": is_kill_switch_active(),
            "broker": self.config.BROKER,
            "broker_total": broker_cash.get("total", 0),
        }

        if self.vcm:
            status["virtual_capital"] = {
                "total_deposited": self.vcm.get_total_deposited(),
                "pnl": round(total - self.vcm.get_total_deposited(), 2),
                "monthly_deposit": self.config.VIRTUAL_MONTHLY_DEPOSIT,
            }

        return status


# ===================================================================
# CLI ENTRY POINT
# ===================================================================

def main():
    ap = argparse.ArgumentParser(description="Quant Agent v2.1 -- Public Edition")
    ap.add_argument("--once", action="store_true", help="Run single cycle")
    ap.add_argument("--status", action="store_true", help="Show status")
    ap.add_argument("--backtest", action="store_true", help="Run backtests")
    ap.add_argument("--reset", type=float, help="Reset simulated broker to N dollars")
    args = ap.parse_args()

    config = TradingConfig()
    setup_logging(config)

    errors = config.validate()
    if errors and not args.status and not args.reset:
        for e in errors:
            logger.error(f"Config error: {e}")
        if config.BROKER != "simulated":
            sys.exit(1)
        logger.warning("[AGENT] Running in simulated mode without full config")

    if args.reset:
        from broker_adapter import BrokerAdapter
        broker = BrokerAdapter(config)
        broker.reset(args.reset)
        print(f"[OK] Simulated broker reset to ${args.reset:,.2f}")
        return

    if args.backtest:
        logger.info("[AGENT] Running backtests...")
        from quant.backtester import BacktestEngine
        engine = BacktestEngine(initial_capital=config.INITIAL_CAPITAL)
        # Run momentum backtest
        result = engine.run_momentum_backtest(
            tickers=config.SHORT_TERM_WATCHLIST[:8],
            period="1y",
        )
        if result:
            print(result.summary())
        # Run trend backtest
        result = engine.run_trend_backtest(
            tickers=config.MID_TERM_WATCHLIST[:8],
            period="1y",
        )
        if result:
            print(result.summary())
        return

    agent = TradingAgent(config)

    if args.status:
        status = agent.get_status()
        print("\n" + "=" * 50)
        print("  Quant Agent v2.1 -- Status")
        print("=" * 50)
        for k, v in status.items():
            if isinstance(v, dict):
                print(f"  {k}:")
                for kk, vv in v.items():
                    print(f"    {kk}: {vv}")
            elif isinstance(v, float):
                print(f"  {k}: ${v:,.2f}" if "value" in k or "cash" in k else f"  {k}: {v}")
            else:
                print(f"  {k}: {v}")
        print("=" * 50 + "\n")
        return

    if args.once:
        agent.run_once()
    else:
        agent.run_continuous()
