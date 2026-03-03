"""
Global Risk Manager — Production Version
Dynamic sleeve allocation + tighter controls for small accounts.
"""
import logging
from datetime import date
from dataclasses import dataclass, field
from typing import Optional
from config import TradingConfig, SleeveConfig

logger = logging.getLogger(__name__)

SECTOR_MAP = {
    "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech",
    "AMZN": "Consumer", "META": "Tech", "TSLA": "Consumer", "AMD": "Tech",
    "NFLX": "Tech", "CRM": "Tech", "COIN": "Finance", "PLTR": "Tech",
    "MARA": "Crypto", "SOFI": "Finance", "JPM": "Finance", "V": "Finance",
    "MA": "Finance", "LLY": "Healthcare", "UNH": "Healthcare",
    "AVGO": "Tech", "COST": "Consumer", "XOM": "Energy", "CVX": "Energy",
    "GS": "Finance", "CAT": "Industrial", "JNJ": "Healthcare",
    "VOO": "Broad", "QQQ": "Tech", "VTI": "Broad", "VXUS": "International",
    "BND": "Bonds", "VNQ": "RealEstate", "GLD": "Commodities", "ARKK": "Tech",
    "SPY": "Broad", "IWM": "Broad",
}

CORRELATION_GROUPS = {
    "mega_tech": {"AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "QQQ"},
    "semiconductor": {"NVDA", "AMD", "AVGO"},
    "finance": {"JPM", "GS", "V", "MA", "SOFI", "COIN"},
    "energy": {"XOM", "CVX"},
    "healthcare": {"LLY", "UNH", "JNJ"},
    "broad_market": {"VOO", "VTI", "SPY"},
    "crypto_adjacent": {"COIN", "MARA"},
}


@dataclass
class TradeProposal:
    sleeve: str
    ticker: str
    action: str
    quantity: float
    order_type: str
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reasoning: str = ""
    confidence: float = 0.0


@dataclass
class RiskCheckResult:
    approved: bool
    original_proposal: TradeProposal
    adjusted_quantity: Optional[float] = None
    rejection_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GlobalRiskManager:
    def __init__(self, config: TradingConfig):
        self.config = config
        self._trades_today: list[dict] = []
        self._daily_pnl: float = 0.0
        self._sleeve_daily_pnl: dict[str, float] = {
            "short_term": 0.0, "mid_term": 0.0, "long_term": 0.0
        }
        self._current_date: date = date.today()

    def _reset_daily_counters(self):
        today = date.today()
        if today != self._current_date:
            self._current_date = today
            self._trades_today = []
            self._daily_pnl = 0.0
            self._sleeve_daily_pnl = {
                "short_term": 0.0, "mid_term": 0.0, "long_term": 0.0
            }

    def get_sleeve_config(self, sleeve_name: str, total_value: float) -> SleeveConfig:
        """Dynamic sleeve config based on current portfolio value."""
        return self.config.get_sleeve_config(sleeve_name, total_value)

    def get_sleeve_capital(self, sleeve_name: str, total_value: float) -> float:
        sleeve = self.get_sleeve_config(sleeve_name, total_value)
        return total_value * (sleeve.allocation_pct / 100)

    def get_sleeve_positions(self, sleeve_name: str, all_positions: list[dict]) -> list[dict]:
        return [p for p in all_positions if p.get("sleeve", "unknown") == sleeve_name]

    def check_trade(
        self,
        proposal: TradeProposal,
        account_cash: float,
        total_portfolio_value: float,
        all_positions: list[dict],
        pending_tickers: set = None,
    ) -> RiskCheckResult:
        self._reset_daily_counters()

        reasons = []
        warnings = []
        adjusted_qty = proposal.quantity
        sleeve = self.get_sleeve_config(proposal.sleeve, total_portfolio_value)
        sleeve_capital = self.get_sleeve_capital(proposal.sleeve, total_portfolio_value)
        plain_ticker = self.config.get_plain_symbol(proposal.ticker)
        pending_tickers = pending_tickers or set()

        # ── Skip disabled sleeves ───────────────────────────────────
        if sleeve.allocation_pct <= 0:
            reasons.append(
                f"{proposal.sleeve} sleeve is disabled at current portfolio "
                f"size (${total_portfolio_value:,.0f})"
            )
            return RiskCheckResult(
                approved=False, original_proposal=proposal,
                rejection_reasons=reasons,
            )

        # ── CHECK 0: Duplicate order ────────────────────────────────
        if plain_ticker in pending_tickers or proposal.ticker in pending_tickers:
            reasons.append(f"Pending order already exists for {proposal.ticker}")

        # ── CHECK 1: Global daily trade limit ───────────────────────
        if len(self._trades_today) >= self.config.MAX_TRADES_PER_DAY:
            reasons.append(f"Global daily trade limit ({self.config.MAX_TRADES_PER_DAY})")

        # ── CHECK 2: Global daily loss ──────────────────────────────
        max_loss = total_portfolio_value * (self.config.MAX_DAILY_LOSS_PCT / 100)
        if self._daily_pnl < -max_loss:
            reasons.append(f"Global daily loss breached: ${self._daily_pnl:.2f}")

        # ── CHECK 3: Sleeve daily loss ──────────────────────────────
        sleeve_loss_limit = sleeve_capital * (sleeve.max_daily_loss_pct / 100)
        sleeve_pnl = self._sleeve_daily_pnl.get(proposal.sleeve, 0)
        if sleeve_pnl < -sleeve_loss_limit:
            reasons.append(f"{proposal.sleeve} sleeve daily loss breached")

        if proposal.action == "BUY":
            # ── CHECK 4: Sleeve position count ──────────────────────
            sleeve_positions = self.get_sleeve_positions(proposal.sleeve, all_positions)
            if len(sleeve_positions) >= sleeve.max_positions:
                reasons.append(f"{proposal.sleeve} max positions ({sleeve.max_positions})")

            # ── CHECK 5: Sleeve position size ───────────────────────
            est_price = proposal.limit_price or proposal.stop_price or 0
            if est_price > 0:
                est_cost = abs(adjusted_qty) * est_price
                max_pos = sleeve_capital * (sleeve.max_position_pct / 100)
                if est_cost > max_pos:
                    adjusted_qty = round(max_pos / est_price, 4)
                    warnings.append(f"Qty reduced to {adjusted_qty} (sleeve max: ${max_pos:.0f})")

            # ── CHECK 6: Minimum trade value (small account guard) ──
            min_trade = max(5.0, total_portfolio_value * 0.005)  # min $5 or 0.5%
            if est_price > 0 and adjusted_qty * est_price < min_trade:
                reasons.append(
                    f"Trade too small: ${adjusted_qty * est_price:.2f} < "
                    f"min ${min_trade:.2f}"
                )

            # ── CHECK 7: Global exposure ────────────────────────────
            total_invested = sum(
                abs(p.get("currentPrice", 0) * p.get("quantity", 0))
                for p in all_positions
            )
            exposure_pct = (total_invested / total_portfolio_value) * 100 if total_portfolio_value > 0 else 0
            if exposure_pct >= self.config.MAX_TOTAL_EXPOSURE_PCT:
                reasons.append(
                    f"Global exposure: {exposure_pct:.1f}% >= {self.config.MAX_TOTAL_EXPOSURE_PCT}%"
                )

            # ── CHECK 8: Cash reserve ───────────────────────────────
            min_cash = total_portfolio_value * (self.config.MIN_CASH_RESERVE_PCT / 100)
            if account_cash - (adjusted_qty * (est_price or 0)) < min_cash:
                available = account_cash - min_cash
                if available > 0 and est_price > 0:
                    adjusted_qty = round(available / est_price, 4)
                    warnings.append(f"Qty reduced to {adjusted_qty} (cash reserve)")
                else:
                    reasons.append("Insufficient cash after reserve")

            # ── CHECK 9: Sector concentration ───────────────────────
            sector = SECTOR_MAP.get(plain_ticker, "Unknown")
            if sector not in ("Broad", "Bonds", "Unknown"):
                sector_value = sum(
                    abs(p.get("currentPrice", 0) * p.get("quantity", 0))
                    for p in all_positions
                    if SECTOR_MAP.get(self.config.get_plain_symbol(p.get("ticker", "")), "") == sector
                )
                sector_pct = (sector_value / total_portfolio_value) * 100 if total_portfolio_value > 0 else 0
                if sector_pct >= self.config.MAX_SECTOR_CONCENTRATION_PCT:
                    reasons.append(f"{sector} concentration: {sector_pct:.1f}%")

            # ── CHECK 10: Correlation ───────────────────────────────
            position_tickers = {
                self.config.get_plain_symbol(p.get("ticker", ""))
                for p in all_positions
            }
            for group_name, group_tickers in CORRELATION_GROUPS.items():
                if plain_ticker in group_tickers:
                    overlap = position_tickers & group_tickers
                    if len(overlap) >= self.config.MAX_CORRELATION_OVERLAP:
                        warnings.append(f"High correlation '{group_name}': {len(overlap)} positions")

        # ── CHECK 11: Sell validation ───────────────────────────────
        if proposal.action == "SELL":
            position = next(
                (p for p in all_positions
                 if self.config.get_plain_symbol(p.get("ticker", "")) == plain_ticker),
                None,
            )
            if not position:
                reasons.append(f"No position to sell: {proposal.ticker}")
            elif abs(adjusted_qty) > abs(position.get("quantity", 0)):
                adjusted_qty = abs(position["quantity"])
                warnings.append(f"Sell qty capped at {adjusted_qty}")

        # ── CHECK 12: Confidence threshold ──────────────────────────
        min_conf = 0.30 if proposal.sleeve == "short_term" else 0.20
        if proposal.confidence < min_conf:
            reasons.append(f"Confidence {proposal.confidence:.0%} < {min_conf:.0%}")

        # ── RESULT ──────────────────────────────────────────────────
        approved = len(reasons) == 0
        result = RiskCheckResult(
            approved=approved,
            original_proposal=proposal,
            adjusted_quantity=adjusted_qty if adjusted_qty != proposal.quantity else None,
            rejection_reasons=reasons,
            warnings=warnings,
        )

        if approved:
            logger.info(
                f"[OK] [{proposal.sleeve.upper()}] {proposal.action} "
                f"{proposal.ticker} qty={adjusted_qty or proposal.quantity}"
            )
            for w in warnings:
                logger.warning(f"  [!] {w}")
        else:
            logger.warning(
                f"[X] [{proposal.sleeve.upper()}] REJECTED: "
                f"{proposal.action} {proposal.ticker}"
            )
            for r in reasons:
                logger.warning(f"  Reason: {r}")

        return result

    def record_trade(self, trade_info: dict):
        self._trades_today.append(trade_info)
        pnl = trade_info.get("realized_pnl", 0)
        self._daily_pnl += pnl
        sleeve = trade_info.get("sleeve", "unknown")
        if sleeve in self._sleeve_daily_pnl:
            self._sleeve_daily_pnl[sleeve] += pnl

    def get_daily_stats(self) -> dict:
        self._reset_daily_counters()
        return {
            "trades_today": len(self._trades_today),
            "max_trades": self.config.MAX_TRADES_PER_DAY,
            "global_daily_pnl": self._daily_pnl,
            "sleeve_pnl": dict(self._sleeve_daily_pnl),
        }