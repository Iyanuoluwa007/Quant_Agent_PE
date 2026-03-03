"""
Quarterly ETF Review System
Automatically reviews ETF lineup every 90 days using Claude analysis.
All changes require explicit user approval before execution.

Flow:
  1. Agent checks: last review > 90 days ago?
  2. Fetches 3mo/6mo/1y performance for all ETFs + benchmarks
  3. Claude evaluates: KEEP / SWAP / REDUCE / INCREASE per ETF
  4. If >30% of tickers have no data -> skip, alert DATA ISSUE
  5. Saves recommendations to pending file
  6. Sends email notification (if configured)

User approval:
  python etf_review.py --pending     # View suggestions
  python etf_review.py --approve     # Approve/reject each change
  python etf_review.py --history     # View past reviews

After approval:
  - Override file written (etf_overrides.json)
  - Sell queue created for swapped ETFs
  - Next cycle: agent sells old, starts buying new
"""
import json
import sys
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

REVIEW_FILE = Path("etf_review_history.json")
PENDING_FILE = Path("etf_review_pending.json")
OVERRIDES_FILE = Path("etf_overrides.json")
SELL_QUEUE_FILE = Path("etf_sell_queue.json")

REVIEW_INTERVAL_DAYS = 90

# Benchmarks to compare against
BENCHMARKS = ["SPY", "QQQ", "VTI", "AGG"]

# Claude system prompt for ETF review (simplified for public edition)
ETF_REVIEW_PROMPT = """You are a portfolio analyst reviewing a long-term ETF allocation.

RULES:
- Be CONSERVATIVE. Favour KEEP for core index funds (VOO, VTI, QQQ, BND).
- Only suggest SWAP for persistent underperformance (6mo+ trailing benchmark).
- REDUCE only if allocation is clearly too high relative to risk/reward.
- INCREASE only for significantly underweight positions with strong outlook.
- Never suggest more than 2 changes per review cycle.
- Consider expense ratios, liquidity, and tracking error.

RESPONSE FORMAT (JSON only):
{
    "market_outlook": "Brief macro view affecting ETF allocation",
    "recommendations": [
        {
            "ticker": "ARKK",
            "action": "KEEP|SWAP|REDUCE|INCREASE",
            "swap_to": null,
            "new_weight": null,
            "confidence": 0.75,
            "reasoning": "Why this recommendation"
        }
    ],
    "overall_assessment": "Summary of portfolio health"
}
"""


