"""
Claude Confidence Calibration Module
Tracks every prediction Claude makes and compares stated confidence
to actual outcomes to build calibration curves.

A well-calibrated model should have:
  - 70% confidence predictions correct ~70% of the time
  - 90% confidence predictions correct ~90% of the time

If Claude says 80% confident but is only right 50% of the time,
the meta-model will downweight Claude's influence.

Metrics:
  - Brier Score (lower is better, 0 = perfect)
  - Calibration curve (confidence bins vs actual accuracy)
  - Per-sleeve calibration
  - Regime-conditional calibration
"""
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CALIBRATION_FILE = Path("calibration_data.json")


@dataclass
class Prediction:
    """A single Claude prediction record."""
    prediction_id: str
    timestamp: str
    sleeve: str
    ticker: str
    action: str                     # BUY or SELL
    confidence: float               # Claude's stated confidence (0-1)
    predicted_direction: str        # UP or DOWN
    predicted_return_pct: float     # Expected return %
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    regime: str                     # Market regime at prediction time
    # Outcome fields (filled later)
    outcome_filled: bool = False
    actual_direction: str = ""      # UP, DOWN, or FLAT
    actual_return_pct: float = 0.0
    exit_price: float = 0.0
    exit_date: str = ""
    correct: bool = False
    hold_days: int = 0


@dataclass
class CalibrationBin:
    """A single bin in the calibration curve."""
    confidence_low: float
    confidence_high: float
    predicted_accuracy: float       # Midpoint of bin
    actual_accuracy: float          # Observed accuracy
    sample_count: int
    brier_contribution: float


@dataclass
class CalibrationReport:
    """Full calibration analysis."""
    total_predictions: int
    resolved_predictions: int
    overall_accuracy: float
    brier_score: float              # 0 = perfect, 1 = worst
    calibration_bins: list[CalibrationBin]
    by_sleeve: dict                 # sleeve -> {accuracy, brier, count}
    by_regime: dict                 # regime -> {accuracy, brier, count}
    overconfidence_score: float     # >0 = overconfident, <0 = underconfident
    reliability_score: float        # 0-1, how trustworthy Claude's confidence is

    def to_dict(self) -> dict:
        return {
            "total_predictions": self.total_predictions,
            "resolved": self.resolved_predictions,
            "overall_accuracy": round(self.overall_accuracy, 3),
            "brier_score": round(self.brier_score, 4),
            "overconfidence": round(self.overconfidence_score, 3),
            "reliability": round(self.reliability_score, 3),
            "by_sleeve": self.by_sleeve,
            "by_regime": self.by_regime,
            "calibration_curve": [
                {
                    "bin": f"{b.confidence_low:.0%}-{b.confidence_high:.0%}",
                    "predicted": round(b.predicted_accuracy, 3),
                    "actual": round(b.actual_accuracy, 3),
                    "count": b.sample_count,
                }
                for b in self.calibration_bins
            ],
        }


