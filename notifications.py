"""
Email Notification System (Sanitized Demo)
Sends alerts and daily summaries. No live emails are sent.
Reads local dummy data only.
"""
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TRADES_FILE = Path("trades.json")
LAST_SUMMARY_FILE = Path(".last_daily_summary")

class EmailNotifier:
    """Email notification service for the trading agent (demo)."""

    def __init__(self, config=None):
        self.enabled = False  # Always disabled in public demo
        self.config = config

    def send(self, subject: str, body: str, html: bool = False) -> bool:
        """Simulate sending an email. Logs message instead of sending."""
        logger.info(f"[EMAIL DEMO] Would send: {subject}\n{body[:200]}...")
        print(f"[EMAIL DEMO] Subject: {subject}")
        return True

    # ──────────────────────────────────────────────────────────────
    # NOTIFICATION TYPES
    # ──────────────────────────────────────────────────────────────

    def send_daily_summary(self, broker_data: dict = None) -> bool:
        trades = self._load_trades()
        today = datetime.now(timezone.utc).date()
        today_trades = [t for t in trades if t.get("timestamp","")[:10]==str(today)]
        executed = [t for t in today_trades if t.get("status")=="EXECUTED"]
        rejected = [t for t in today_trades if t.get("status")=="REJECTED"]

        lines = [
            f"Daily Summary -- {today.strftime('%A, %d %B %Y')}",
            "="*50,
            "",
        ]

        if broker_data:
            total = broker_data.get("total", 1000)
            cash = broker_data.get("free", 500)
            pnl = broker_data.get("result", 0)
            sign = "+" if pnl>=0 else ""
            lines.extend([
                f"Portfolio: ${total:,.2f}",
                f"Cash: ${cash:,.2f}",
                f"Day P&L: {sign}${pnl:,.2f}",
                "",
            ])

        lines.append(f"Trades today: {len(executed)} executed, {len(rejected)} rejected")
        body = "\n".join(lines)
        return self.send(f"Daily Summary - {today}", body)

    def send_etf_review_alert(self, changes_count: int) -> bool:
        body = f"{changes_count} ETF change(s) pending approval (demo)."
        return self.send(f"{changes_count} ETF Changes Pending", body)

    def send_kill_switch_alert(self, drawdown_pct: float) -> bool:
        body = f"Drawdown kill switch triggered (demo). Current drawdown: {drawdown_pct:.1f}%"
        return self.send("KILL SWITCH ACTIVATED (DEMO)", body)

    def send_error_alert(self, error_msg: str) -> bool:
        body = f"Critical error in trading agent (demo):\n\n{error_msg}"
        return self.send("Error Alert (DEMO)", body)

    def send_data_issue_alert(self, missing_count: int, total_count: int) -> bool:
        body = f"ETF Review skipped due to data issues (demo). Missing {missing_count}/{total_count} tickers."
        return self.send("ETF Review -- DATA ISSUE (DEMO)", body)

    # ──────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────

    def _should_send_daily(self) -> bool:
        """Always allow daily demo summary."""
        return True

    def _mark_daily_sent(self):
        """Mark today's daily summary as sent (demo)."""
        today = datetime.now(timezone.utc).date()
        LAST_SUMMARY_FILE.write_text(str(today))

    def _load_trades(self) -> list[dict]:
        """Load trades (dummy if missing)."""
        if not TRADES_FILE.exists():
            return [
                {"timestamp": str(datetime.now(timezone.utc)), "status": "EXECUTED", "ticker":"DEMO1","action":"BUY","sleeve":"long_term"},
                {"timestamp": str(datetime.now(timezone.utc)), "status": "REJECTED", "ticker":"DEMO2","action":"SELL","sleeve":"short_term"}
            ]
        try:
            return json.loads(TRADES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []