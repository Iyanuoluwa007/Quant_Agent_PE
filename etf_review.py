"""
Quarterly ETF Review System -- Public Edition
Automatically reviews ETF lineup every 90 days.
All changes require explicit user approval before execution.

Sanitized version: Claude API calls and live trading logic removed.
Demo-only performance fetch with yfinance.
"""
import json
import sys
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

logger = logging.getLogger(__name__)

REVIEW_FILE = Path("etf_review_history.json")
PENDING_FILE = Path("etf_review_pending.json")
OVERRIDES_FILE = Path("etf_overrides.json")
SELL_QUEUE_FILE = Path("etf_sell_queue.json")

REVIEW_INTERVAL_DAYS = 90

# Benchmarks to compare against
BENCHMARKS = ["SPY", "QQQ", "VTI", "AGG"]


class ETFReviewEngine:
    """Quarterly ETF lineup review (sanitized public version)."""

    def __init__(self, config):
        self.config = config

    def is_review_due(self) -> bool:
        history = self._load_history()
        if not history:
            return True
        last_review = history[-1].get("timestamp", "")
        try:
            last_dt = datetime.fromisoformat(last_review.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - last_dt).days
            return days_since >= REVIEW_INTERVAL_DAYS
        except Exception:
            return True

    def run_review(self) -> dict:
        """Run a demo ETF review."""
        logger.info("[ETF-REVIEW] Starting demo ETF review...")
        etf_targets = self.config.LONG_TERM_ETF_TARGETS
        performance = {}

        for ticker in list(etf_targets.keys()) + BENCHMARKS:
            perf = self._fetch_etf_performance(ticker)
            if perf:
                performance[ticker] = perf

        # Simplified: No external AI evaluation
        review = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "NO_CHANGES",
            "market_outlook": "Stable",
            "overall_assessment": "Demo review - no real analysis",
            "recommendations": [],
            "changes_proposed": 0,
            "performance_snapshot": performance,
        }
        self._append_history(review)
        return review

    def get_pending(self) -> dict:
        if not PENDING_FILE.exists():
            return {}
        try:
            return json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def get_active_overrides(self) -> dict:
        if not OVERRIDES_FILE.exists():
            return {}
        try:
            return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _fetch_etf_performance(self, ticker: str) -> dict:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            if hist.empty or len(hist) < 20:
                return {}
            close = hist["Close"]
            current = close.iloc[-1]
            perf = {"ticker": ticker, "current_price": round(current, 2)}
            for label, days in [("3mo", 63), ("6mo", 126), ("1y", 252)]:
                if len(close) >= days:
                    past = close.iloc[-days]
                    perf[f"return_{label}"] = round(((current / past) - 1) * 100, 2)
                else:
                    perf[f"return_{label}"] = None
            return perf
        except Exception as e:
            logger.warning(f"[ETF-REVIEW] Failed to fetch {ticker}: {e}")
            return {}

    def _load_history(self) -> list:
        if not REVIEW_FILE.exists():
            return []
        try:
            return json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _append_history(self, review: dict):
        history = self._load_history()
        history.append(review)
        REVIEW_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="ETF Quarterly Review - Public Edition")
    ap.add_argument("--history", action="store_true", help="View review history")
    ap.add_argument("--force", action="store_true", help="Force demo review now")
    ap.add_argument("--clear", action="store_true", help="Clear overrides")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from config import TradingConfig
    config = TradingConfig()
    engine = ETFReviewEngine(config)

    if args.history:
        history = engine._load_history()
        if not history:
            print("[ETF-REVIEW] No review history.")
            return
        for r in history[-5:]:
            ts = r.get("timestamp", "?")[:16]
            status = r.get("status", "?")
            changes = r.get("changes_proposed", 0)
            print(f"  {ts} | {status} | {changes} changes proposed")
        return

    if args.clear:
        OVERRIDES_FILE.unlink(missing_ok=True)
        print("[ETF-REVIEW] Overrides cleared. Using config.py defaults.")
        return

    if args.force or engine.is_review_due():
        print("[ETF-REVIEW] Running demo review...")
        result = engine.run_review()
        print(f"  Status: {result.get('status')}")
        print(f"  Changes: {result.get('changes_proposed', 0)}")
    else:
        print("[ETF-REVIEW] Not due yet. Use --force to run anyway.")


if __name__ == "__main__":
    main()