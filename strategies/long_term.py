"""
Long-Term ETF Core Strategy
- Horizon: Months to years (buy and hold)
- Approach: Systematic DCA into diversified ETFs
- Rebalance: When any holding drifts > 5% from target weight
- No Claude needed for this sleeve — it's purely rule-based
"""
import logging
from typing import Optional
import yfinance as yf
from config import TradingConfig
from risk.global_risk import TradeProposal

logger = logging.getLogger(__name__)


class LongTermStrategy:
    """Long-term ETF core sleeve — systematic DCA + rebalancing."""

    SLEEVE_NAME = "long_term"

    def __init__(self, config: TradingConfig):
        self.config = config
        self._price_cache: dict[str, float] = {}

    def _get_current_price(self, ticker: str) -> float:
        """Fetch current price via yfinance. Caches results."""
        if ticker in self._price_cache:
            return self._price_cache[ticker]
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if not hist.empty:
                price = round(float(hist["Close"].iloc[-1]), 2)
                self._price_cache[ticker] = price
                return price
        except Exception as e:
            logger.warning(f"[LONG] Failed to fetch price for {ticker}: {e}")
        return 0.0

    def analyze(
        self,
        sleeve_positions: list[dict],
        sleeve_capital: float,
        account_cash: float,
        pending_tickers: set,
        total_portfolio_value: float = 0,
    ) -> list[TradeProposal]:
        """
        Rule-based ETF analysis:
        1. Check if rebalance needed
        2. If not, DCA into underweight positions
        """
        targets = self.config.LONG_TERM_ETF_TARGETS
        threshold = self.config.LONG_TERM_REBALANCE_THRESHOLD_PCT
        dca_amount = self.config.get_dca_amount(total_portfolio_value or sleeve_capital)
        proposals = []

        # Build current weights
        position_map = {}
        total_invested = 0
        for p in sleeve_positions:
            ticker = self.config.get_plain_symbol(p.get("ticker", ""))
            value = abs(p.get("currentPrice", 0) * p.get("quantity", 0))
            position_map[ticker] = {
                "value": value,
                "quantity": p.get("quantity", 0),
                "price": p.get("currentPrice", 0),
            }
            total_invested += value

        # Use sleeve capital as the reference (not just invested)
        reference = max(sleeve_capital, total_invested)

        logger.info(
            f"[LONG] Sleeve capital: ${sleeve_capital:,.2f} | "
            f"Invested: ${total_invested:,.2f}"
        )

        # ── Phase 1: Check for rebalancing ──────────────────────────
        rebalance_needed = False
        if total_invested > 0:
            for etf, target_weight in targets.items():
                current_value = position_map.get(etf, {}).get("value", 0)
                current_weight = current_value / reference
                drift = abs(current_weight - target_weight) * 100

                if drift > threshold:
                    rebalance_needed = True
                    logger.info(
                        f"[LONG] {etf}: target={target_weight:.0%} "
                        f"actual={current_weight:.0%} drift={drift:.1f}%"
                    )

        if rebalance_needed:
            logger.info("[LONG] Rebalancing triggered!")
            proposals.extend(
                self._generate_rebalance_orders(
                    position_map, reference, targets, pending_tickers
                )
            )
        else:
            # ── Phase 2: DCA into underweight ETFs ──────────────────
            logger.info("[LONG] No rebalance needed. Running DCA.")
            proposals.extend(
                self._generate_dca_orders(
                    position_map, reference, targets,
                    dca_amount, pending_tickers
                )
            )

        return proposals

    def _generate_rebalance_orders(
        self,
        position_map: dict,
        reference: float,
        targets: dict,
        pending_tickers: set,
    ) -> list[TradeProposal]:
        """Generate orders to bring portfolio back to target weights."""
        proposals = []

        for etf, target_weight in targets.items():
            if etf in pending_tickers:
                continue

            current_value = position_map.get(etf, {}).get("value", 0)
            current_price = position_map.get(etf, {}).get("price", 0)
            if current_price <= 0:
                current_price = self._get_current_price(etf)
            target_value = reference * target_weight
            diff = target_value - current_value

            if current_price <= 0:
                logger.warning(f"[LONG] Skipping {etf} rebalance -- no price")
                continue

            # Only rebalance if diff is meaningful (> $50)
            if abs(diff) < 50:
                continue

            if diff > 0:
                # Need to BUY more
                qty = round(diff / current_price, 4)
                proposals.append(TradeProposal(
                    sleeve=self.SLEEVE_NAME,
                    ticker=etf,
                    action="BUY",
                    quantity=qty,
                    order_type="market",
                    confidence=0.90,  # High confidence — rule-based
                    reasoning=(
                        f"Rebalance: {etf} underweight. "
                        f"Target ${target_value:.0f}, "
                        f"Current ${current_value:.0f}, "
                        f"buying ${diff:.0f}"
                    ),
                ))
            elif diff < 0:
                # Need to SELL some
                qty = round(abs(diff) / current_price, 4)
                proposals.append(TradeProposal(
                    sleeve=self.SLEEVE_NAME,
                    ticker=etf,
                    action="SELL",
                    quantity=qty,
                    order_type="market",
                    confidence=0.90,
                    reasoning=(
                        f"Rebalance: {etf} overweight. "
                        f"Target ${target_value:.0f}, "
                        f"Current ${current_value:.0f}, "
                        f"selling ${abs(diff):.0f}"
                    ),
                ))

        logger.info(f"[LONG] Generated {len(proposals)} rebalance orders")
        return proposals

    def _generate_dca_orders(
        self,
        position_map: dict,
        reference: float,
        targets: dict,
        dca_budget: float,
        pending_tickers: set,
    ) -> list[TradeProposal]:
        """
        DCA: distribute budget into the most underweight ETFs.
        Prioritize ETFs furthest below target weight.
        """
        proposals = []

        # Calculate underweight scores
        underweight = []
        for etf, target_weight in targets.items():
            if etf in pending_tickers:
                continue
            current_value = position_map.get(etf, {}).get("value", 0)
            current_weight = current_value / reference if reference > 0 else 0
            gap = target_weight - current_weight
            if gap > 0:
                underweight.append((etf, gap, target_weight))

        if not underweight:
            logger.info("[LONG] All ETFs at or above target. No DCA needed.")
            return []

        # Sort by gap (most underweight first)
        underweight.sort(key=lambda x: x[1], reverse=True)

        # Distribute DCA budget proportionally to gaps
        total_gap = sum(g for _, g, _ in underweight)
        remaining_budget = dca_budget

        for etf, gap, target_weight in underweight:
            if remaining_budget <= 10:
                break

            # Allocate proportional to gap
            allocation = dca_budget * (gap / total_gap)
            allocation = min(allocation, remaining_budget)

            # Get current price (try position_map first, then fetch)
            price = position_map.get(etf, {}).get("price", 0)
            if price <= 0:
                price = self._get_current_price(etf)
            if price <= 0:
                logger.warning(f"[LONG] Skipping {etf} DCA -- could not get price")
                continue

            qty = round(allocation / price, 4)
            if qty <= 0:
                continue

            proposals.append(TradeProposal(
                sleeve=self.SLEEVE_NAME,
                ticker=etf,
                action="BUY",
                quantity=qty,
                order_type="market",
                confidence=0.85,
                reasoning=(
                    f"DCA: {etf} underweight by {gap:.1%}. "
                    f"Investing ${allocation:.2f}"
                ),
            ))
            remaining_budget -= allocation

        logger.info(
            f"[LONG] Generated {len(proposals)} DCA orders "
            f"(${dca_budget - remaining_budget:.2f} deployed)"
        )
        return proposals