class CalibrationTracker:
    """
    Tracks Claude's prediction accuracy and builds calibration curves.

    Workflow:
    1. record_prediction() — called when Claude makes a trade recommendation
    2. resolve_prediction() — called when the trade closes
    3. get_calibration_report() — generates full calibration analysis
    """

    def __init__(self):
        self.predictions: list[Prediction] = []
        self._load()

    def _load(self):
        """Load prediction history from disk."""
        if CALIBRATION_FILE.exists():
            try:
                data = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
                self.predictions = [
                    Prediction(**p) for p in data.get("predictions", [])
                ]
            except Exception as e:
                logger.warning(f"[CALIBRATION] Load error: {e}")
                self.predictions = []

    def _save(self):
        """Persist prediction history."""
        data = {
            "predictions": [
                {
                    "prediction_id": p.prediction_id,
                    "timestamp": p.timestamp,
                    "sleeve": p.sleeve,
                    "ticker": p.ticker,
                    "action": p.action,
                    "confidence": p.confidence,
                    "predicted_direction": p.predicted_direction,
                    "predicted_return_pct": p.predicted_return_pct,
                    "entry_price": p.entry_price,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                    "regime": p.regime,
                    "outcome_filled": p.outcome_filled,
                    "actual_direction": p.actual_direction,
                    "actual_return_pct": p.actual_return_pct,
                    "exit_price": p.exit_price,
                    "exit_date": p.exit_date,
                    "correct": p.correct,
                    "hold_days": p.hold_days,
                }
                for p in self.predictions
            ],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        CALIBRATION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_prediction(
        self,
        sleeve: str,
        ticker: str,
        action: str,
        confidence: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        regime: str = "NORMAL",
    ) -> str:
        """
        Record a new prediction from Claude.
        Returns a prediction_id for later resolution.
        """
        pred_id = f"{sleeve}_{ticker}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        direction = "UP" if action == "BUY" else "DOWN"
        # Estimate expected return from stop/target
        expected_return = 0.0
        if take_profit and entry_price > 0:
            if action == "BUY":
                expected_return = ((take_profit - entry_price) / entry_price) * 100
            else:
                expected_return = ((entry_price - take_profit) / entry_price) * 100

        pred = Prediction(
            prediction_id=pred_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            sleeve=sleeve,
            ticker=ticker,
            action=action,
            confidence=confidence,
            predicted_direction=direction,
            predicted_return_pct=round(expected_return, 2),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            regime=regime,
        )

        self.predictions.append(pred)
        self._save()

        logger.info(
            f"[CALIBRATION] Recorded: {sleeve}/{ticker} {action} "
            f"conf={confidence:.0%} entry=${entry_price:.2f}"
        )
        return pred_id

    def resolve_prediction(
        self,
        prediction_id: str = None,
        ticker: str = None,
        sleeve: str = None,
        exit_price: float = 0.0,
    ):
        """
        Resolve a prediction with actual outcome.
        Can match by prediction_id or by ticker+sleeve (most recent unresolved).
        """
        pred = None
        if prediction_id:
            pred = next(
                (p for p in self.predictions if p.prediction_id == prediction_id),
                None,
            )
        elif ticker and sleeve:
            # Find most recent unresolved prediction for this ticker/sleeve
            for p in reversed(self.predictions):
                if (p.ticker == ticker and p.sleeve == sleeve
                        and not p.outcome_filled):
                    pred = p
                    break

        if not pred:
            logger.warning(
                f"[CALIBRATION] No matching prediction to resolve: "
                f"{prediction_id or f'{ticker}/{sleeve}'}"
            )
            return

        if exit_price <= 0:
            return

        # Calculate outcome
        if pred.action == "BUY":
            actual_return = ((exit_price - pred.entry_price) / pred.entry_price) * 100
            actual_direction = "UP" if actual_return > 0.5 else ("DOWN" if actual_return < -0.5 else "FLAT")
        else:
            actual_return = ((pred.entry_price - exit_price) / pred.entry_price) * 100
            actual_direction = "DOWN" if exit_price < pred.entry_price else "UP"

        correct = (pred.predicted_direction == actual_direction)

        pred.outcome_filled = True
        pred.actual_direction = actual_direction
        pred.actual_return_pct = round(actual_return, 2)
        pred.exit_price = exit_price
        pred.exit_date = datetime.now(timezone.utc).isoformat()
        pred.correct = correct

        # Calculate hold days
        try:
            entry_dt = datetime.fromisoformat(pred.timestamp.replace("Z", "+00:00"))
            pred.hold_days = (datetime.now(timezone.utc) - entry_dt).days
        except Exception:
            pred.hold_days = 0

        self._save()

        logger.info(
            f"[CALIBRATION] Resolved: {pred.ticker} "
            f"conf={pred.confidence:.0%} -> "
            f"{'CORRECT' if correct else 'WRONG'} "
            f"({actual_return:+.2f}%)"
        )

    def get_calibration_report(self, days: int = 90) -> CalibrationReport:
        """Generate full calibration analysis."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        resolved = [
            p for p in self.predictions
            if p.outcome_filled
            and datetime.fromisoformat(
                p.timestamp.replace("Z", "+00:00")
            ) >= cutoff
        ]

        if not resolved:
            return self._empty_report()

        # Overall accuracy
        correct_count = sum(1 for p in resolved if p.correct)
        overall_accuracy = correct_count / len(resolved)

        # Brier score: mean((confidence - outcome)^2)
        brier = sum(
            (p.confidence - (1.0 if p.correct else 0.0)) ** 2
            for p in resolved
        ) / len(resolved)

        # Calibration bins (10% intervals)
        bins = []
        for low in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            high = low + 0.1
            bin_preds = [p for p in resolved if low <= p.confidence < high]
            if bin_preds:
                actual_acc = sum(1 for p in bin_preds if p.correct) / len(bin_preds)
                brier_contrib = sum(
                    (p.confidence - (1.0 if p.correct else 0.0)) ** 2
                    for p in bin_preds
                ) / len(bin_preds)
                bins.append(CalibrationBin(
                    confidence_low=low,
                    confidence_high=high,
                    predicted_accuracy=(low + high) / 2,
                    actual_accuracy=actual_acc,
                    sample_count=len(bin_preds),
                    brier_contribution=brier_contrib,
                ))

        # Per-sleeve analysis
        by_sleeve = {}
        for sleeve in ["short_term", "mid_term", "long_term"]:
            sleeve_preds = [p for p in resolved if p.sleeve == sleeve]
            if sleeve_preds:
                acc = sum(1 for p in sleeve_preds if p.correct) / len(sleeve_preds)
                b = sum(
                    (p.confidence - (1.0 if p.correct else 0.0)) ** 2
                    for p in sleeve_preds
                ) / len(sleeve_preds)
                by_sleeve[sleeve] = {
                    "accuracy": round(acc, 3),
                    "brier": round(b, 4),
                    "count": len(sleeve_preds),
                }

        # Per-regime analysis
        by_regime = {}
        for regime in ["LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"]:
            regime_preds = [p for p in resolved if p.regime == regime]
            if regime_preds:
                acc = sum(1 for p in regime_preds if p.correct) / len(regime_preds)
                by_regime[regime] = {
                    "accuracy": round(acc, 3),
                    "count": len(regime_preds),
                }

        # Overconfidence score: average(confidence - accuracy_in_bin)
        overconf = 0.0
        if bins:
            overconf = sum(
                (b.predicted_accuracy - b.actual_accuracy) * b.sample_count
                for b in bins
            ) / sum(b.sample_count for b in bins)

        # Reliability score (inverse of calibration error)
        reliability = max(0, 1.0 - abs(overconf) * 2)

        return CalibrationReport(
            total_predictions=len(self.predictions),
            resolved_predictions=len(resolved),
            overall_accuracy=overall_accuracy,
            brier_score=brier,
            calibration_bins=bins,
            by_sleeve=by_sleeve,
            by_regime=by_regime,
            overconfidence_score=overconf,
            reliability_score=reliability,
        )

    def get_confidence_adjustment(self, stated_confidence: float) -> float:
        """
        Adjust Claude's stated confidence based on historical calibration.
        Returns adjusted confidence that better reflects actual accuracy.
        """
        report = self.get_calibration_report()
        if report.resolved_predictions < 20:
            return stated_confidence  # Not enough data to adjust

        # Find the calibration bin for this confidence level
        for b in report.calibration_bins:
            if b.confidence_low <= stated_confidence < b.confidence_high:
                if b.sample_count >= 5:
                    # Blend stated and historical: 60% historical, 40% stated
                    adjusted = 0.6 * b.actual_accuracy + 0.4 * stated_confidence
                    return round(adjusted, 3)

        return stated_confidence

    def _empty_report(self) -> CalibrationReport:
        return CalibrationReport(
            total_predictions=len(self.predictions),
            resolved_predictions=0,
            overall_accuracy=0,
            brier_score=0,
            calibration_bins=[],
            by_sleeve={},
            by_regime={},
            overconfidence_score=0,
            reliability_score=0.5,
        )
