"""
Prediction Accuracy Tracker
Logs direction predictions, price targets, and timing estimates.
Computes hit rates by sleeve, ticker, and market regime.

This module provides the raw data that feeds into the calibration
and meta-model modules. It focuses on simple, concrete metrics:
  - Direction accuracy (did price go the predicted way?)
  - Target hit rate (did price reach take-profit?)
  - Stop hit rate (did price hit stop-loss?)
  - Timing accuracy (did the trade resolve within expected hold time?)
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ACCURACY_FILE = Path("accuracy_log.json")


class AccuracyTracker:
    """
    Tracks concrete prediction outcomes for performance analysis.

    Simpler than the calibration module -- this just tracks
    hit/miss rates without building calibration curves.
    """

    def __init__(self):
        self._log: list[dict] = []
        self._load()

    def _load(self):
        if ACCURACY_FILE.exists():
            try:
                data = json.loads(ACCURACY_FILE.read_text(encoding="utf-8"))
                self._log = data.get("entries", [])
            except Exception:
                self._log = []

    def _save(self):
        data = {
            "entries": self._log,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        ACCURACY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_outcome(
        self,
        ticker: str,
        sleeve: str,
        action: str,
        entry_price: float,
        exit_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        confidence: float,
        hold_days: int,
        regime: str = "NORMAL",
    ):
        """Record a completed trade outcome."""
        if action == "BUY":
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            direction_correct = exit_price > entry_price
            target_hit = (take_profit and exit_price >= take_profit)
            stop_hit = (stop_loss and exit_price <= stop_loss)
        else:
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100
            direction_correct = exit_price < entry_price
            target_hit = (take_profit and exit_price <= take_profit)
            stop_hit = (stop_loss and exit_price >= stop_loss)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "sleeve": sleeve,
            "action": action,
            "confidence": confidence,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_pct": round(pnl_pct, 2),
            "direction_correct": direction_correct,
            "target_hit": bool(target_hit),
            "stop_hit": bool(stop_hit),
            "hold_days": hold_days,
            "regime": regime,
        }

        self._log.append(entry)
        self._save()

    def get_stats(self, days: int = 90) -> dict:
        """Get accuracy statistics for the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = [
            e for e in self._log
            if datetime.fromisoformat(
                e["timestamp"].replace("Z", "+00:00")
            ) >= cutoff
        ]

        if not recent:
            return {"total": 0, "direction_accuracy": 0, "avg_pnl": 0}

        total = len(recent)
        direction_correct = sum(1 for e in recent if e["direction_correct"])
        targets_hit = sum(1 for e in recent if e["target_hit"])
        stops_hit = sum(1 for e in recent if e["stop_hit"])
        avg_pnl = sum(e["pnl_pct"] for e in recent) / total

        # Per-sleeve breakdown
        by_sleeve = {}
        for sleeve in ["short_term", "mid_term", "long_term"]:
            s = [e for e in recent if e["sleeve"] == sleeve]
            if s:
                by_sleeve[sleeve] = {
                    "total": len(s),
                    "direction_accuracy": round(
                        sum(1 for e in s if e["direction_correct"]) / len(s), 3
                    ),
                    "avg_pnl": round(sum(e["pnl_pct"] for e in s) / len(s), 2),
                    "target_hit_rate": round(
                        sum(1 for e in s if e["target_hit"]) / len(s), 3
                    ),
                }

        return {
            "total": total,
            "direction_accuracy": round(direction_correct / total, 3),
            "target_hit_rate": round(targets_hit / total, 3),
            "stop_hit_rate": round(stops_hit / total, 3),
            "avg_pnl": round(avg_pnl, 2),
            "by_sleeve": by_sleeve,
        }
