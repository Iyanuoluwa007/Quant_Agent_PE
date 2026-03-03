"""
Meta-Model Module
Dynamically adjusts Claude's influence on trading decisions based on
recent prediction accuracy and calibration quality.

When Claude is well-calibrated (Brier < 0.25, accuracy > 55%):
  -> Full trust: use Claude's confidence directly for position sizing
  
When Claude is poorly calibrated (Brier > 0.35, accuracy < 45%):
  -> Reduced trust: scale down Claude-driven positions, increase
     reliance on quantitative signals

The meta-model acts as a Bayesian prior updater:
  effective_confidence = claude_weight * claude_confidence
                       + (1 - claude_weight) * quant_signal_confidence
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from intelligence.calibration import CalibrationTracker, CalibrationReport

logger = logging.getLogger(__name__)


@dataclass
class MetaModelState:
    """Current meta-model weighting state."""
    claude_weight: float              # 0-1, how much to trust Claude
    quant_weight: float               # 0-1, how much to trust quant signals
    reason: str                       # Why this weight
    calibration_brier: float          # Recent Brier score
    calibration_accuracy: float       # Recent accuracy
    reliability_score: float          # From calibration tracker
    sample_size: int                  # Predictions evaluated
    per_sleeve_weights: dict          # Different trust per sleeve
    regime_adjustment: float          # Additional regime modifier

    def to_dict(self) -> dict:
        return {
            "claude_weight": round(self.claude_weight, 3),
            "quant_weight": round(self.quant_weight, 3),
            "reason": self.reason,
            "brier_score": round(self.calibration_brier, 4),
            "accuracy": round(self.calibration_accuracy, 3),
            "reliability": round(self.reliability_score, 3),
            "sample_size": self.sample_size,
            "sleeve_weights": {
                k: round(v, 3) for k, v in self.per_sleeve_weights.items()
            },
        }


# Thresholds for trust levels
TRUST_THRESHOLDS = {
    "high_trust": {
        "min_accuracy": 0.55,
        "max_brier": 0.25,
        "min_samples": 20,
        "claude_weight": 0.85,
    },
    "moderate_trust": {
        "min_accuracy": 0.48,
        "max_brier": 0.30,
        "min_samples": 10,
        "claude_weight": 0.65,
    },
    "low_trust": {
        "min_accuracy": 0.40,
        "max_brier": 0.35,
        "min_samples": 5,
        "claude_weight": 0.40,
    },
    "minimal_trust": {
        "claude_weight": 0.20,
    },
}


class MetaModel:
    """
    Bayesian meta-model that dynamically adjusts Claude's weight.

    Uses a rolling window of predictions to:
    1. Assess Claude's recent performance
    2. Compute trust level per sleeve
    3. Generate effective confidence for position sizing
    4. Apply regime-based modifications

    The key insight: Claude may perform well in certain market regimes
    (e.g., trending markets) but poorly in others (e.g., choppy/ranging).
    The meta-model captures this conditional performance.
    """

    def __init__(self, calibration: CalibrationTracker):
        self.calibration = calibration
        self._state: Optional[MetaModelState] = None
        self._last_update: float = 0

    def get_state(self, regime: str = "NORMAL") -> MetaModelState:
        """Get current meta-model state with trust weights."""
        import time
        now = time.time()
        if self._state and (now - self._last_update < 600):  # 10 min cache
            return self._state

        report = self.calibration.get_calibration_report(days=30)
        state = self._compute_weights(report, regime)

        self._state = state
        self._last_update = now

        logger.info(
            f"[META] Claude weight: {state.claude_weight:.2f} | "
            f"Accuracy: {state.calibration_accuracy:.1%} | "
            f"Brier: {state.calibration_brier:.3f} | "
            f"Reason: {state.reason}"
        )

        return state

    def get_effective_confidence(
        self,
        claude_confidence: float,
        quant_signal_strength: float = 0.5,
        sleeve: str = "mid_term",
        regime: str = "NORMAL",
    ) -> float:
        """
        Compute effective confidence blending Claude and quant signals.

        Args:
            claude_confidence: Claude's stated confidence (0-1)
            quant_signal_strength: Quantitative signal strength (0-1)
            sleeve: Strategy sleeve name
            regime: Current market regime

        Returns:
            Blended confidence value (0-1)
        """
        state = self.get_state(regime)

        # Get sleeve-specific weight
        claude_w = state.per_sleeve_weights.get(sleeve, state.claude_weight)

        # Adjust Claude's confidence using calibration data
        adjusted_claude = self.calibration.get_confidence_adjustment(claude_confidence)

        # Blend
        effective = (claude_w * adjusted_claude
                     + (1 - claude_w) * quant_signal_strength)

        # Apply regime modifier
        effective *= state.regime_adjustment

        # Clamp to valid range
        effective = max(0.0, min(1.0, effective))

        return round(effective, 3)

    def get_position_size_multiplier(
        self,
        sleeve: str = "mid_term",
        regime: str = "NORMAL",
    ) -> float:
        """
        Get multiplier for Claude-driven position sizes.
        When trust is low, this reduces position sizes.
        """
        state = self.get_state(regime)
        sleeve_weight = state.per_sleeve_weights.get(sleeve, state.claude_weight)

        # Map weight to position size: full weight -> 1.0x, zero weight -> 0.3x
        multiplier = 0.3 + (0.7 * sleeve_weight)
        return round(multiplier, 3)

    def _compute_weights(
        self,
        report: CalibrationReport,
        regime: str,
    ) -> MetaModelState:
        """Compute trust weights from calibration data."""
        accuracy = report.overall_accuracy
        brier = report.brier_score
        samples = report.resolved_predictions
        reliability = report.reliability_score

        # Determine trust level
        if samples >= 20 and accuracy >= 0.55 and brier <= 0.25:
            trust_level = "high_trust"
            reason = "Strong calibration: accuracy and Brier score within targets"
        elif samples >= 10 and accuracy >= 0.48 and brier <= 0.30:
            trust_level = "moderate_trust"
            reason = "Moderate calibration: acceptable accuracy and Brier"
        elif samples >= 5 and accuracy >= 0.40:
            trust_level = "low_trust"
            reason = "Weak calibration: accuracy below target"
        elif samples < 5:
            trust_level = "moderate_trust"
            reason = "Insufficient data: using moderate trust as default"
        else:
            trust_level = "minimal_trust"
            reason = f"Poor calibration: accuracy={accuracy:.1%}, brier={brier:.3f}"

        base_weight = TRUST_THRESHOLDS[trust_level]["claude_weight"]

        # Per-sleeve weights based on per-sleeve accuracy
        sleeve_weights = {}
        for sleeve in ["short_term", "mid_term", "long_term"]:
            sleeve_data = report.by_sleeve.get(sleeve, {})
            sleeve_acc = sleeve_data.get("accuracy", accuracy)
            sleeve_count = sleeve_data.get("count", 0)

            if sleeve_count >= 10:
                # Enough data to differentiate
                if sleeve_acc >= 0.55:
                    sleeve_weights[sleeve] = min(base_weight + 0.1, 0.95)
                elif sleeve_acc < 0.40:
                    sleeve_weights[sleeve] = max(base_weight - 0.2, 0.15)
                else:
                    sleeve_weights[sleeve] = base_weight
            else:
                sleeve_weights[sleeve] = base_weight

        # Regime adjustment
        regime_adj = 1.0
        regime_data = report.by_regime.get(regime, {})
        if regime_data.get("count", 0) >= 5:
            regime_acc = regime_data.get("accuracy", accuracy)
            if regime_acc >= 0.60:
                regime_adj = 1.1   # Claude does well in this regime
            elif regime_acc < 0.40:
                regime_adj = 0.8   # Claude struggles in this regime

        return MetaModelState(
            claude_weight=base_weight,
            quant_weight=1.0 - base_weight,
            reason=reason,
            calibration_brier=brier,
            calibration_accuracy=accuracy,
            reliability_score=reliability,
            sample_size=samples,
            per_sleeve_weights=sleeve_weights,
            regime_adjustment=regime_adj,
        )

    def should_override_claude(self, sleeve: str = "mid_term") -> bool:
        """
        Check if quant signals should fully override Claude.
        Only in extreme underperformance cases.
        """
        state = self.get_state()
        sleeve_weight = state.per_sleeve_weights.get(sleeve, state.claude_weight)
        return sleeve_weight < 0.25
