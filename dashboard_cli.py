# dashboard.py
"""
Live Risk Dashboard (CLI)
Reads trades.json produced by TradeLogger and prints key risk/performance metrics.

Usage:
  python dashboard.py
  python dashboard.py --file trades.json
  python dashboard.py --days 7
  python dashboard.py --days 30
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import math


# -----------------------------
# Helpers
# -----------------------------

def parse_iso(ts: str) -> Optional[datetime]:
    """Parse ISO timestamp safely."""
    if not ts:
        return None
    try:
        # Handles "2026-02-19T17:00:00.123456"
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


def pct(x: float) -> str:
    return f"{x*100:.1f}%"


def money(x: float, currency: str = "£") -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}{currency}{abs(x):,.2f}"


# -----------------------------
# Core data model
# -----------------------------

@dataclass
class TradeRow:
    timestamp: datetime
    ticker: str
    action: str
    quantity: float
    status: str
    sleeve: str
    realized_pnl: float

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> Optional["TradeRow"]:
        ts = parse_iso(str(d.get("timestamp", "")))
        if not ts:
            return None

        ticker = str(d.get("ticker", "")).strip() or "?"
        action = str(d.get("action", "")).strip().upper() or "?"
        status = str(d.get("status", "")).strip().upper() or "?"

        qty = safe_float(d.get("quantity", 0.0), 0.0)

        # Sleeve might not exist yet — default to "unknown"
        sleeve = str(d.get("sleeve", "unknown")).strip().lower() or "unknown"
        if sleeve not in {"short_term", "mid_term", "long_term", "unknown"}:
            sleeve = "unknown"

        # Your current code doesn't always add realized_pnl; treat missing as 0
        realized_pnl = safe_float(d.get("realized_pnl", 0.0), 0.0)

        return TradeRow(
            timestamp=ts,
            ticker=ticker,
            action=action,
            quantity=qty,
            status=status,
            sleeve=sleeve,
            realized_pnl=realized_pnl,
        )


# -----------------------------
# Analytics
# -----------------------------

def load_trades(path: Path) -> List[TradeRow]:
    if not path.exists():
        raise FileNotFoundError(f"Trade log not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: List[TradeRow] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            row = TradeRow.from_dict(item)
            if row:
                rows.append(row)
    rows.sort(key=lambda r: r.timestamp)
    return rows


def filter_last_days(trades: List[TradeRow], days: int) -> List[TradeRow]:
    if not trades:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [t for t in trades if t.timestamp >= cutoff]


def compute_equity_curve_from_realized_pnl(trades: List[TradeRow]) -> List[Tuple[datetime, float]]:
    """
    Approx equity curve based solely on realized PnL in logs.
    If realized_pnl is always 0, the curve will be flat (expected).
    """
    curve: List[Tuple[datetime, float]] = []
    equity = 0.0
    for t in trades:
        if t.status == "EXECUTED":
            equity += t.realized_pnl
        curve.append((t.timestamp, equity))
    return curve


def max_drawdown(curve: List[Tuple[datetime, float]]) -> float:
    """Max drawdown on a curve of cumulative PnL (not account equity)."""
    if not curve:
        return 0.0
    peak = -math.inf
    mdd = 0.0
    for _, v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v - peak)  # negative number
    return mdd  # negative value


def summarize(trades: List[TradeRow]) -> Dict[str, Any]:
    total = len(trades)
    executed = [t for t in trades if t.status == "EXECUTED"]
    rejected = [t for t in trades if t.status == "REJECTED"]
    failed = [t for t in trades if t.status == "FAILED"]
    skipped = [t for t in trades if t.status == "SKIPPED"]

    buys = sum(1 for t in executed if t.action == "BUY")
    sells = sum(1 for t in executed if t.action == "SELL")

    pnl = sum(t.realized_pnl for t in executed)

    by_sleeve: Dict[str, Dict[str, Any]] = {}
    for sleeve in ["short_term", "mid_term", "long_term", "unknown"]:
        sleeve_trades = [t for t in trades if t.sleeve == sleeve]
        sleeve_exec = [t for t in sleeve_trades if t.status == "EXECUTED"]
        by_sleeve[sleeve] = {
            "total": len(sleeve_trades),
            "executed": len(sleeve_exec),
            "rejected": sum(1 for t in sleeve_trades if t.status == "REJECTED"),
            "failed": sum(1 for t in sleeve_trades if t.status == "FAILED"),
            "skipped": sum(1 for t in sleeve_trades if t.status == "SKIPPED"),
            "pnl": sum(t.realized_pnl for t in sleeve_exec),
            "buys": sum(1 for t in sleeve_exec if t.action == "BUY"),
            "sells": sum(1 for t in sleeve_exec if t.action == "SELL"),
        }

    curve = compute_equity_curve_from_realized_pnl(trades)
    mdd = max_drawdown(curve)

    return {
        "total": total,
        "executed": len(executed),
        "rejected": len(rejected),
        "failed": len(failed),
        "skipped": len(skipped),
        "buy_count": buys,
        "sell_count": sells,
        "realized_pnl": pnl,
        "max_drawdown_realized_pnl": mdd,  # negative number
        "by_sleeve": by_sleeve,
    }


# -----------------------------
# Dashboard printing
# -----------------------------

def print_dashboard(all_trades: List[TradeRow], days: int, currency: str = "£") -> None:
    trades = filter_last_days(all_trades, days)

    print("\n" + "=" * 72)
    print(f"AI TRADING AGENT — LIVE RISK DASHBOARD (last {days} days)")
    print("=" * 72)

    if not trades:
        print("No trades found in this window.")
        return

    s = summarize(trades)

    print("\n[1] Decision/Execution Summary")
    print(f"  Total decisions: {s['total']}")
    print(f"  Executed: {s['executed']} | Rejected: {s['rejected']} | Failed: {s['failed']} | Skipped: {s['skipped']}")
    print(f"  Executed Buys: {s['buy_count']} | Executed Sells: {s['sell_count']}")

    print("\n[2] Realized P&L (from logs)")
    print(f"  Realized P&L: {money(s['realized_pnl'], currency)}")
    dd = s["max_drawdown_realized_pnl"]
    print(f"  Max drawdown (realized P&L curve): {money(dd, currency)}")
    if s["executed"] > 0 and all(t.realized_pnl == 0 for t in trades if t.status == "EXECUTED"):
        print("  NOTE: realized_pnl is 0 for executed trades in your logs, so P&L/DD may be understated.")
        print("        To improve accuracy, add 'realized_pnl' when you close positions (or from broker fills).")

    print("\n[3] Sleeve Breakdown")
    print("  Sleeve       | Total | Exec | Rej | Fail | Skip | P&L")
    print("  ------------ | ----- | ---- | --- | ---- | ---- | -------------")
    for sleeve in ["short_term", "mid_term", "long_term", "unknown"]:
        row = s["by_sleeve"][sleeve]
        print(
            f"  {sleeve:<12} | {row['total']:>5} | {row['executed']:>4} | {row['rejected']:>3} | {row['failed']:>4} | {row['skipped']:>4} | {money(row['pnl'], currency):>13}"
        )

    print("\n[4] Operational Integrity Checks")
    # Duplicate ticker decisions in a short period can hint at race conditions
    # We'll flag if same ticker has >3 executed decisions within 1 hour
    executed = [t for t in trades if t.status == "EXECUTED"]
    executed_by_ticker: Dict[str, List[TradeRow]] = {}
    for t in executed:
        executed_by_ticker.setdefault(t.ticker, []).append(t)

    flags = 0
    for ticker, rows in executed_by_ticker.items():
        rows.sort(key=lambda r: r.timestamp)
        for i in range(len(rows)):
            window = [r for r in rows if rows[i].timestamp <= r.timestamp <= rows[i].timestamp + timedelta(hours=1)]
            if len(window) >= 4:
                flags += 1
                print(f"  [!] Possible over-trading/race: {ticker} executed {len(window)} times within 1 hour.")
                break

    if flags == 0:
        print("  [OK] No obvious over-trading/race patterns detected from executed trades.")

    print("\n[5] Recent Executions (latest 10)")
    for t in sorted(trades, key=lambda r: r.timestamp, reverse=True)[:10]:
        ts = t.timestamp.strftime("%Y-%m-%d %H:%M")
        print(f"  [{ts}Z] {t.status:<8} {t.action:<4} {t.ticker:<8} qty={t.quantity:<8} sleeve={t.sleeve}")

    print("\n" + "=" * 72 + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="trades.json", help="Path to trades.json")
    ap.add_argument("--days", type=int, default=7, help="Lookback window in days")
    ap.add_argument("--currency", default="£", help="Currency symbol for display")
    args = ap.parse_args()

    path = Path(args.file).expanduser().resolve()
    trades = load_trades(path)
    print_dashboard(trades, days=args.days, currency=args.currency)


if __name__ == "__main__":
    main()


'''
python dashboard.py
python dashboard.py --days 30
python dashboard.py --file trades.json --days 7

'''