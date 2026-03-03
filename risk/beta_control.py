"""
Portfolio Beta Control Module
Monitors and manages portfolio-level beta exposure relative to SPY.

Beta measures systematic (market) risk:
  beta = 1.0 -> moves 1:1 with market
  beta > 1.0 -> amplifies market moves (higher risk/reward)
  beta < 1.0 -> dampens market moves (defensive)
  beta < 0.0 -> inversely correlated

Target: Keep portfolio beta between 0.5 and 1.2 depending on regime.
"""
import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class BetaState:
    """Current portfolio beta analysis."""
    portfolio_beta: float           # Weighted-average portfolio beta
    target_beta_low: float          # Lower bound of target range
    target_beta_high: float         # Upper bound of target range
    in_range: bool                  # Whether beta is within target
    beta_by_position: dict          # Per-ticker beta values
    beta_by_sleeve: dict            # Per-sleeve weighted beta
    action_required: str            # NONE, REDUCE_BETA, INCREASE_BETA
    suggested_adjustment: str       # Human-readable suggestion

    def to_dict(self) -> dict:
        return {
            "portfolio_beta": round(self.portfolio_beta, 3),
            "target_range": [self.target_beta_low, self.target_beta_high],
            "in_range": self.in_range,
            "beta_by_sleeve": {
                k: round(v, 3) for k, v in self.beta_by_sleeve.items()
            },
            "action_required": self.action_required,
            "suggested_adjustment": self.suggested_adjustment,
        }


# Beta targets by regime
BETA_TARGETS = {
    "LOW_VOL":  {"low": 0.8, "high": 1.3},
    "NORMAL":   {"low": 0.6, "high": 1.2},
    "HIGH_VOL": {"low": 0.4, "high": 0.9},
    "CRISIS":   {"low": 0.2, "high": 0.6},
}


