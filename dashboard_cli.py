"""
Quant Agent v2.1 -- Demo CLI Dashboard

This CLI dashboard reads the demo trade log produced by the public
version of the agent and prints basic activity metrics.

All proprietary analytics, performance attribution models, and
risk calculations have been removed for the public edition.

Usage:
  python dashboard_cli.py
  python dashboard_cli.py --file trades_demo.json
  python dashboard_cli.py --days 7
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# ===============================================================
# Helpers
# ===============================================================

def parse_iso(ts: str) -> Optional[datetime]:

    if not ts:
        return None

    try:

        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


def safe_float(x: Any, default: float = 0.0) -> float:

    try:

        if x is None:
            return default

        return float(x)

    except Exception:
        return default


def money(x: float, currency: str = "$") -> str:

    sign = "-" if x < 0 else ""

    return f"{sign}{currency}{abs(x):,.2f}"


# ===============================================================
# Trade model
# ===============================================================

@dataclass
class TradeRow:

    timestamp: datetime
    ticker: str
    action: str
    quantity: float
    status: str
    sleeve: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> Optional["TradeRow"]:

        ts = parse_iso(str(d.get("timestamp", "")))

        if not ts:
            return None

        ticker = str(d.get("ticker", "UNKNOWN")).upper()
        action = str(d.get("action", "UNKNOWN")).upper()
        status = str(d.get("status", "UNKNOWN")).upper()

        quantity = safe_float(d.get("quantity", 0))

        sleeve = str(d.get("sleeve", "unknown")).lower()

        return TradeRow(
            timestamp=ts,
            ticker=ticker,
            action=action,
            quantity=quantity,
            status=status,
            sleeve=sleeve,
        )


# ===============================================================
# Load trades
# ===============================================================

def load_trades(path: Path) -> List[TradeRow]:

    if not path.exists():
        raise FileNotFoundError(f"Trade log not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    rows: List[TradeRow] = []

    if isinstance(raw, list):

        for item in raw:

            if isinstance(item, dict):

                row = TradeRow.from_dict(item)

                if row:
                    rows.append(row)

    rows.sort(key=lambda r: r.timestamp)

    return rows


def filter_last_days(trades: List[TradeRow], days: int) -> List[TradeRow]:

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    return [t for t in trades if t.timestamp >= cutoff]


# ===============================================================
# Summary metrics
# ===============================================================

def summarize(trades: List[TradeRow]) -> Dict[str, Any]:

    total = len(trades)

    executed = [t for t in trades if t.status == "EXECUTED"]

    rejected = [t for t in trades if t.status == "REJECTED"]

    failed = [t for t in trades if t.status == "FAILED"]

    skipped = [t for t in trades if t.status == "SKIPPED"]

    buys = sum(1 for t in executed if t.action == "BUY")

    sells = sum(1 for t in executed if t.action == "SELL")

    by_sleeve: Dict[str, Dict[str, int]] = {}

    for sleeve in ["short_term", "mid_term", "long_term", "unknown"]:

        sleeve_rows = [t for t in trades if t.sleeve == sleeve]

        sleeve_exec = [t for t in sleeve_rows if t.status == "EXECUTED"]

        by_sleeve[sleeve] = {
            "total": len(sleeve_rows),
            "executed": len(sleeve_exec),
            "rejected": sum(1 for t in sleeve_rows if t.status == "REJECTED"),
            "failed": sum(1 for t in sleeve_rows if t.status == "FAILED"),
            "skipped": sum(1 for t in sleeve_rows if t.status == "SKIPPED"),
        }

    return {
        "total": total,
        "executed": len(executed),
        "rejected": len(rejected),
        "failed": len(failed),
        "skipped": len(skipped),
        "buy_count": buys,
        "sell_count": sells,
        "by_sleeve": by_sleeve,
    }


# ===============================================================
# Dashboard printing
# ===============================================================

def print_dashboard(all_trades: List[TradeRow], days: int, currency: str = "$"):

    trades = filter_last_days(all_trades, days)

    print("\n" + "=" * 70)

    print(f"QUANT AGENT DEMO — ACTIVITY DASHBOARD (last {days} days)")

    print("=" * 70)

    if not trades:

        print("No trades recorded in this window.")

        return

    s = summarize(trades)

    print("\n[1] Decision Summary")

    print(f"  Total decisions: {s['total']}")

    print(
        f"  Executed: {s['executed']} | Rejected: {s['rejected']} | Failed: {s['failed']} | Skipped: {s['skipped']}"
    )

    print(f"  Buys: {s['buy_count']} | Sells: {s['sell_count']}")

    print("\n[2] Sleeve Breakdown")

    print("  Sleeve       | Total | Executed | Rejected | Failed | Skipped")

    print("  ------------ | ----- | -------- | -------- | ------ | -------")

    for sleeve in ["short_term", "mid_term", "long_term", "unknown"]:

        row = s["by_sleeve"][sleeve]

        print(
            f"  {sleeve:<12} | {row['total']:>5} | {row['executed']:>8} | {row['rejected']:>8} | {row['failed']:>6} | {row['skipped']:>7}"
        )

    print("\n[3] Recent Executions")

    for t in sorted(trades, key=lambda r: r.timestamp, reverse=True)[:10]:

        ts = t.timestamp.strftime("%Y-%m-%d %H:%M")

        print(
            f"  [{ts}Z] {t.status:<8} {t.action:<4} {t.ticker:<8} qty={t.quantity:<8} sleeve={t.sleeve}"
        )

    print("\n" + "=" * 70 + "\n")


# ===============================================================
# CLI
# ===============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--file",
        default="trades_demo.json",
        help="Path to demo trade log",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback window in days",
    )

    parser.add_argument(
        "--currency",
        default="$",
        help="Currency symbol",
    )

    args = parser.parse_args()

    path = Path(args.file).expanduser().resolve()

    trades = load_trades(path)

    print_dashboard(trades, days=args.days, currency=args.currency)


if __name__ == "__main__":
    main()