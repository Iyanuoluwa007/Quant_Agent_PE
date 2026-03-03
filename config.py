"""
Quant Agent v2.1 -- Public Edition Configuration
Multi-strategy AI trading system with dynamic allocation.

This is the PUBLIC version. Proprietary parameters, production prompts,
and real broker credentials are not included. See README for details.
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SleeveConfig:
    """Config for a single strategy sleeve."""
    name: str
    allocation_pct: float
    max_position_pct: float
    max_positions: int
    max_daily_loss_pct: float


@dataclass
class TradingConfig:
    # ── Broker ──────────────────────────────────────────────────────
    # "simulated" for paper testing, "alpaca" for Alpaca paper/live
    BROKER: str = os.getenv("BROKER", "simulated")
    INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "100000"))

    # ── Virtual Capital ─────────────────────────────────────────────
    # The agent manages a virtual allocation WITHIN the broker account.
    # Alpaca paper may have $20K but agent only trades with its slice.
    VIRTUAL_CAPITAL_ENABLED: bool = os.getenv("VIRTUAL_CAPITAL_ENABLED", "true").lower() == "true"
    VIRTUAL_INITIAL_CAPITAL: float = float(os.getenv("VIRTUAL_INITIAL_CAPITAL", "12500"))
    VIRTUAL_MONTHLY_DEPOSIT: float = float(os.getenv("VIRTUAL_MONTHLY_DEPOSIT", "625"))
    VIRTUAL_DEPOSIT_DAY: int = int(os.getenv("VIRTUAL_DEPOSIT_DAY", "1"))

    # ── Alpaca API (for real trading) ───────────────────────────────
    ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "")
    ALPACA_API_SECRET: str = os.getenv("ALPACA_API_SECRET", "")
    ALPACA_ENV: str = os.getenv("ALPACA_ENV", "paper")

    # ── Claude API ──────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

    # ── Currency ────────────────────────────────────────────────────
    CURRENCY: str = os.getenv("CURRENCY", "USD")
    CURRENCY_SYMBOL: str = os.getenv("CURRENCY_SYMBOL", "$")

    # ── Market Hours Gate ───────────────────────────────────────────
    # Skip cycles when US markets are closed to save API costs.
    MARKET_HOURS_ONLY: bool = os.getenv("MARKET_HOURS_ONLY", "true").lower() == "true"
    # Pre-market analysis buffer (minutes before open)
    PRE_MARKET_BUFFER_MIN: int = int(os.getenv("PRE_MARKET_BUFFER_MIN", "30"))

    # ── Dynamic Sleeve Allocation ───────────────────────────────────
    FORCE_SHORT_PCT: float = float(os.getenv("FORCE_SHORT_PCT", "0"))
    FORCE_MID_PCT: float = float(os.getenv("FORCE_MID_PCT", "0"))
    FORCE_LONG_PCT: float = float(os.getenv("FORCE_LONG_PCT", "0"))

    def get_dynamic_split(self, total_value: float) -> dict[str, float]:
        """
        Dynamic sleeve allocation based on account size.
        Small accounts prioritize ETF accumulation.
        Active trading scales up as capital grows.
        """
        if self.FORCE_SHORT_PCT + self.FORCE_MID_PCT + self.FORCE_LONG_PCT > 0:
            return {
                "short_term": self.FORCE_SHORT_PCT,
                "mid_term": self.FORCE_MID_PCT,
                "long_term": self.FORCE_LONG_PCT,
            }

        if total_value < 500:
            return {"short_term": 0.0, "mid_term": 5.0, "long_term": 95.0}
        elif total_value < 1000:
            return {"short_term": 5.0, "mid_term": 15.0, "long_term": 80.0}
        elif total_value < 2000:
            return {"short_term": 10.0, "mid_term": 20.0, "long_term": 70.0}
        elif total_value < 5000:
            return {"short_term": 15.0, "mid_term": 25.0, "long_term": 60.0}
        else:
            return {"short_term": 20.0, "mid_term": 30.0, "long_term": 50.0}

    # ── Global Risk Limits ──────────────────────────────────────────
    MAX_TOTAL_EXPOSURE_PCT: float = 80.0
    MIN_CASH_RESERVE_PCT: float = 15.0
    MAX_SECTOR_CONCENTRATION_PCT: float = 35.0
    MAX_CORRELATION_OVERLAP: int = 4
    MAX_TRADES_PER_DAY: int = 15
    MAX_DAILY_LOSS_PCT: float = 2.0

    # ── Drawdown Kill Switch ────────────────────────────────────────
    KILL_SWITCH_DRAWDOWN_PCT: float = float(os.getenv("KILL_SWITCH_DRAWDOWN_PCT", "20.0"))

    # ── Per-trade risk ──────────────────────────────────────────────
    def get_max_risk_per_trade_pct(self, total_value: float) -> float:
        if total_value < 500:
            return 1.0
        elif total_value < 1000:
            return 1.5
        elif total_value < 2000:
            return 2.0
        else:
            return 2.5

    # ── Sleeve-specific configs ─────────────────────────────────────

    def get_sleeve_config(self, sleeve_name: str, total_value: float) -> SleeveConfig:
        split = self.get_dynamic_split(total_value)

        configs = {
            "short_term": SleeveConfig(
                name="short_term",
                allocation_pct=split["short_term"],
                max_position_pct=20.0,
                max_positions=3,
                max_daily_loss_pct=3.0,
            ),
            "mid_term": SleeveConfig(
                name="mid_term",
                allocation_pct=split["mid_term"],
                max_position_pct=25.0,
                max_positions=4,
                max_daily_loss_pct=4.0,
            ),
            "long_term": SleeveConfig(
                name="long_term",
                allocation_pct=split["long_term"],
                max_position_pct=35.0,
                max_positions=10,
                max_daily_loss_pct=6.0,
            ),
        }

        if sleeve_name not in configs:
            raise ValueError(f"Unknown sleeve: {sleeve_name}")
        return configs[sleeve_name]

    # ── Short-Term Watchlist (public subset) ────────────────────────
    SHORT_TERM_WATCHLIST: list = field(default_factory=lambda: [
        "AAPL", "MSFT", "NVDA", "TSLA", "META", "AMZN", "GOOGL",
        "AMD", "NFLX", "CRM", "COIN", "PLTR",
    ])
    SHORT_TERM_MAX_HOLD_DAYS: int = 3
    SHORT_TERM_STOP_LOSS_PCT: float = 2.0
    SHORT_TERM_TAKE_PROFIT_PCT: float = 4.0

    # ── Mid-Term Watchlist (public subset) ──────────────────────────
    MID_TERM_WATCHLIST: list = field(default_factory=lambda: [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META",
        "JPM", "V", "MA", "LLY", "UNH", "AVGO", "COST",
        "XOM", "CVX", "GS", "CAT",
    ])
    MID_TERM_STOP_LOSS_PCT: float = 5.0
    MID_TERM_TRAILING_STOP_PCT: float = 4.0

    # ── Long-Term ETF Targets ──────────────────────────────────────
    LONG_TERM_ETF_TARGETS: dict = field(default_factory=lambda: {
        "VOO": 0.30,    # S&P 500
        "QQQ": 0.20,    # Nasdaq 100
        "VTI": 0.15,    # Total US Market
        "VXUS": 0.10,   # International
        "BND": 0.10,    # Bonds
        "VNQ": 0.05,    # REITs
        "GLD": 0.05,    # Gold
        "ARKK": 0.05,   # Innovation/Growth
    })
    LONG_TERM_REBALANCE_THRESHOLD_PCT: float = 5.0

    # ── ETF Quarterly Review ────────────────────────────────────────
    ETF_REVIEW_INTERVAL_DAYS: int = 90

    def get_etf_targets(self) -> dict:
        """Get active ETF targets (with overrides if approved)."""
        from pathlib import Path
        override_file = Path("etf_overrides.json")
        if override_file.exists():
            try:
                import json
                data = json.loads(override_file.read_text(encoding="utf-8"))
                targets = data.get("targets", {})
                if targets:
                    return targets
            except Exception:
                pass
        return dict(self.LONG_TERM_ETF_TARGETS)

    def get_dca_amount(self, total_value: float) -> float:
        if total_value < 500:
            return 25.0
        elif total_value < 1000:
            return 50.0
        elif total_value < 2000:
            return 100.0
        elif total_value < 5000:
            return 200.0
        else:
            return 500.0

    # ── Volatility Targeting ────────────────────────────────────────
    VOL_TARGET_PCT: float = float(os.getenv("VOL_TARGET_PCT", "12.0"))

    # ── Analysis Intervals ──────────────────────────────────────────
    SHORT_TERM_INTERVAL_MIN: int = 30
    MID_TERM_INTERVAL_MIN: int = 120
    LONG_TERM_INTERVAL_MIN: int = 1440
    STALE_ORDER_TTL_MIN: int = 120

    # ── Logging ─────────────────────────────────────────────────────
    LOG_FILE: str = os.getenv("LOG_FILE", "trading_agent.log")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    TRADE_LOG_FILE: str = os.getenv("TRADE_LOG_FILE", "trades.json")

    # ── Dashboard ───────────────────────────────────────────────────
    DASHBOARD_TOKEN: str = os.getenv("DASHBOARD_TOKEN", "")

    def get_broker_symbol(self, symbol: str) -> str:
        return symbol

    def get_plain_symbol(self, broker_symbol: str) -> str:
        if "_" in broker_symbol:
            return broker_symbol.split("_")[0]
        return broker_symbol

    def validate(self) -> list[str]:
        errors = []
        if not self.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is required")
        if self.BROKER == "alpaca":
            if not self.ALPACA_API_KEY:
                errors.append("ALPACA_API_KEY is required")
            if not self.ALPACA_API_SECRET:
                errors.append("ALPACA_API_SECRET is required")
        return errors
