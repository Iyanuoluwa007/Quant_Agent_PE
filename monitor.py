"""
Portfolio Monitor
Tracks portfolio value over time, calculates drawdown, and enforces
the -20% kill switch. Also generates daily/weekly summaries.

Usage:
  python monitor.py                  # Show current status
  python monitor.py --check          # Check drawdown + update history
  python monitor.py --report daily   # Daily performance report
  python monitor.py --report weekly  # Weekly performance report
  python monitor.py --history        # Show equity curve
  python monitor.py --reset          # Clear history and start fresh
"""
import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Fix imports
SCRIPT_DIR = str(Path(__file__).parent.resolve())
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

HISTORY_FILE = Path("portfolio_history.json")
KILL_SWITCH_FILE = Path("KILL_SWITCH_ACTIVE.flag")


# ═══════════════════════════════════════════════════════════════════
# Portfolio History
# ═══════════════════════════════════════════════════════════════════

def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))


def save_history(history: list[dict]):
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def record_snapshot(value: float, cash: float, positions: list[dict]) -> dict:
    """Record a portfolio snapshot."""
    history = load_history()
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_value": round(value, 2),
        "cash": round(cash, 2),
        "invested": round(value - cash, 2),
        "positions_count": len(positions),
        "positions": [
            {
                "ticker": p.get("ticker", "?"),
                "value": round(
                    abs(p.get("quantity", 0) * p.get("currentPrice", 0)), 2
                ),
                "pnl_pct": round(p.get("resultPct", 0), 2),
            }
            for p in positions
        ],
    }
    history.append(snapshot)
    save_history(history)
    return snapshot


# ═══════════════════════════════════════════════════════════════════
# Drawdown Calculation
# ═══════════════════════════════════════════════════════════════════