class BetaController:
    """
    Monitors portfolio beta and suggests adjustments.

    Calculates rolling beta of each position against SPY,
    then computes weighted-average portfolio beta.
    """

    def __init__(self, lookback_days: int = 60):
        self.lookback = lookback_days
        self._beta_cache: dict[str, float] = {}
        self._spy_returns: Optional[pd.Series] = None
        self._last_refresh: float = 0

    def analyze(
        self,
        positions: list[dict],
        total_portfolio_value: float,
        regime: str = "NORMAL",
    ) -> BetaState:
        """
        Calculate portfolio beta and check against regime-appropriate targets.
        """
        self._refresh_spy_data()

        if self._spy_returns is None or self._spy_returns.empty:
            return self._default_state(regime)

        target = BETA_TARGETS.get(regime, BETA_TARGETS["NORMAL"])

        # Calculate beta for each position
        beta_by_position = {}
        beta_by_sleeve = {"short_term": 0.0, "mid_term": 0.0, "long_term": 0.0}
        sleeve_values = {"short_term": 0.0, "mid_term": 0.0, "long_term": 0.0}
        portfolio_beta = 0.0
        total_invested = 0.0

        for pos in positions:
            ticker = pos.get("ticker", "").split("_")[0]
            qty = abs(pos.get("quantity", 0))
            price = pos.get("currentPrice", 0)
            value = qty * price
            sleeve = pos.get("sleeve", "unknown")

            if value <= 0:
                continue

            beta = self._get_beta(ticker)
            beta_by_position[ticker] = beta

            weight = value / total_portfolio_value if total_portfolio_value > 0 else 0
            portfolio_beta += beta * weight
            total_invested += value

            if sleeve in beta_by_sleeve:
                beta_by_sleeve[sleeve] += beta * value
                sleeve_values[sleeve] += value

        # Normalize sleeve betas
        for sleeve in beta_by_sleeve:
            if sleeve_values[sleeve] > 0:
                beta_by_sleeve[sleeve] /= sleeve_values[sleeve]

        # Cash portion has beta = 0, which pulls portfolio beta down
        cash_weight = max(0, 1.0 - (total_invested / total_portfolio_value)) \
            if total_portfolio_value > 0 else 1.0
        portfolio_beta *= (1.0 - cash_weight)

        in_range = target["low"] <= portfolio_beta <= target["high"]

        # Determine action
        action = "NONE"
        suggestion = "Portfolio beta within target range."
        if portfolio_beta > target["high"]:
            action = "REDUCE_BETA"
            excess = portfolio_beta - target["high"]
            suggestion = (
                f"Beta {portfolio_beta:.2f} exceeds {regime} target "
                f"({target['high']:.1f}). Consider reducing high-beta "
                f"positions or adding defensive ETFs (BND, GLD)."
            )
        elif portfolio_beta < target["low"]:
            action = "INCREASE_BETA"
            deficit = target["low"] - portfolio_beta
            suggestion = (
                f"Beta {portfolio_beta:.2f} below {regime} target "
                f"({target['low']:.1f}). Portfolio may be too defensive. "
                f"Consider adding equity exposure."
            )

        state = BetaState(
            portfolio_beta=portfolio_beta,
            target_beta_low=target["low"],
            target_beta_high=target["high"],
            in_range=in_range,
            beta_by_position=beta_by_position,
            beta_by_sleeve=beta_by_sleeve,
            action_required=action,
            suggested_adjustment=suggestion,
        )

        logger.info(
            f"[BETA] Portfolio beta: {portfolio_beta:.3f} | "
            f"Target: {target['low']:.1f}-{target['high']:.1f} | "
            f"Regime: {regime} | Action: {action}"
        )

        return state

    def _refresh_spy_data(self):
        """Fetch SPY returns for beta calculation."""
        import time
        now = time.time()
        if self._spy_returns is not None and (now - self._last_refresh < 3600):
            return

        try:
            spy = yf.Ticker("SPY")
            hist = spy.history(period="6mo")
            if not hist.empty:
                self._spy_returns = np.log(
                    hist["Close"] / hist["Close"].shift(1)
                ).dropna()
                self._last_refresh = now
                self._beta_cache.clear()
        except Exception as e:
            logger.warning(f"[BETA] SPY data error: {e}")

    def _get_beta(self, ticker: str) -> float:
        """
        Calculate rolling beta of a ticker against SPY.
        Uses OLS regression of log returns.
        Caches results per ticker.
        """
        if ticker in self._beta_cache:
            return self._beta_cache[ticker]

        # Known betas for common ETFs
        known_betas = {
            "SPY": 1.0, "VOO": 1.0, "VTI": 1.0, "IWM": 1.2,
            "QQQ": 1.15, "ARKK": 1.5,
            "BND": 0.0, "VXUS": 0.85, "VNQ": 0.7,
            "GLD": 0.05,
        }
        if ticker in known_betas:
            self._beta_cache[ticker] = known_betas[ticker]
            return known_betas[ticker]

        if self._spy_returns is None:
            return 1.0  # Default assumption

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            if hist.empty or len(hist) < 30:
                return 1.0

            stock_returns = np.log(
                hist["Close"] / hist["Close"].shift(1)
            ).dropna()

            # Align dates
            aligned = pd.DataFrame({
                "stock": stock_returns,
                "spy": self._spy_returns,
            }).dropna()

            if len(aligned) < 20:
                return 1.0

            # OLS beta: cov(stock, spy) / var(spy)
            cov = aligned["stock"].cov(aligned["spy"])
            var_spy = aligned["spy"].var()

            beta = cov / var_spy if var_spy > 0 else 1.0
            beta = max(-2.0, min(beta, 3.0))  # Clamp extreme values

            self._beta_cache[ticker] = beta
            return beta

        except Exception:
            return 1.0

    def _default_state(self, regime: str) -> BetaState:
        target = BETA_TARGETS.get(regime, BETA_TARGETS["NORMAL"])
        return BetaState(
            portfolio_beta=1.0,
            target_beta_low=target["low"],
            target_beta_high=target["high"],
            in_range=True,
            beta_by_position={},
            beta_by_sleeve={},
            action_required="NONE",
            suggested_adjustment="Insufficient data for beta calculation.",
        )
