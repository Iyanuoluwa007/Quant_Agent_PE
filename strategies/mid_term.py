"""
Mid-Term Trend Strategy (Public Edition -- Redacted)

Architecture and interface preserved for review.
Full implementation available in the private production repository.

- Horizon: 5-30 days (swing to position)
- Entry: Confirmed trend setups, MA crossovers, breakouts with volume
- Exit: Trendline break, MA breakdown, trailing stop hit (4%)
- Sizing: ATR-based, risk 2% of sleeve per trade
- AI: Claude receives pre-screened trend candidates + technical data,
      returns structured JSON with BUY/SELL/HOLD recommendations

Signal Pipeline:
  Screener (250 tickers) -> Top 12 trend picks -> Claude analysis
  -> JSON parse -> TradeProposal objects -> Risk engine -> Execution

Claude Integration Pattern:
  - System prompt defines trading persona, trend criteria, exit signals
  - User prompt assembles: sleeve status, existing positions (with exit
    signal checks), pending orders, screener context, market data
  - Response: structured JSON with trailing_stop_pct, expected_hold_days
  - Temperature: 0.3 (consistent trend identification)
  - Exit signal checking prioritized over new entries
"""
import json
import logging
from typing import Optional
from config import TradingConfig
from risk.global_risk import TradeProposal

logger = logging.getLogger(__name__)

# ── Claude System Prompt ──────────────────────────────────────────
# The production system prompt defines:
#   - Trading persona (mid-term trend follower, 5-30 day holds)
#   - Entry criteria (confirmed uptrend: SMA20 > SMA50, pullback
#     to SMA20 + RSI 40-50, MACD histogram turning positive)
#   - Exit signals (price below SMA20 for 2+ days, death cross,
#     RSI divergence, trailing stop at 4%)
#   - Risk rules (2.5x ATR stop-loss, sector diversification,
#     max 3 new positions per cycle)
#   - Position management (check exits before new entries)
#   - Response format (structured JSON, see below)
#
# Response schema:
# {
#     "trend_assessment": "Overall market trend view",
#     "recommendations": [
#         {
#             "ticker": "NVDA",
#             "action": "BUY|SELL|HOLD",
#             "order_type": "limit|market|stop",
#             "quantity": 15,
#             "limit_price": 180.00,
#             "stop_loss": 168.00,
#             "take_profit": null,
#             "trailing_stop_pct": 4.0,
#             "confidence": 0.70,
#             "reasoning": "Trend setup and rationale",
#             "expected_hold_days": 14
#         }
#     ]
# }
SYSTEM_PROMPT = """[REDACTED -- Public Edition]"""


class MidTermStrategy:
    """
    Mid-term trend-following sleeve.

    Receives pre-screened candidates from the MarketScreener (top 12 by
    trend score) and forwards them to Claude for deep analysis.

    Key differences from short-term:
      - Wider stops (2-3x ATR vs 1.5-2x)
      - Prefers limit orders (patience for pullback entries)
      - Checks exit signals on existing positions before new entries
      - Uses trailing stops instead of fixed take-profit
      - Considers sector diversification across the sleeve

    Returns:
      List[TradeProposal] -- validated by risk engine before execution
    """

    SLEEVE_NAME = "mid_term"

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
        Run mid-term trend analysis via Claude.

        Args:
            market_data: {ticker: formatted_technical_data} from market_data.py
            sleeve_positions: Current positions with hold_days and P&L
            sleeve_capital: Available capital for this sleeve
            pending_tickers: Set of tickers with pending orders
            screener_summary: Pre-formatted screener output showing trend rankings

        Returns:
            List of TradeProposal objects for the risk engine.
            Includes trailing_stop_pct for mid-term positions.

        Flow:
            1. Assemble context: sleeve status (2% risk budget), positions
            2. Check exit signals on existing positions (priority)
            3. Append screener context + market data
            4. Call Claude API (temperature=0.3)
            5. Parse JSON, extract recommendations
            6. Convert to TradeProposal with limit orders preferred
        """
        # ── [REDACTED] ─────────────────────────────────────────────
        # Production implementation:
        #   - Builds structured prompt emphasizing exit signal checks
        #   - Calls self.client.messages.create() with trend system prompt
        #   - Parses JSON with trailing_stop_pct and expected_hold_days
        #   - Handles: JSON errors, API errors, empty responses
        #
        # See README.md for architecture details.
        # ──────────────────────────────────────────────────────────
        raise NotImplementedError(
            "Strategy implementation not included in Public Edition. "
            "See README for architecture documentation."
        )
