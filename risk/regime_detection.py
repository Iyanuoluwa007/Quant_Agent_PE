"""
Regime Detection Module
Identifies market volatility regimes using:
- Realized volatility clustering (EWMA)
- VIX level classification
- Volatility-of-volatility (vol-of-vol) for transition detection

Regimes:
  LOW_VOL    — VIX < 15, realized vol < 10% annualized
  NORMAL     — VIX 15-20, realized vol 10-18%
  HIGH_VOL   — VIX 20-30, realized vol 18-28%
  CRISIS     — VIX > 30, realized vol > 28%

Each regime maps to risk multipliers for position sizing and sleeve activation.
"""
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class RegimeState:
    """Current market regime classification."""
    regime: str                    # LOW_VOL, NORMAL, HIGH_VOL, CRISIS
    vix_level: float               # Current VIX value
    realized_vol_20d: float        # 20-day realized vol (annualized %)
    realized_vol_60d: float        # 60-day realized vol (annualized %)
    vol_of_vol: float              # Volatility of volatility
    vol_ratio: float               # 20d vol / 60d vol (>1 = vol expanding)
    risk_multiplier: float         # Scaling factor for position sizing
    sleeve_adjustments: dict       # Per-sleeve allocation adjustments
    confidence: float              # Confidence in regime classification
    timestamp: str = ""
    transition_signal: str = ""    # STABLE, EXPANDING, CONTRACTING

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "vix_level": round(self.vix_level, 2),
            "realized_vol_20d": round(self.realized_vol_20d, 2),
            "realized_vol_60d": round(self.realized_vol_60d, 2),
            "vol_of_vol": round(self.vol_of_vol, 2),
            "vol_ratio": round(self.vol_ratio, 2),
            "risk_multiplier": round(self.risk_multiplier, 2),
            "sleeve_adjustments": self.sleeve_adjustments,
            "confidence": round(self.confidence, 2),
            "transition_signal": self.transition_signal,
            "timestamp": self.timestamp,
        }


# Regime thresholds
REGIME_THRESHOLDS = {
    "LOW_VOL":  {"vix_max": 15, "rvol_max": 10},
    "NORMAL":   {"vix_max": 20, "rvol_max": 18},
    "HIGH_VOL": {"vix_max": 30, "rvol_max": 28},
    "CRISIS":   {"vix_max": 999, "rvol_max": 999},
}

# Risk multipliers per regime
RISK_MULTIPLIERS = {
    "LOW_VOL":  1.2,   # Slightly increase sizing in calm markets
    "NORMAL":   1.0,   # Baseline
    "HIGH_VOL": 0.6,   # Reduce exposure significantly
    "CRISIS":   0.3,   # Minimal exposure
}

# Sleeve allocation adjustments per regime
# Values are multipliers applied to base allocation
SLEEVE_ADJUSTMENTS = {
    "LOW_VOL": {
        "short_term": 1.0,
        "mid_term": 1.0,
        "long_term": 1.0,
    },
    "NORMAL": {
        "short_term": 1.0,
        "mid_term": 1.0,
        "long_term": 1.0,
    },
    "HIGH_VOL": {
        "short_term": 0.5,    # Halve short-term in high vol
        "mid_term": 0.75,
        "long_term": 1.25,    # Shift capital to long-term
    },
    "CRISIS": {
        "short_term": 0.0,    # Disable short-term in crisis
        "mid_term": 0.5,
        "long_term": 1.5,     # Maximize defensive allocation
    },
}