class ETFReviewEngine:
    """Quarterly ETF lineup review with Claude analysis."""

    def __init__(self, config):
        self.config = config

    def is_review_due(self) -> bool:
        """Check if 90 days have passed since last review."""
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

    def run_review(self) -> Optional[dict]:
        """
        Run the quarterly ETF review.
        Returns review results or None if skipped.
        """
        logger.info("[ETF-REVIEW] Starting quarterly ETF review...")

        # 1. Fetch performance data for all ETFs
        etf_targets = self.config.LONG_TERM_ETF_TARGETS
        performance = {}
        no_data_count = 0

        for ticker in list(etf_targets.keys()) + BENCHMARKS:
            perf = self._fetch_etf_performance(ticker)
            if perf:
                performance[ticker] = perf
            else:
                no_data_count += 1
                logger.warning(f"[ETF-REVIEW] No data for {ticker}")

        # 2. Data quality gate
        total_tickers = len(etf_targets) + len(BENCHMARKS)
        if no_data_count / total_tickers > 0.30:
            logger.error(
                f"[ETF-REVIEW] DATA ISSUE: {no_data_count}/{total_tickers} "
                f"tickers missing data. Skipping review."
            )
            return {"status": "SKIPPED", "reason": "data_quality", "missing": no_data_count}

        # 3. Build analysis prompt
        prompt = self._build_prompt(etf_targets, performance)

        # 4. Run Claude analysis
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.config.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=self.config.CLAUDE_MODEL,
                max_tokens=2000,
                system=ETF_REVIEW_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            analysis = json.loads(cleaned.strip())
        except Exception as e:
            logger.error(f"[ETF-REVIEW] Claude analysis failed: {e}")
            return {"status": "FAILED", "reason": str(e)}

        # 5. Filter to actionable recommendations
        changes = [
            r for r in analysis.get("recommendations", [])
            if r.get("action") in ("SWAP", "REDUCE", "INCREASE")
        ]

        # 6. Save pending review
        review = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "PENDING" if changes else "NO_CHANGES",
            "market_outlook": analysis.get("market_outlook", ""),
            "overall_assessment": analysis.get("overall_assessment", ""),
            "recommendations": analysis.get("recommendations", []),
            "changes_proposed": len(changes),
            "performance_snapshot": performance,
        }

        if changes:
            self._save_pending(review)
            logger.info(
                f"[ETF-REVIEW] {len(changes)} changes proposed. "
                f"Run 'python etf_review.py --pending' to review."
            )
        else:
            logger.info("[ETF-REVIEW] No changes recommended. Portfolio looks healthy.")

        # 7. Save to history
        self._append_history(review)

        return review

    def get_pending(self) -> Optional[dict]:
        """Get pending review awaiting approval."""
        if not PENDING_FILE.exists():
            return None
        try:
            return json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None

    def approve_changes(self, interactive: bool = True) -> dict:
        """
        Interactive approval of pending changes.
        Each change needs individual y/n approval.
        """
        pending = self.get_pending()
        if not pending:
            print("[ETF-REVIEW] No pending changes to approve.")
            return {"approved": 0, "rejected": 0}

        recommendations = pending.get("recommendations", [])
        changes = [r for r in recommendations if r.get("action") in ("SWAP", "REDUCE", "INCREASE")]

        if not changes:
            print("[ETF-REVIEW] No actionable changes in pending review.")
            return {"approved": 0, "rejected": 0}

        print("\n" + "=" * 60)
        print("  QUARTERLY ETF REVIEW -- PENDING APPROVAL")
        print("=" * 60)
        print(f"  Review date: {pending.get('timestamp', '?')[:16]}")
        print(f"  Outlook: {pending.get('market_outlook', 'N/A')[:80]}")
        print(f"  Changes proposed: {len(changes)}")
        print("=" * 60)

        approved = []
        rejected = []

        for i, change in enumerate(changes, 1):
            ticker = change.get("ticker", "?")
            action = change.get("action", "?")
            reasoning = change.get("reasoning", "No reasoning provided")
            confidence = change.get("confidence", 0)

            print(f"\n  [{i}/{len(changes)}] {action} {ticker}")
            print(f"  Confidence: {confidence:.0%}")
            print(f"  Reasoning: {reasoning}")

            if action == "SWAP":
                swap_to = change.get("swap_to", "?")
                print(f"  Swap to: {swap_to}")
            elif action in ("REDUCE", "INCREASE"):
                new_weight = change.get("new_weight")
                if new_weight:
                    print(f"  New weight: {new_weight:.0%}")

            if interactive:
                response = input("  Approve? (y/n): ").strip().lower()
                if response == "y":
                    approved.append(change)
                    print("  [OK] Approved")
                else:
                    rejected.append(change)
                    print("  [--] Rejected")
            else:
                rejected.append(change)

        # Apply approved changes
        if approved:
            self._apply_approvals(approved, pending)

        # Clear pending
        PENDING_FILE.unlink(missing_ok=True)

        result = {"approved": len(approved), "rejected": len(rejected)}
        print(f"\n  Result: {len(approved)} approved, {len(rejected)} rejected")
        if approved:
            print("  Override file written. Changes will apply next cycle.")
        print("=" * 60 + "\n")

        return result

    def get_active_overrides(self) -> Optional[dict]:
        """Get currently active ETF overrides (applied by agent)."""
        if not OVERRIDES_FILE.exists():
            return None
        try:
            return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None

    def get_sell_queue(self) -> list[dict]:
        """Get pending sell orders from ETF swaps."""
        if not SELL_QUEUE_FILE.exists():
            return []
        try:
            return json.loads(SELL_QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def clear_sell_queue_item(self, ticker: str):
        """Remove a ticker from the sell queue after execution."""
        queue = self.get_sell_queue()
        queue = [q for q in queue if q.get("ticker") != ticker]
        SELL_QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL METHODS
    # ═══════════════════════════════════════════════════════════════

    def _fetch_etf_performance(self, ticker: str) -> Optional[dict]:
        """Fetch 3mo/6mo/1y performance data for an ETF."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            if hist.empty or len(hist) < 20:
                return None

            close = hist["Close"]
            current = close.iloc[-1]
            info = stock.info

            perf = {
                "ticker": ticker,
                "current_price": round(current, 2),
                "expense_ratio": info.get("annualReportExpenseRatio"),
                "aum": info.get("totalAssets"),
            }

            # Calculate returns
            for label, days in [("3mo", 63), ("6mo", 126), ("1y", 252)]:
                if len(close) >= days:
                    past = close.iloc[-days]
                    perf[f"return_{label}"] = round(((current / past) - 1) * 100, 2)
                else:
                    perf[f"return_{label}"] = None

            # Volatility (annualized)
            if len(close) >= 60:
                daily_returns = close.pct_change().dropna()
                perf["volatility_1y"] = round(daily_returns.std() * (252 ** 0.5) * 100, 2)
            else:
                perf["volatility_1y"] = None

            return perf
        except Exception as e:
            logger.warning(f"[ETF-REVIEW] Failed to fetch {ticker}: {e}")
            return None

    def _build_prompt(self, etf_targets: dict, performance: dict) -> str:
        """Build Claude analysis prompt with performance data."""
        parts = ["## CURRENT ETF ALLOCATION"]
        for ticker, weight in etf_targets.items():
            perf = performance.get(ticker, {})
            ret_3m = perf.get("return_3mo", "N/A")
            ret_6m = perf.get("return_6mo", "N/A")
            ret_1y = perf.get("return_1y", "N/A")
            vol = perf.get("volatility_1y", "N/A")
            parts.append(
                f"  {ticker}: weight={weight:.0%} | "
                f"3mo={ret_3m}% | 6mo={ret_6m}% | 1y={ret_1y}% | vol={vol}%"
            )

        parts.append("\n## BENCHMARKS")
        for ticker in BENCHMARKS:
            perf = performance.get(ticker, {})
            ret_3m = perf.get("return_3mo", "N/A")
            ret_6m = perf.get("return_6mo", "N/A")
            ret_1y = perf.get("return_1y", "N/A")
            parts.append(f"  {ticker}: 3mo={ret_3m}% | 6mo={ret_6m}% | 1y={ret_1y}%")

        parts.append(
            "\n## TASK"
            "\nReview each ETF. For core index funds (VOO, VTI, QQQ, BND), "
            "strongly favour KEEP. Only suggest changes with clear evidence. "
            "Max 2 changes per cycle."
        )

        return "\n".join(parts)

    def _apply_approvals(self, approved: list[dict], review: dict):
        """Write override file and sell queue from approved changes."""
        from config import TradingConfig
        config = TradingConfig()
        current_targets = dict(config.LONG_TERM_ETF_TARGETS)
        sell_queue = []

        for change in approved:
            ticker = change["ticker"]
            action = change["action"]

            if action == "SWAP":
                old_weight = current_targets.pop(ticker, 0)
                new_ticker = change.get("swap_to")
                if new_ticker and old_weight > 0:
                    current_targets[new_ticker] = old_weight
                    sell_queue.append({
                        "ticker": ticker,
                        "reason": f"Swapped to {new_ticker}",
                        "approved_at": datetime.now(timezone.utc).isoformat(),
                    })

            elif action == "REDUCE":
                new_weight = change.get("new_weight")
                if new_weight and ticker in current_targets:
                    current_targets[ticker] = new_weight

            elif action == "INCREASE":
                new_weight = change.get("new_weight")
                if new_weight and ticker in current_targets:
                    current_targets[ticker] = new_weight

        # Normalize weights to sum to 1.0
        total = sum(current_targets.values())
        if total > 0:
            current_targets = {k: round(v / total, 4) for k, v in current_targets.items()}

        # Save override file
        override = {
            "targets": current_targets,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "review_date": review.get("timestamp", ""),
            "changes": [c["ticker"] + ":" + c["action"] for c in approved],
        }
        OVERRIDES_FILE.write_text(json.dumps(override, indent=2), encoding="utf-8")
        logger.info(f"[ETF-REVIEW] Override file written: {OVERRIDES_FILE}")

        # Save sell queue
        if sell_queue:
            existing = self.get_sell_queue()
            existing.extend(sell_queue)
            SELL_QUEUE_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            logger.info(f"[ETF-REVIEW] {len(sell_queue)} sells queued")

    def _save_pending(self, review: dict):
        PENDING_FILE.write_text(json.dumps(review, indent=2), encoding="utf-8")

    def _load_history(self) -> list[dict]:
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


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="ETF Quarterly Review")
    ap.add_argument("--pending", action="store_true", help="View pending changes")
    ap.add_argument("--approve", action="store_true", help="Approve/reject pending changes")
    ap.add_argument("--history", action="store_true", help="View review history")
    ap.add_argument("--force", action="store_true", help="Force run review now")
    ap.add_argument("--clear", action="store_true", help="Clear overrides (revert to defaults)")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    from config import TradingConfig
    config = TradingConfig()
    engine = ETFReviewEngine(config)

    if args.pending:
        pending = engine.get_pending()
        if not pending:
            print("[ETF-REVIEW] No pending changes.")
            return
        print(json.dumps(pending, indent=2))
        return

    if args.approve:
        engine.approve_changes(interactive=True)
        return

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

    if args.force:
        result = engine.run_review()
        if result:
            print(json.dumps(result, indent=2, default=str))
        return

    # Default: check if due
    if engine.is_review_due():
        print("[ETF-REVIEW] Review is due. Running...")
        result = engine.run_review()
        if result:
            print(f"  Status: {result.get('status')}")
            print(f"  Changes: {result.get('changes_proposed', 0)}")
    else:
        print("[ETF-REVIEW] Not due yet. Use --force to run anyway.")


if __name__ == "__main__":
    main()