def calculate_drawdown(history: list[dict]) -> dict:
    """Calculate current and max drawdown from history."""
    if not history:
        return {
            "current_value": 0,
            "peak_value": 0,
            "current_drawdown_pct": 0,
            "max_drawdown_pct": 0,
            "max_dd_date": None,
            "peak_date": None,
            "days_since_peak": 0,
        }

    values = [(h["timestamp"], h["total_value"]) for h in history]

    peak = 0
    peak_date = values[0][0]
    max_dd = 0
    max_dd_date = None
    current_value = values[-1][1]

    for ts, val in values:
        if val > peak:
            peak = val
            peak_date = ts
        dd = ((val - peak) / peak) * 100 if peak > 0 else 0
        if dd < max_dd:
            max_dd = dd
            max_dd_date = ts

    current_dd = ((current_value - peak) / peak) * 100 if peak > 0 else 0

    # Days since peak
    try:
        peak_dt = datetime.fromisoformat(peak_date.replace("Z", "+00:00"))
        days_since = (datetime.now(timezone.utc) - peak_dt).days
    except Exception:
        days_since = 0

    return {
        "current_value": current_value,
        "peak_value": round(peak, 2),
        "current_drawdown_pct": round(current_dd, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "max_dd_date": max_dd_date,
        "peak_date": peak_date,
        "days_since_peak": days_since,
    }


# ═══════════════════════════════════════════════════════════════════
# Kill Switch
# ═══════════════════════════════════════════════════════════════════

def is_kill_switch_active() -> bool:
    return KILL_SWITCH_FILE.exists()


def activate_kill_switch(reason: str):
    KILL_SWITCH_FILE.write_text(
        json.dumps({
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }),
        encoding="utf-8",
    )


def deactivate_kill_switch():
    if KILL_SWITCH_FILE.exists():
        KILL_SWITCH_FILE.unlink()


def check_drawdown_limit(max_drawdown_pct: float = -20.0) -> bool:
    """
    Check if drawdown exceeds limit.
    Returns True if SAFE, False if BREACHED.
    """
    history = load_history()
    if not history:
        return True  # no data yet, safe

    dd = calculate_drawdown(history)

    if dd["max_drawdown_pct"] <= max_drawdown_pct:
        reason = (
            f"Max drawdown {dd['max_drawdown_pct']:.1f}% breached "
            f"limit of {max_drawdown_pct}%"
        )
        activate_kill_switch(reason)
        return False

    if dd["current_drawdown_pct"] <= max_drawdown_pct:
        reason = (
            f"Current drawdown {dd['current_drawdown_pct']:.1f}% breached "
            f"limit of {max_drawdown_pct}%"
        )
        activate_kill_switch(reason)
        return False

    return True


# ═══════════════════════════════════════════════════════════════════
# Reports
# ═══════════════════════════════════════════════════════════════════

def get_period_performance(days: int) -> dict:
    """Performance over last N days."""
    history = load_history()
    if not history:
        return {"error": "No history data"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = [
        h for h in history
        if datetime.fromisoformat(
            h["timestamp"].replace("Z", "+00:00")
        ) >= cutoff
    ]

    if not filtered:
        return {"error": f"No data in last {days} days"}

    start_val = filtered[0]["total_value"]
    end_val = filtered[-1]["total_value"]
    change = end_val - start_val
    change_pct = (change / start_val) * 100 if start_val > 0 else 0

    return {
        "period_days": days,
        "start_value": round(start_val, 2),
        "end_value": round(end_val, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "snapshots": len(filtered),
    }


def print_daily_report():
    """Print daily performance report."""
    perf = get_period_performance(1)
    dd = calculate_drawdown(load_history())
    trades = _load_trades_summary(1)

    print("\n" + "=" * 60)
    print("  DAILY REPORT - " + datetime.now().strftime("%Y-%m-%d"))
    print("=" * 60)

    if "error" in perf:
        print(f"  {perf['error']}")
    else:
        arrow = "+" if perf["change"] >= 0 else ""
        print(f"\n  Portfolio: ${perf['end_value']:,.2f}")
        print(f"  Day Change: {arrow}${perf['change']:,.2f} ({arrow}{perf['change_pct']:.2f}%)")

    print(f"\n  Peak Value: ${dd['peak_value']:,.2f}")
    print(f"  Current Drawdown: {dd['current_drawdown_pct']:.2f}%")
    print(f"  Max Drawdown: {dd['max_drawdown_pct']:.2f}%")
    print(f"  Days Since Peak: {dd['days_since_peak']}")

    if trades:
        print(f"\n  Trades Today: {trades['executed']} executed, {trades['rejected']} rejected")
        for sleeve, count in trades["by_sleeve"].items():
            if count > 0:
                print(f"    {sleeve}: {count} trades")

    # Drawdown warning
    if dd["current_drawdown_pct"] <= -15:
        print("\n  [!!!] WARNING: Drawdown approaching -20% kill switch!")
    elif dd["current_drawdown_pct"] <= -10:
        print("\n  [!] CAUTION: Drawdown at -10%+")

    if is_kill_switch_active():
        print("\n  [XXX] KILL SWITCH IS ACTIVE — TRADING HALTED")
        data = json.loads(KILL_SWITCH_FILE.read_text())
        print(f"  Reason: {data.get('reason', 'Unknown')}")
        print(f"  Activated: {data.get('activated_at', '?')}")

    print("=" * 60 + "\n")


def print_weekly_report():
    """Print weekly performance report."""
    perf = get_period_performance(7)
    dd = calculate_drawdown(load_history())
    trades = _load_trades_summary(7)

    print("\n" + "=" * 60)
    print("  WEEKLY REPORT - Week ending " + datetime.now().strftime("%Y-%m-%d"))
    print("=" * 60)

    if "error" in perf:
        print(f"  {perf['error']}")
    else:
        arrow = "+" if perf["change"] >= 0 else ""
        print(f"\n  Portfolio: ${perf['end_value']:,.2f}")
        print(f"  Week Change: {arrow}${perf['change']:,.2f} ({arrow}{perf['change_pct']:.2f}%)")
        print(f"  Snapshots: {perf['snapshots']}")

    print(f"\n  All-Time Peak: ${dd['peak_value']:,.2f}")
    print(f"  Current Drawdown: {dd['current_drawdown_pct']:.2f}%")
    print(f"  Max Drawdown: {dd['max_drawdown_pct']:.2f}%")

    if trades:
        print(f"\n  Weekly Trades: {trades['executed']} executed, {trades['rejected']} rejected")

    # Go-live readiness check
    history = load_history()
    if history:
        first_dt = datetime.fromisoformat(
            history[0]["timestamp"].replace("Z", "+00:00")
        )
        days_running = (datetime.now(timezone.utc) - first_dt).days
        print(f"\n  Days Running: {days_running}")
        print(f"  Go-Live Requires: 30 days paper + max DD > -20%")
        if days_running >= 30 and dd["max_drawdown_pct"] > -20:
            print("  Status: [READY] Meets go-live criteria")
        elif days_running < 30:
            print(f"  Status: [WAIT] Need {30 - days_running} more days of paper testing")
        else:
            print("  Status: [BLOCKED] Drawdown exceeded -20%")

    print("=" * 60 + "\n")


def _load_trades_summary(days: int) -> dict:
    """Quick trade count from trades.json."""
    trades_file = Path("trades.json")
    if not trades_file.exists():
        return {}
    try:
        trades = json.loads(trades_file.read_text(encoding="utf-8"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = []
        for t in trades:
            try:
                ts = datetime.fromisoformat(
                    t.get("timestamp", "").replace("Z", "+00:00")
                )
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    recent.append(t)
            except Exception:
                continue

        executed = sum(1 for t in recent if t.get("status") == "EXECUTED")
        rejected = sum(1 for t in recent if t.get("status") == "REJECTED")
        by_sleeve = {}
        for t in recent:
            if t.get("status") == "EXECUTED":
                s = t.get("sleeve", "unknown")
                by_sleeve[s] = by_sleeve.get(s, 0) + 1

        return {"executed": executed, "rejected": rejected, "by_sleeve": by_sleeve}
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════
# Show Status
# ═══════════════════════════════════════════════════════════════════

def show_status():
    """Full current status display."""
    from config import TradingConfig
    from alpaca_client import AlpacaClient

    config = TradingConfig()
    client = AlpacaClient(config)

    cash_info = client.get_account_cash()
    positions = client.get_positions()
    cash = cash_info.get("free", 0)
    total = cash_info.get("total", cash)

    # Record snapshot
    snapshot = record_snapshot(total, cash, positions)

    # Calculate drawdown
    dd = calculate_drawdown(load_history())
    split = config.get_dynamic_split(total)

    print("\n" + "=" * 60)
    print("  PORTFOLIO MONITOR")
    print("=" * 60)

    env = "PAPER" if config.ALPACA_ENV == "paper" else "LIVE"
    print(f"\n  Broker: {config.BROKER.upper()} ({env})")
    print(f"  Total Value: ${total:,.2f}")
    print(f"  Cash: ${cash:,.2f}")
    print(
        f"  Allocation: Short {split['short_term']:.0f}% / "
        f"Mid {split['mid_term']:.0f}% / Long {split['long_term']:.0f}%"
    )

    print(f"\n  -- Drawdown Tracker --")
    print(f"  Peak Value: ${dd['peak_value']:,.2f}")
    print(f"  Current Drawdown: {dd['current_drawdown_pct']:.2f}%")
    print(f"  Max Drawdown: {dd['max_drawdown_pct']:.2f}%")
    print(f"  Days Since Peak: {dd['days_since_peak']}")

    # Drawdown bar
    dd_pct = abs(dd["current_drawdown_pct"])
    bar_len = int(min(dd_pct, 25))
    bar = "#" * bar_len + "-" * (25 - bar_len)
    limit_pos = int(20)  # -20% position
    bar_list = list(bar)
    if limit_pos < len(bar_list):
        bar_list[limit_pos] = "|"
    print(f"  Drawdown: [{''.join(bar_list)}] -20% limit")

    if dd["current_drawdown_pct"] <= -15:
        print("  [!!!] DANGER: Approaching -20% kill switch!")
    elif dd["current_drawdown_pct"] <= -10:
        print("  [!] CAUTION: Significant drawdown")
    elif dd["current_drawdown_pct"] <= -5:
        print("  [~] Moderate drawdown -- monitoring")
    else:
        print("  [OK] Drawdown within safe range")

    if positions:
        print(f"\n  -- Positions ({len(positions)}) --")

        # Group by sleeve (approximation)
        etf_tickers = set(config.LONG_TERM_ETF_TARGETS.keys())
        for p in sorted(positions, key=lambda x: x.get("ticker", "")):
            ticker = config.get_plain_symbol(p.get("ticker", ""))
            qty = p.get("quantity", 0)
            avg = p.get("averagePrice", 0)
            cur = p.get("currentPrice", 0)
            pnl_pct = p.get("resultPct", 0)
            value = abs(qty * cur)
            sleeve = "ETF" if ticker in etf_tickers else "Active"
            arrow = "+" if pnl_pct >= 0 else ""
            print(
                f"  {sleeve:>6} | {ticker:<6} {qty:>8.2f} sh | "
                f"${avg:>8.2f} -> ${cur:>8.2f} | "
                f"{arrow}{pnl_pct:.1f}% | ${value:>10,.2f}"
            )

    if is_kill_switch_active():
        print("\n  [XXX] KILL SWITCH IS ACTIVE — TRADING HALTED")
        data = json.loads(KILL_SWITCH_FILE.read_text())
        print(f"  Reason: {data.get('reason', 'Unknown')}")

    print("=" * 60 + "\n")


def show_history():
    """Show equity curve from history."""
    history = load_history()
    if not history:
        print("No history yet. Run 'python monitor.py --check' first.")
        return

    print("\n" + "=" * 60)
    print("  EQUITY CURVE")
    print("=" * 60)
    print(f"  {'Date':<20} {'Value':>12} {'Change':>10} {'DD%':>8}")
    print("  " + "-" * 52)

    prev_val = None
    for h in history[-30:]:  # last 30 snapshots
        ts = h["timestamp"][:16].replace("T", " ")
        val = h["total_value"]
        change = ""
        if prev_val:
            diff = val - prev_val
            sign = "+" if diff >= 0 else ""
            change = f"{sign}${diff:,.2f}"
        prev_val = val

        # Calculate DD at this point
        dd = calculate_drawdown(
            [x for x in history if x["timestamp"] <= h["timestamp"]]
        )
        print(
            f"  {ts:<20} ${val:>10,.2f} {change:>10} "
            f"{dd['current_drawdown_pct']:>7.2f}%"
        )

    print("=" * 60 + "\n")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Portfolio Monitor & Drawdown Tracker")
    ap.add_argument("--check", action="store_true", help="Record snapshot + check drawdown")
    ap.add_argument("--report", choices=["daily", "weekly"], help="Generate report")
    ap.add_argument("--history", action="store_true", help="Show equity curve")
    ap.add_argument("--reset", action="store_true", help="Reset history")
    ap.add_argument("--unlock", action="store_true", help="Deactivate kill switch")
    args = ap.parse_args()

    if args.reset:
        confirm = input("Reset all portfolio history? (type RESET): ").strip()
        if confirm == "RESET":
            if HISTORY_FILE.exists():
                HISTORY_FILE.unlink()
            if KILL_SWITCH_FILE.exists():
                KILL_SWITCH_FILE.unlink()
            print("History cleared.")
        else:
            print("Cancelled.")
        return

    if args.unlock:
        if is_kill_switch_active():
            confirm = input(
                "This removes the safety kill switch. Are you sure? (type UNLOCK): "
            ).strip()
            if confirm == "UNLOCK":
                deactivate_kill_switch()
                print("Kill switch deactivated. Trading will resume.")
            else:
                print("Cancelled.")
        else:
            print("Kill switch is not active.")
        return

    if args.check:
        # Record snapshot and check drawdown
        from config import TradingConfig
        from alpaca_client import AlpacaClient
        config = TradingConfig()
        client = AlpacaClient(config)
        cash_info = client.get_account_cash()
        positions = client.get_positions()
        cash = cash_info.get("free", 0)
        total = cash_info.get("total", cash)

        record_snapshot(total, cash, positions)
        safe = check_drawdown_limit(-20.0)

        dd = calculate_drawdown(load_history())
        print(f"Snapshot recorded: ${total:,.2f} (DD: {dd['current_drawdown_pct']:.2f}%)")
        if not safe:
            print("[XXX] KILL SWITCH ACTIVATED — drawdown exceeded -20%!")
        return

    if args.report == "daily":
        print_daily_report()
        return

    if args.report == "weekly":
        print_weekly_report()
        return

    if args.history:
        show_history()
        return

    # Default: show full status
    show_status()


if __name__ == "__main__":
    main()