class RegimeDetector:
    """
    Detects market volatility regimes using multiple signals.

    Uses a composite scoring approach:
    1. VIX absolute level (forward-looking implied vol)
    2. Realized volatility (backward-looking actual vol)
    3. Vol-of-vol (regime transition indicator)
    4. Vol ratio (20d/60d — expansion/contraction signal)
    """

    def __init__(self):
        self._cache: Optional[RegimeState] = None
        self._cache_time: float = 0
        self._cache_ttl: int = 900  # 15-minute cache
        self._history: list[dict] = []

    def detect(self, force: bool = False) -> RegimeState:
        """
        Classify current market regime.
        Caches result for 15 minutes to avoid excessive API calls.
        """
        import time
        now = time.time()
        if not force and self._cache and (now - self._cache_time < self._cache_ttl):
            return self._cache

        vix_level = self._fetch_vix()
        spy_data = self._fetch_spy_history()

        if spy_data is None or spy_data.empty:
            logger.warning("[REGIME] Failed to fetch SPY data, defaulting to NORMAL")
            return self._default_state()

        rvol_20d = self._realized_volatility(spy_data, window=20)
        rvol_60d = self._realized_volatility(spy_data, window=60)
        vol_of_vol = self._vol_of_vol(spy_data, window=20)
        vol_ratio = rvol_20d / rvol_60d if rvol_60d > 0 else 1.0

        regime = self._classify(vix_level, rvol_20d)
        transition = self._detect_transition(vol_ratio, vol_of_vol)
        confidence = self._regime_confidence(vix_level, rvol_20d, regime)

        state = RegimeState(
            regime=regime,
            vix_level=vix_level,
            realized_vol_20d=rvol_20d,
            realized_vol_60d=rvol_60d,
            vol_of_vol=vol_of_vol,
            vol_ratio=vol_ratio,
            risk_multiplier=RISK_MULTIPLIERS[regime],
            sleeve_adjustments=SLEEVE_ADJUSTMENTS[regime],
            confidence=confidence,
            transition_signal=transition,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._cache = state
        self._cache_time = now

        # Record for history tracking
        self._history.append(state.to_dict())
        if len(self._history) > 500:
            self._history = self._history[-500:]

        logger.info(
            f"[REGIME] {regime} | VIX: {vix_level:.1f} | "
            f"RVol20d: {rvol_20d:.1f}% | VolRatio: {vol_ratio:.2f} | "
            f"Transition: {transition} | Confidence: {confidence:.0%}"
        )

        return state

    def _fetch_vix(self) -> float:
        """Fetch current VIX level."""
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="5d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as e:
            logger.warning(f"[REGIME] VIX fetch failed: {e}")
        return 18.0  # Default to normal

    def _fetch_spy_history(self) -> Optional[pd.DataFrame]:
        """Fetch SPY daily close prices for vol calculation."""
        try:
            spy = yf.Ticker("SPY")
            hist = spy.history(period="6mo")
            if not hist.empty:
                return hist
        except Exception as e:
            logger.warning(f"[REGIME] SPY data fetch failed: {e}")
        return None

    def _realized_volatility(self, data: pd.DataFrame, window: int = 20) -> float:
        """
        Calculate realized volatility (annualized) using log returns.
        Returns percentage (e.g., 15.0 for 15% annualized vol).
        """
        if len(data) < window + 1:
            return 15.0  # Default

        close = data["Close"]
        log_returns = np.log(close / close.shift(1)).dropna()

        if len(log_returns) < window:
            return 15.0

        # Use EWMA for more responsive vol estimate
        ewma_var = log_returns.ewm(span=window).var().iloc[-1]
        annualized_vol = math.sqrt(ewma_var * 252) * 100

        return annualized_vol

    def _vol_of_vol(self, data: pd.DataFrame, window: int = 20) -> float:
        """
        Calculate volatility-of-volatility.
        High vol-of-vol suggests regime transitions are occurring.
        """
        if len(data) < window * 2:
            return 1.0

        close = data["Close"]
        log_returns = np.log(close / close.shift(1)).dropna()

        # Rolling realized vol
        rolling_vol = log_returns.rolling(window).std() * math.sqrt(252) * 100

        # Vol of the vol series
        vol_of_vol = rolling_vol.dropna().tail(window).std()

        return float(vol_of_vol) if not math.isnan(vol_of_vol) else 1.0

    def _classify(self, vix: float, rvol: float) -> str:
        """
        Classify regime using composite of VIX and realized vol.
        Uses a weighted vote: VIX gets 60% weight (forward-looking),
        realized vol gets 40% weight (backward-looking).
        """
        def vix_regime(v: float) -> str:
            if v < 15:
                return "LOW_VOL"
            elif v < 20:
                return "NORMAL"
            elif v < 30:
                return "HIGH_VOL"
            return "CRISIS"

        def rvol_regime(r: float) -> str:
            if r < 10:
                return "LOW_VOL"
            elif r < 18:
                return "NORMAL"
            elif r < 28:
                return "HIGH_VOL"
            return "CRISIS"

        regime_order = ["LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"]
        vix_r = vix_regime(vix)
        rvol_r = rvol_regime(rvol)

        vix_idx = regime_order.index(vix_r)
        rvol_idx = regime_order.index(rvol_r)

        # Weighted composite — bias toward the more severe regime
        composite_idx = round(vix_idx * 0.6 + rvol_idx * 0.4)
        composite_idx = max(0, min(composite_idx, len(regime_order) - 1))

        return regime_order[composite_idx]

    def _detect_transition(self, vol_ratio: float, vol_of_vol: float) -> str:
        """
        Detect if we are transitioning between regimes.
        vol_ratio > 1.3 = vol expanding (potential regime shift up)
        vol_ratio < 0.7 = vol contracting (potential regime shift down)
        """
        if vol_ratio > 1.3 or vol_of_vol > 4.0:
            return "EXPANDING"
        elif vol_ratio < 0.7:
            return "CONTRACTING"
        return "STABLE"

    def _regime_confidence(self, vix: float, rvol: float, regime: str) -> float:
        """
        How confident are we in the regime classification?
        Higher when VIX and realized vol agree.
        """
        regime_order = ["LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"]

        def vix_regime(v):
            if v < 15: return 0
            elif v < 20: return 1
            elif v < 30: return 2
            return 3

        def rvol_regime(r):
            if r < 10: return 0
            elif r < 18: return 1
            elif r < 28: return 2
            return 3

        vix_idx = vix_regime(vix)
        rvol_idx = rvol_regime(rvol)
        disagreement = abs(vix_idx - rvol_idx)

        if disagreement == 0:
            return 0.95
        elif disagreement == 1:
            return 0.75
        elif disagreement == 2:
            return 0.55
        return 0.40

    def _default_state(self) -> RegimeState:
        return RegimeState(
            regime="NORMAL",
            vix_level=18.0,
            realized_vol_20d=15.0,
            realized_vol_60d=15.0,
            vol_of_vol=1.0,
            vol_ratio=1.0,
            risk_multiplier=1.0,
            sleeve_adjustments=SLEEVE_ADJUSTMENTS["NORMAL"],
            confidence=0.5,
            transition_signal="STABLE",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def get_history(self) -> list[dict]:
        """Return regime detection history for analysis."""
        return list(self._history)

    def get_regime_summary(self) -> str:
        """Human-readable regime summary for logging."""
        state = self.detect()
        lines = [
            f"  Market Regime: {state.regime}",
            f"  VIX: {state.vix_level:.1f}",
            f"  Realized Vol (20d): {state.realized_vol_20d:.1f}%",
            f"  Realized Vol (60d): {state.realized_vol_60d:.1f}%",
            f"  Vol Ratio (20/60): {state.vol_ratio:.2f}",
            f"  Transition: {state.transition_signal}",
            f"  Risk Multiplier: {state.risk_multiplier:.2f}",
            f"  Confidence: {state.confidence:.0%}",
        ]
        return "\n".join(lines)
