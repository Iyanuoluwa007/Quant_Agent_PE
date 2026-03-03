"""
Short-Term Momentum Strategy (Public Edition -- Redacted)

Architecture and interface preserved for review.
Full implementation available in the private production repository.

- Horizon: 1-3 days (intraday to swing)
- Entry: Momentum breakouts, RSI divergence, volume spikes
- Exit: Tight stop-loss (2%), take-profit (4%), time-based (3 day max)
- Sizing: ATR-based, risk 1% of sleeve per trade
- AI: Claude receives pre-screened candidates + technical data,
      returns structured JSON with BUY/SELL/HOLD recommendations

Signal Pipeline:
  Screener (250 tickers) -> Top 12 momentum picks -> Claude analysis
  -> JSON parse -> TradeProposal objects -> Risk engine -> Execution

Claude Integration Pattern:
  - System prompt defines trading persona, signal criteria, and rules
  - User prompt assembles: sleeve status, existing positions, pending
    orders, screener context, and detailed market data per ticker
  - Response: structured JSON with ticker, action, order type,
    quantity, stop/target, confidence (0-1), reasoning
  - Temperature: 0.3 (low creativity, consistent analysis)
  - Existing positions managed FIRST (exit before new entries)
"""
import json
import logging
from typing import Optional
from config import TradingConfig
from risk.global_risk import TradeProposal

logger = logging.getLogger(__name__)

# ── Claude System Prompt ──────────────────────────────────────────
# The production system prompt defines:
#   - Trading persona (short-term momentum, 1-3 day holds)
#   - Signal criteria (RSI oversold bounce, MACD crossover,
#     volume spikes > 2x avg, price near SMA20 support)
#   - Risk rules (mandatory stop-loss, max 1-2% risk per trade,
#     3-day max hold, quality over quantity)
#   - Position management (manage existing before adding new)
#   - Response format (structured JSON, see below)
#
# Response schema:
# {
#     "market_view": "Brief momentum assessment",
#     "recommendations": [
#         {
#             "ticker": "AAPL",
#             "action": "BUY|SELL|HOLD",
#             "order_type": "market|limit",
#             "quantity": 10,
#             "limit_price": null,
#             "stop_loss": 148.00,
#             "take_profit": 158.00,
#             "confidence": 0.75,
#             "reasoning": "Why this trade NOW",
#             "urgency": "high|medium|low"
#         }
#     ]
# }
SYSTEM_PROMPT = """[REDACTED -- Public Edition]"""


class ShortTermStrategy:
    """
    Short-term momentum trading sleeve.

    Receives pre-screened candidates from the MarketScreener (top 12 by
    momentum score) and forwards them to Claude for deep analysis.

    Claude sees:
      - Sleeve capital and risk budget
      - Current positions with hold duration and P&L
      - Pending orders (duplicate prevention)
      - Screener ranking context
      - Full technical data per ticker (OHLCV, RSI, MACD, SMAs, ATR)

    Returns:
      List[TradeProposal] -- validated by risk engine before execution
    """

    SLEEVE_NAME = "short_term"

    def __init__(self, config: TradingConfig):
        self.config = config
        # Production: self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def analyze(
        self,
        market_data: dict[str, str],
        sleeve_positions: list[dict],
        sleeve_capital: float,
        pending_tickers: set,
        screener_summary: str = "",
    ) -> list[TradeProposal]:
        """
        Run short-term momentum analysis via Claude.

        Args:
            market_data: {ticker: formatted_technical_data} from market_data.py
            sleeve_positions: Current positions in this sleeve with hold_days
            sleeve_capital: Available capital for this sleeve
            pending_tickers: Set of tickers with pending orders (skip these)
            screener_summary: Pre-formatted screener output showing rankings

        Returns:
            List of TradeProposal objects for the risk engine to validate.
            Each proposal includes: ticker, action, quantity, order_type,
            stop_loss, take_profit, confidence, reasoning.

        Flow:
            1. Assemble context: sleeve status, positions, pending, screener
            2. Append market data for each ticker
            3. Call Claude API (temperature=0.3)
            4. Parse JSON response, strip markdown fences if present
            5. Convert recommendations to TradeProposal objects
            6. Filter out HOLD recommendations
            7. Log market view and each recommendation
        """
        # ── [REDACTED] ─────────────────────────────────────────────
        # Production implementation:
        #   - Builds structured prompt from sleeve state + market data
        #   - Calls self.client.messages.create() with system prompt
        #   - Parses JSON response into TradeProposal list
        #   - Handles: JSON parse errors, API errors, empty responses
        #
        # See README.md for architecture details.
        # ──────────────────────────────────────────────────────────
        raise NotImplementedError(
            "Strategy implementation not included in Public Edition. "
            "See README for architecture documentation."
        )
