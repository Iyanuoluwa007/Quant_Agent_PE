"""
Volatility Targeting Module
Scales portfolio exposure to maintain a constant risk budget.

Concept:
  If target vol = 12% and realized vol = 24%, scale exposure to 50%.
  If target vol = 12% and realized vol = 8%, scale exposure to 150% (capped at 100%).

This prevents the portfolio from being over-exposed in volatile markets
and under-exposed in calm markets. Applied as a multiplier on top of
position sizing from the strategy sleeves.

Reference: "Risk Parity Fundamentals" (Qian, 2016)
"""
import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Annualized trading days
TRADING_DAYS = 252

# Bounds on the exposure scalar
MIN_EXPOSURE_SCALAR = 0.20    # Never go below 20% exposure
MAX_EXPOSURE_SCALAR = 1.00    # Never leverage above 100%


@dataclass
class VolTargetState:
    """Current volatility targeting state."""
    target_vol_pct: float          # Target annualized vol (e.g., 12.0)
    realized_vol_pct: float        # Current realized annualized vol
    exposure_scalar: float         # Multiplier for position sizes
    lookback_days: int             # Window used for vol estimation
    ewma_halflife: int             # EWMA half-life in days
    raw_scalar: float              # Before clamping to bounds
    capped: bool                   # Whether scalar was clamped

    def to_dict(self) -> dict:
        return {
            "target_vol": round(self.target_vol_pct, 2),
            "realized_vol": round(self.realized_vol_pct, 2),
            "exposure_scalar": round(self.exposure_scalar, 4),
            "raw_scalar": round(self.raw_scalar, 4),
            "capped": self.capped,
            "lookback_days": self.lookback_days,
        }


class VolatilityTargeter:
    """
    Implements constant-volatility targeting.

    The core idea: scale position sizes so that expected portfolio
    volatility stays near a target level regardless of market conditions.

    scalar = target_vol / realized_vol

    Uses EWMA (exponentially weighted moving average) for responsive
    volatility estimation that reacts quickly to regime changes.
    """

    def __init__(
        self,
        target_vol_pct: float = 12.0,
        lookback_days: int = 60,
        ewma_halflife: int = 20,
        min_scalar: float = MIN_EXPOSURE_SCALAR,
        max_scalar: float = MAX_EXPOSURE_SCALAR,
    ):
        self.target_vol = target_vol_pct
        self.lookback = lookback_days
        self.halflife = ewma_halflife
        self.min_scalar = min_scalar
        self.max_scalar = max_scalar
        self._cache: Optional[VolTargetState] = None
        self._cache_time: float = 0
        self._history: list[dict] = []

    def compute(self, force: bool = False) -> VolTargetState:
        """
        Compute the current volatility-targeting scalar.
        Caches for 30 minutes.
        """
        import time
        now = time.time()
        if not force and self._cache and (now - self._cache_time < 1800):
            return self._cache

        realized_vol = self._estimate_portfolio_vol()

        if realized_vol <= 0:
            logger.warning("[VOL_TARGET] Realized vol is 0, using target as fallback")
            realized_vol = self.target_vol

        raw_scalar = self.target_vol / realized_vol
        clamped = max(self.min_scalar, min(raw_scalar, self.max_scalar))
        capped = (clamped != raw_scalar)

        state = VolTargetState(
            target_vol_pct=self.target_vol,
            realized_vol_pct=realized_vol,
            exposure_scalar=clamped,
            lookback_days=self.lookback,
            ewma_halflife=self.halflife,
            raw_scalar=raw_scalar,
            capped=capped,
        )

        self._cache = state
        self._cache_time = now
        self._history.append(state.to_dict())

        logger.info(
            f"[VOL_TARGET] Target: {self.target_vol:.1f}% | "
            f"Realized: {realized_vol:.1f}% | "
            f"Scalar: {clamped:.2f}"
            + (" (CAPPED)" if capped else "")
        )

        return state

    def _estimate_portfolio_vol(self) -> float:
        """
        Estimate portfolio-level volatility using SPY as a proxy.
        In production, this would use actual portfolio returns.
        For now, SPY realized vol serves as a market-level estimate.
        """
        try:
            spy = yf.Ticker("SPY")
            hist = spy.history(period="6mo")
            if hist.empty or len(hist) < self.lookback:
                return self.target_vol

            close = hist["Close"]
            log_returns = np.log(close / close.shift(1)).dropna()

            # EWMA variance (more responsive than simple rolling)
            ewma_var = log_returns.ewm(halflife=self.halflife).var().iloc[-1]
            annualized_vol = math.sqrt(ewma_var * TRADING_DAYS) * 100

            return annualized_vol

        except Exception as e:
            logger.warning(f"[VOL_TARGET] SPY data error: {e}")
            return self.target_vol

    def compute_from_returns(self, daily_returns: pd.Series) -> VolTargetState:
        """
        Compute vol target from actual portfolio daily returns.
        Use this when portfolio return history is available.
        """
        if daily_returns.empty or len(daily_returns) < 10:
            return self.compute()

        ewma_var = daily_returns.ewm(halflife=self.halflife).var().iloc[-1]
        realized_vol = math.sqrt(ewma_var * TRADING_DAYS) * 100

        if realized_vol <= 0:
            realized_vol = self.target_vol

        raw_scalar = self.target_vol / realized_vol
        clamped = max(self.min_scalar, min(raw_scalar, self.max_scalar))

        state = VolTargetState(
            target_vol_pct=self.target_vol,
            realized_vol_pct=realized_vol,
            exposure_scalar=clamped,
            lookback_days=self.lookback,
            ewma_halflife=self.halflife,
            raw_scalar=raw_scalar,
            capped=(clamped != raw_scalar),
        )

        self._cache = state
        return state

    def adjust_position_size(self, base_quantity: float) -> float:
        """
        Adjust a position size by the vol-targeting scalar.
        Call this after normal position sizing to apply the vol overlay.
        """
        state = self.compute()
        adjusted = base_quantity * state.exposure_scalar
        return round(adjusted, 4)

    def get_history(self) -> list[dict]:
        return list(self._history)
