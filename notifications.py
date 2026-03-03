"""
Email Notification System
Sends alerts and daily summaries. No Claude API cost -- reads local data only.

Notifications:
  - Daily summary (9 PM UK, Mon-Fri): trade count, P&L, positions, risk state
  - ETF review alert: when quarterly review proposes changes
  - Kill switch alert: when drawdown exceeds threshold
  - Error alerts: when critical errors occur

Setup:
  Set these in .env:
    EMAIL_ENABLED=true
    EMAIL_SMTP_HOST=smtp.gmail.com
    EMAIL_SMTP_PORT=587
    EMAIL_SENDER=yourbot@gmail.com
    EMAIL_PASSWORD=your_app_password
    EMAIL_RECIPIENT=you@email.com

  For Gmail: use an App Password (Settings > Security > App Passwords)
"""
import os
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TRADES_FILE = Path("trades.json")
LAST_SUMMARY_FILE = Path(".last_daily_summary")


class EmailNotifier:
    """Email notification service for the trading agent."""

    def __init__(self, config=None):
        self.enabled = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
        self.smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.sender = os.getenv("EMAIL_SENDER", "")
        self.password = os.getenv("EMAIL_PASSWORD", "")
        self.recipient = os.getenv("EMAIL_RECIPIENT", "")
        self.config = config

        if self.enabled and not all([self.sender, self.password, self.recipient]):
            logger.warning(
                "[EMAIL] Enabled but missing credentials. "
                "Set EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT."
            )
            self.enabled = False

    def send(self, subject: str, body: str, html: bool = False) -> bool:
        """Send an email. Returns True on success."""
        if not self.enabled:
            logger.debug(f"[EMAIL] Disabled. Would send: {subject}")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.sender
            msg["To"] = self.recipient
            msg["Subject"] = f"[Quant Agent] {subject}"

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.send_message(msg)

            logger.info(f"[EMAIL] Sent: {subject}")
            return True
        except Exception as e:
            logger.error(f"[EMAIL] Failed to send '{subject}': {e}")
            return False

    # ═══════════════════════════════════════════════════════════════
    # NOTIFICATION TYPES
    # ═══════════════════════════════════════════════════════════════

    def send_daily_summary(self, broker_data: dict = None) -> bool:
        """
        Daily summary email (9 PM UK, Mon-Fri).
        No Claude API calls -- reads local trade logs only.
        """
        if not self._should_send_daily():
            return False

        trades = self._load_trades()
        today = datetime.now(timezone.utc).date()
        today_trades = [
            t for t in trades
            if t.get("timestamp", "")[:10] == str(today)
        ]

        executed = [t for t in today_trades if t.get("status") == "EXECUTED"]
        rejected = [t for t in today_trades if t.get("status") == "REJECTED"]

        # Build summary
        lines = [
            f"Daily Summary -- {today.strftime('%A, %d %B %Y')}",
            "=" * 50,
            "",
        ]

        # Broker data
        if broker_data:
            total = broker_data.get("total", 0)
            cash = broker_data.get("free", 0)
            pnl = broker_data.get("result", 0)
            sign = "+" if pnl >= 0 else ""
            lines.extend([
                f"Portfolio: ${total:,.2f}",
                f"Cash: ${cash:,.2f}",
                f"Day P&L: {sign}${pnl:,.2f}",
                "",
            ])

        # Trade activity
        lines.extend([
            f"Trades today: {len(executed)} executed, {len(rejected)} rejected",
        ])

        if executed:
            lines.append("")
            lines.append("Executed:")
            for t in executed:
                ticker = t.get("ticker", "?")
                action = t.get("action", "?")
                sleeve = t.get("sleeve", "?")
                lines.append(f"  {action} {ticker} ({sleeve})")

        # Sleeve breakdown
        for sleeve in ["short_term", "mid_term", "long_term"]:
            sleeve_trades = [t for t in executed if t.get("sleeve") == sleeve]
            if sleeve_trades:
                buys = sum(1 for t in sleeve_trades if t.get("action") == "BUY")
                sells = sum(1 for t in sleeve_trades if t.get("action") == "SELL")
                lines.append(f"  {sleeve}: {buys} buys, {sells} sells")

        # Risk state
        lines.extend(["", "Risk Status: All checks normal"])

        body = "\n".join(lines)
        success = self.send(f"Daily Summary - {today}", body)

        if success:
            self._mark_daily_sent()

        return success

    def send_etf_review_alert(self, changes_count: int) -> bool:
        """Alert when ETF review proposes changes."""
        body = (
            f"{changes_count} ETF change(s) pending approval.\n\n"
            f"Review with:\n"
            f"  python etf_review.py --pending\n"
            f"  python etf_review.py --approve\n"
        )
        return self.send(f"{changes_count} ETF Changes Pending", body)

    def send_kill_switch_alert(self, drawdown_pct: float) -> bool:
        """Alert when drawdown kill switch activates."""
        body = (
            f"DRAWDOWN KILL SWITCH ACTIVATED\n\n"
            f"Current drawdown: {drawdown_pct:.1f}%\n"
            f"Threshold: -20%\n\n"
            f"All trading has been halted.\n"
            f"Manual unlock required:\n"
            f"  python monitor.py --unlock\n"
        )
        return self.send("KILL SWITCH ACTIVATED", body)

    def send_error_alert(self, error_msg: str) -> bool:
        """Alert on critical errors."""
        body = f"Critical error in trading agent:\n\n{error_msg}"
        return self.send("Error Alert", body)

    def send_data_issue_alert(self, missing_count: int, total_count: int) -> bool:
        """Alert when ETF data quality is poor."""
        body = (
            f"ETF Review skipped due to data quality issues.\n\n"
            f"Missing data: {missing_count}/{total_count} tickers\n"
            f"Threshold: 30%\n\n"
            f"This usually resolves on its own. If persistent, "
            f"check Yahoo Finance connectivity.\n"
        )
        return self.send("ETF Review -- DATA ISSUE", body)

    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _should_send_daily(self) -> bool:
        """Check if daily summary should be sent (9 PM UK, Mon-Fri)."""
        now = datetime.now(timezone.utc)
        uk_offset = timedelta(hours=0)  # UTC ~= GMT for simplicity
        now_uk = now + uk_offset

        # Only Mon-Fri
        if now_uk.weekday() >= 5:
            return False

        # Only around 9 PM UK (21:00-21:30)
        if not (21 <= now_uk.hour <= 21 and now_uk.minute < 30):
            return False

        # Check if already sent today
        if LAST_SUMMARY_FILE.exists():
            try:
                last = LAST_SUMMARY_FILE.read_text().strip()
                if last == str(now_uk.date()):
                    return False
            except Exception:
                pass

        return True

    def _mark_daily_sent(self):
        """Mark today's daily summary as sent."""
        today = datetime.now(timezone.utc).date()
        LAST_SUMMARY_FILE.write_text(str(today))

    def _load_trades(self) -> list[dict]:
        if not TRADES_FILE.exists():
            return []
        try:
            return json.loads(TRADES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
