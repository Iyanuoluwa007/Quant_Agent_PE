"""
Quant Agent v2.1 -- Main Orchestrator (Public Edition)
Sanitized for public demo: all proprietary logic, API keys, and live execution removed.
"""

import json
import time
import logging
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path


# ===================================================================
# DEMO CONFIGURATION
# ===================================================================

class TradingConfig:
    """
    Generic configuration used for demonstration purposes.
    All production credentials, endpoints, and proprietary
    parameters have been removed.
    """

    BROKER = "SIMULATED"
    LOG_FILE = "agent.log"
    LOG_LEVEL = "INFO"

    MARKET_HOURS_ONLY = True
    PRE_MARKET_BUFFER_MIN = 30

    SHORT_TERM_INTERVAL_MIN = 15
    MID_TERM_INTERVAL_MIN = 60
    LONG_TERM_INTERVAL_MIN = 1440

    CURRENCY = "USD"
    CURRENCY_SYMBOL = "$"

    INITIAL_CAPITAL = 100_000

    TRADE_LOG_FILE = "trades_demo.json"

    def validate(self):
        return []

    def get_dynamic_split(self, total_value):
        return {"short_term": 30, "mid_term": 40, "long_term": 30}

    def get_plain_symbol(self, ticker):
        return ticker.upper()

    def get_etf_targets(self):
        return {"DEMOETF": 0.5}

    def get_broker_symbol(self, ticker):
        return ticker.upper()


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

    def __init__(self, filepath: str = "trades_demo.json"):
        self.filepath = Path(filepath)
        self._trades = self._load()

    def _load(self):

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

    def get_recent(self, n: int = 50):
        return self._trades[-n:]


# ===================================================================
# KILL SWITCH (DEMO)
# ===================================================================

KILL_SWITCH_FILE = Path(".kill_switch")


def is_kill_switch_active():

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
# DEMO BROKER
# ===================================================================

class DemoBroker:
    """
    Simulated broker used for demonstration.
    Does not connect to any real brokerage.
    """

    def get_market_clock(self):
        return {"is_open": True, "next_open": "2026-01-01T14:30:00Z"}

    def get_account_cash(self):
        return {"total": 100_000, "free": 50_000}

    def get_positions(self):
        return [{"ticker": "DEMOETF", "quantity": 10}]

    def get_pending_orders(self):
        return []

    def place_market_order(self, symbol, qty):
        return {"id": f"demo_order_{symbol}", "fillPrice": 100}

    def place_limit_order(self, symbol, qty, price):
        return {"id": f"demo_order_{symbol}", "fillPrice": price}

    def place_stop_order(self, symbol, qty, stop_price):
        return {"id": f"demo_order_{symbol}", "fillPrice": stop_price}

    def place_stop_limit_order(self, symbol, qty, stop_price, limit_price):
        return {"id": f"demo_order_{symbol}", "fillPrice": limit_price}


def create_broker(config: TradingConfig):

    return DemoBroker()


# ===================================================================
# PLACEHOLDER SERVICES
# ===================================================================

class MarketDataService:

    def format_for_agent(self, ticker):

        return {
            "price": 100,
            "volume": 1000
        }


class MarketScreener:
    """
    Simplified screener for demo purposes.
    """

    def scan_momentum(self, top_n=10):

        return [f"DEMO{i}" for i in range(top_n)]

    def scan_trend(self, top_n=10):

        return [f"DEMO{i}" for i in range(top_n)]

    def format_momentum_summary(self, tickers):

        return "Momentum scan (demo data)"

    def format_trend_summary(self, tickers):

        return "Trend scan (demo data)"


# ===================================================================
# STRATEGY PLACEHOLDERS
# ===================================================================

class ShortTermStrategy:

    def __init__(self, config):
        self.config = config

    def analyze(self, **kwargs):
        return []


class MidTermStrategy:

    def __init__(self, config):
        self.config = config

    def analyze(self, **kwargs):
        return []


class LongTermStrategy:

    def __init__(self, config):
        self.config = config

    def analyze(self, **kwargs):
        return []


# ===================================================================
# RISK MANAGEMENT (SANITIZED)
# ===================================================================

class GlobalRiskManager:

    def __init__(self, config):
        self.config = config

    def check_trade(self, proposal, **kwargs):

        return type(
            "RiskResult",
            (),
            {
                "approved": True,
                "adjusted_quantity": proposal.quantity,
                "rejection_reasons": [],
            },
        )()

    def record_trade(self, trade):
        pass


# ===================================================================
# SUPPORTING COMPONENTS (PLACEHOLDERS)
# ===================================================================

class EmailNotifier:

    def __init__(self, config):
        self.config = config

    def send_daily_summary(self, broker_data):
        print("[DEMO] Daily summary sent")

    def send_error_alert(self, message):
        print(f"[DEMO] Error alert: {message}")


# ===================================================================
# TRADE PROPOSAL
# ===================================================================

class TradeProposal:

    def __init__(
        self,
        sleeve,
        ticker,
        action,
        quantity=0,
        order_type="market",
        confidence=1.0,
        reasoning="Demo",
        limit_price=None,
        stop_price=None,
    ):

        self.sleeve = sleeve
        self.ticker = ticker
        self.action = action
        self.quantity = quantity
        self.order_type = order_type
        self.confidence = confidence
        self.reasoning = reasoning

        self.limit_price = limit_price
        self.stop_price = stop_price


# ===================================================================
# MARKET HOURS CHECK
# ===================================================================

def is_market_open_or_near(broker, config):

    if not config.MARKET_HOURS_ONLY:
        return True, "Market hours check disabled"

    try:

        clock = broker.get_market_clock()

        return clock.get("is_open", True), "Demo market open"

    except Exception:

        return True, "Clock unavailable (demo fallback)"


# ===================================================================
# TRADING AGENT
# ===================================================================

class TradingAgent:

    def __init__(self, config):

        self.config = config

        self.broker = create_broker(config)

        self.market_data = MarketDataService()
        self.screener = MarketScreener()

        self.risk_manager = GlobalRiskManager(config)

        self.trade_logger = TradeLogger(config.TRADE_LOG_FILE)

        self.short_term = ShortTermStrategy(config)
        self.mid_term = MidTermStrategy(config)
        self.long_term = LongTermStrategy(config)

        self.notifier = EmailNotifier(config)

        logger.info("[AGENT] Initialized -- Public Edition")

    # ---------------------------------------------------------------

    def run_once(self):

        if is_kill_switch_active():

            logger.warning("[AGENT] Kill switch active. Skipping cycle.")

            return

        should_run, reason = is_market_open_or_near(self.broker, self.config)

        if not should_run:

            logger.info(f"[AGENT] Skipping cycle: {reason}")

            return

        logger.info(f"[AGENT] Running cycle ({reason})")

        proposals = [
            TradeProposal("short_term", "DEMO1", "BUY", quantity=10),
            TradeProposal("mid_term", "DEMO2", "SELL", quantity=5),
        ]

        for proposal in proposals:

            logger.info(
                f"[AGENT] Executing {proposal.action} {proposal.ticker} x{proposal.quantity}"
            )

            self.trade_logger.log(
                {
                    "sleeve": proposal.sleeve,
                    "ticker": proposal.ticker,
                    "action": proposal.action,
                    "quantity": proposal.quantity,
                    "status": "EXECUTED",
                }
            )

        self.notifier.send_daily_summary(None)

    # ---------------------------------------------------------------

    def run_continuous(self):

        while True:

            try:

                self.run_once()

                time.sleep(self.config.SHORT_TERM_INTERVAL_MIN * 60)

            except KeyboardInterrupt:

                logger.info("[AGENT] Interrupted. Shutting down.")

                break

    # ---------------------------------------------------------------

    def get_status(self):

        return {
            "portfolio_value": 100_000,
            "cash": 50_000,
            "positions": 2,
            "kill_switch": is_kill_switch_active(),
        }


# ===================================================================
# CLI ENTRY POINT
# ===================================================================

def main():

    parser = argparse.ArgumentParser(
        description="Quant Agent v2.1 -- Public Edition"
    )

    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")

    args = parser.parse_args()

    config = TradingConfig()

    setup_logging(config)

    agent = TradingAgent(config)

    if args.status:

        print(agent.get_status())

        return

    if args.once:

        agent.run_once()

    else:

        agent.run_continuous()


if __name__ == "__main__":
    main()