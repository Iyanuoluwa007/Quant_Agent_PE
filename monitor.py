"""
Portfolio Monitor (Sanitized Demo)
Tracks portfolio value over time, calculates drawdown, and generates
daily/weekly summaries. All trading logic and thresholds are disabled.

Usage:
  python monitor.py                  # Show current status (demo data)
  python monitor.py --check          # Record snapshot (dummy) + check drawdown
  python monitor.py --report daily   # Daily performance report
  python monitor.py --report weekly  # Weekly performance report
  python monitor.py --history        # Show equity curve
  python monitor.py --reset          # Clear history
"""
import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
import random

SCRIPT_DIR = str(Path(__file__).parent.resolve())
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

HISTORY_FILE = Path("portfolio_history.json")

# ──────────────────────────────────────────────────────────────
# Portfolio History
# ──────────────────────────────────────────────────────────────

def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

def save_history(history: list[dict]):
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")

def record_snapshot(value: float, cash: float, positions: list[dict]) -> dict:
    """Record a portfolio snapshot (demo data)."""
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
                "value": round(abs(p.get("quantity", 0) * p.get("currentPrice", 0)), 2),
                "pnl_pct": round(p.get("resultPct", 0), 2),
            }
            for p in positions
        ],
    }
    history.append(snapshot)
    save_history(history)
    return snapshot

# ──────────────────────────────────────────────────────────────
# Drawdown Calculation
# ──────────────────────────────────────────────────────────────

def calculate_drawdown(history: list[dict]) -> dict:
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

# ──────────────────────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────────────────────

def get_period_performance(days: int) -> dict:
    history = load_history()
    if not history:
        return {"error": "No history data"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = [h for h in history if datetime.fromisoformat(h["timestamp"].replace("Z","+00:00")) >= cutoff]

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
    perf = get_period_performance(1)
    dd = calculate_drawdown(load_history())
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
    print("=" * 60 + "\n")

def print_weekly_report():
    perf = get_period_performance(7)
    dd = calculate_drawdown(load_history())
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
    print("=" * 60 + "\n")

# ──────────────────────────────────────────────────────────────
# Demo Status
# ──────────────────────────────────────────────────────────────

def show_status():
    """Show demo portfolio status."""
    # Dummy data
    total = round(random.uniform(500, 1000), 2)
    cash = round(total * random.uniform(0.2,0.5),2)
    positions = [
        {"ticker":"DEMO1","quantity":10,"currentPrice":50,"resultPct":5},
        {"ticker":"DEMO2","quantity":5,"currentPrice":80,"resultPct":-3},
    ]
    record_snapshot(total, cash, positions)
    dd = calculate_drawdown(load_history())

    print("\n" + "=" * 60)
    print("  PORTFOLIO MONITOR (DEMO)")
    print("=" * 60)
    print(f"\n  Broker: SIMULATED_BROKER (PAPER)")
    print(f"  Total Value: ${total:,.2f}")
    print(f"  Cash: ${cash:,.2f}")
    print(f"\n  -- Drawdown Tracker --")
    print(f"  Peak Value: ${dd['peak_value']:,.2f}")
    print(f"  Current Drawdown: {dd['current_drawdown_pct']:.2f}%")
    print(f"  Max Drawdown: {dd['max_drawdown_pct']:.2f}%")
    print(f"  Days Since Peak: {dd['days_since_peak']}")
    print("=" * 60 + "\n")

def show_history():
    """Show demo equity curve."""
    history = load_history()
    if not history:
        print("No history yet. Run '--check' first.")
        return
    print("\n" + "=" * 60)
    print("  EQUITY CURVE (DEMO)")
    print("=" * 60)
    for h in history[-30:]:
        ts = h["timestamp"][:16].replace("T"," ")
        print(f"  {ts} | ${h['total_value']:,.2f}")
    print("=" * 60 + "\n")

# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Portfolio Monitor (Demo)")
    ap.add_argument("--check", action="store_true", help="Record demo snapshot")
    ap.add_argument("--report", choices=["daily","weekly"], help="Generate report")
    ap.add_argument("--history", action="store_true", help="Show equity curve")
    ap.add_argument("--reset", action="store_true", help="Reset history")
    args = ap.parse_args()

    if args.reset:
        confirm = input("Reset all portfolio history? (type RESET): ").strip()
        if confirm == "RESET" and HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
            print("History cleared.")
        return

    if args.check:
        # Record dummy snapshot
        total = round(random.uniform(500,1000),2)
        cash = round(total*random.uniform(0.2,0.5),2)
        positions = [
            {"ticker":"DEMO1","quantity":10,"currentPrice":50,"resultPct":5},
            {"ticker":"DEMO2","quantity":5,"currentPrice":80,"resultPct":-3},
        ]
        snapshot = record_snapshot(total, cash, positions)
        dd = calculate_drawdown(load_history())
        print(f"Snapshot recorded: ${snapshot['total_value']:,.2f} (DD: {dd['current_drawdown_pct']:.2f}%)")
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

    show_status()

if __name__ == "__main__":
    main()