#!/usr/bin/env python3
"""
Pre-Launch Verification Script
Run this BEFORE deploying to Hetzner or pushing to GitHub.

Usage:
    python preflight.py           # Full check
    python preflight.py --quick   # Skip network tests
    python preflight.py --reset   # Reset all state for fresh start
"""
import sys
import os
import json
import argparse
import importlib
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).parent.resolve()
os.chdir(SCRIPT_DIR)
sys.path.insert(0, str(SCRIPT_DIR))

# ── Colors ────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0
warnings = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  {RED}[FAIL]{RESET} {msg}")


def warn(msg):
    global warnings
    warnings += 1
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def section(title):
    print(f"\n{BOLD}--- {title} ---{RESET}")


# ═══════════════════════════════════════════════════════════════════
# 1. FILE STRUCTURE
# ═══════════════════════════════════════════════════════════════════

def check_files():
    section("File Structure")

    required = [
        "agent.py", "config.py", "run.py", "broker_adapter.py",
        "screener.py", "market_data.py", "monitor.py",
        "etf_review.py", "notifications.py", "virtual_capital.py",
        "api_server.py", "dashboard_cli.py",
        ".env.example", ".gitignore", "README.md", "requirements.txt",
        "risk/__init__.py", "risk/global_risk.py", "risk/position_sizing.py",
        "risk/regime_detection.py", "risk/volatility_target.py", "risk/beta_control.py",
        "intelligence/__init__.py", "intelligence/calibration.py",
        "intelligence/meta_model.py", "intelligence/accuracy_tracker.py",
        "strategies/__init__.py", "strategies/short_term.py",
        "strategies/mid_term.py", "strategies/long_term.py",
        "quant/__init__.py", "quant/backtester.py",
        "tests/test_risk_and_intelligence.py",
        "dashboard/package.json", "dashboard/app/page.tsx",
        "dashboard/public/demo_data.json", "dashboard/vercel.json",
    ]

    for f in required:
        if Path(f).exists():
            ok(f)
        else:
            fail(f"Missing: {f}")


# ═══════════════════════════════════════════════════════════════════
# 2. SECRETS CHECK
# ═══════════════════════════════════════════════════════════════════

def check_secrets():
    section("Secrets & Safety")

    # .env should NOT be committed
    if Path(".env").exists():
        warn(".env file exists (make sure it is in .gitignore)")
    else:
        ok("No .env file found (will use .env.example)")

    # Check .gitignore catches .env
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    if ".env" in gitignore and "!.env.example" in gitignore:
        ok(".gitignore protects .env, allows .env.example")
    else:
        fail(".gitignore missing .env protection")

    # Scan Python files for hardcoded secrets
    secret_patterns = [
        "sk-ant-", "PACA", "Bearer ", "password",
        "smtp.gmail", "-----BEGIN",
    ]
    suspect_files = []
    for pyfile in Path(".").rglob("*.py"):
        if "__pycache__" in str(pyfile) or "preflight.py" in str(pyfile):
            continue
        content = pyfile.read_text(encoding="utf-8", errors="ignore")
        for pattern in secret_patterns:
            if pattern in content:
                # Allow patterns in env reading code and comments
                lines = [
                    l.strip() for l in content.split("\n")
                    if pattern in l
                    and not l.strip().startswith("#")
                    and "os.getenv" not in l
                    and "os.environ" not in l
                    and "getenv" not in l
                    and ".env" not in l
                    and 'example' in str(pyfile).lower()
                ]
                if lines:
                    suspect_files.append((str(pyfile), pattern))

    if not suspect_files:
        ok("No hardcoded secrets found in Python files")
    else:
        for f, p in suspect_files:
            fail(f"Possible secret in {f}: pattern '{p}'")

    # Check demo_data.json has no real account info
    demo = Path("dashboard/public/demo_data.json")
    if demo.exists():
        data = json.loads(demo.read_text())
        if data.get("meta", {}).get("mode") == "Simulated":
            ok("demo_data.json marked as Simulated")
        else:
            warn("demo_data.json not marked as Simulated")
    else:
        warn("demo_data.json not found")


# ═══════════════════════════════════════════════════════════════════
# 3. CONFIG VALIDATION
# ═══════════════════════════════════════════════════════════════════

def check_config():
    section("Configuration")

    try:
        from config import TradingConfig
        config = TradingConfig()
        ok(f"Config loaded: BROKER={config.BROKER}")

        # Check virtual capital
        if config.VIRTUAL_CAPITAL_ENABLED:
            ok(f"Virtual capital: {config.CURRENCY_SYMBOL}{config.VIRTUAL_INITIAL_CAPITAL:,.0f} + {config.CURRENCY_SYMBOL}{config.VIRTUAL_MONTHLY_DEPOSIT:,.0f}/mo")
        else:
            warn("Virtual capital disabled")

        # Check market hours
        if config.MARKET_HOURS_ONLY:
            ok("Market hours gate: ON")
        else:
            warn("Market hours gate: OFF (will run during closed hours)")

        # Validate
        config.ANTHROPIC_API_KEY = config.ANTHROPIC_API_KEY or "test"
        errors = config.validate()
        if not errors:
            ok("Config validates with no errors")
        else:
            for e in errors:
                fail(f"Config error: {e}")

    except Exception as e:
        fail(f"Config import failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# 4. MODULE IMPORTS
# ═══════════════════════════════════════════════════════════════════

def check_imports():
    section("Module Imports")

    modules = [
        ("config", "TradingConfig"),
        ("broker_adapter", "BrokerAdapter"),
        ("virtual_capital", "VirtualCapitalManager"),
        ("etf_review", "ETFReviewEngine"),
        ("notifications", "EmailNotifier"),
        ("risk.global_risk", "GlobalRiskManager"),
        ("risk.position_sizing", "calculate_position_size"),
        ("risk.regime_detection", "RegimeDetector"),
        ("risk.volatility_target", "VolatilityTargeter"),
        ("risk.beta_control", "BetaController"),
        ("intelligence.calibration", "CalibrationTracker"),
        ("intelligence.meta_model", "MetaModel"),
        ("intelligence.accuracy_tracker", "AccuracyTracker"),
        ("quant.backtester", "BacktestEngine"),
    ]

    for mod_name, class_name in modules:
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, class_name):
                ok(f"{mod_name}.{class_name}")
            else:
                fail(f"{mod_name} loaded but missing {class_name}")
        except Exception as e:
            fail(f"{mod_name}: {e}")


# ═══════════════════════════════════════════════════════════════════
# 5. BROKER ADAPTER
# ═══════════════════════════════════════════════════════════════════

def check_broker():
    section("Broker Adapter (Simulated)")

    try:
        from config import TradingConfig
        from broker_adapter import BrokerAdapter, SIMULATED_STATE_FILE

        # Clean state for test
        SIMULATED_STATE_FILE.unlink(missing_ok=True)

        config = TradingConfig()
        config.BROKER = "simulated"
        config.INITIAL_CAPITAL = 50000
        broker = BrokerAdapter(config)

        # Cash
        cash = broker.get_account_cash()
        assert cash["free"] == 50000, f"Expected 50000, got {cash['free']}"
        ok(f"Initial cash: ${cash['free']:,.2f}")

        # Market clock
        clock = broker.get_market_clock()
        assert "is_open" in clock
        ok(f"Market clock: is_open={clock['is_open']}")

        # Positions
        pos = broker.get_positions()
        assert pos == []
        ok("Empty positions on fresh state")

        # Reset
        broker.reset(100000)
        cash = broker.get_account_cash()
        assert cash["free"] == 100000
        ok("Reset to $100,000")

        # Cleanup
        SIMULATED_STATE_FILE.unlink(missing_ok=True)

    except Exception as e:
        fail(f"Broker test failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# 6. VIRTUAL CAPITAL
# ═══════════════════════════════════════════════════════════════════

def check_virtual_capital():
    section("Virtual Capital Manager")

    try:
        from virtual_capital import VirtualCapitalManager, STATE_FILE

        STATE_FILE.unlink(missing_ok=True)
        vcm = VirtualCapitalManager(
            initial_capital=12500, monthly_deposit=625,
            currency="USD", currency_symbol="$",
        )

        # Initial state
        assert vcm.get_virtual_cash() == 12500
        ok("Initial: $12,500")

        # Buy
        assert vcm.record_buy("NVDA", 10, 125.0, sleeve="mid_term")
        assert vcm.get_virtual_cash() == 11250
        ok("Buy 10 NVDA @ $125 -> cash $11,250")

        # Sell
        assert vcm.record_sell("NVDA", 5, 130.0)
        assert vcm.get_virtual_cash() == 11250 + 650
        ok("Sell 5 NVDA @ $130 -> cash $11,900")

        # Deposit
        vcm.deposit(625, "monthly")
        assert vcm.get_total_deposited() == 13125
        ok("Monthly deposit: total deposited $13,125")

        # Agent interface
        info = vcm.get_account_cash_for_agent()
        assert "free" in info and "total" in info
        ok("Agent interface compatible")

        # Cleanup
        STATE_FILE.unlink(missing_ok=True)

    except Exception as e:
        fail(f"Virtual capital test failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# 7. RISK ENGINE
# ═══════════════════════════════════════════════════════════════════

def check_risk():
    section("Risk Engine")

    try:
        from config import TradingConfig
        from risk.global_risk import GlobalRiskManager, TradeProposal, RiskCheckResult

        config = TradingConfig()
        rm = GlobalRiskManager(config)

        # Basic approval
        proposal = TradeProposal(
            ticker="AAPL", action="BUY", quantity=5,
            sleeve="mid_term", confidence=0.75,
            order_type="limit",
            limit_price=150.0, stop_loss=145.0, take_profit=165.0,
            reasoning="Test trade",
        )
        result = rm.check_trade(
            proposal=proposal,
            account_cash=50000,
            total_portfolio_value=100000,
            all_positions=[],
            pending_tickers=set(),
        )
        if result.approved:
            ok("Basic BUY proposal: approved")
        else:
            warn(f"Basic BUY proposal rejected: {result.rejection_reasons}")

        # Low confidence rejection
        low_conf = TradeProposal(
            ticker="COIN", action="BUY", quantity=10,
            sleeve="short_term", confidence=0.10,
            order_type="market",
            reasoning="Test low confidence",
        )
        result = rm.check_trade(
            proposal=low_conf,
            account_cash=50000,
            total_portfolio_value=100000,
            all_positions=[],
            pending_tickers=set(),
        )
        if not result.approved:
            ok("Low confidence (10%): correctly rejected")
        else:
            fail("Low confidence should be rejected")

    except Exception as e:
        fail(f"Risk engine test failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# 8. TESTS
# ═══════════════════════════════════════════════════════════════════

def check_tests():
    section("Test Suite")

    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        capture_output=True, text=True, cwd=str(SCRIPT_DIR),
    )

    # Parse output
    output = result.stdout.strip()
    last_line = output.split("\n")[-1] if output else ""

    if "passed" in last_line and "failed" not in last_line:
        ok(last_line)
    elif "failed" in last_line:
        fail(last_line)
        # Show failures
        for line in output.split("\n"):
            if "FAILED" in line:
                print(f"    {RED}{line.strip()}{RESET}")
    else:
        fail(f"Unexpected test output: {last_line}")


# ═══════════════════════════════════════════════════════════════════
# 9. DASHBOARD
# ═══════════════════════════════════════════════════════════════════

def check_dashboard():
    section("Dashboard")

    demo = Path("dashboard/public/demo_data.json")
    if demo.exists():
        data = json.loads(demo.read_text())
        sections = ["meta", "performance", "positions", "recent_trades", "risk", "intelligence", "etf_review"]
        for s in sections:
            if s in data:
                ok(f"demo_data.json has '{s}'")
            else:
                fail(f"demo_data.json missing '{s}'")
    else:
        fail("dashboard/public/demo_data.json not found")

    pkg = Path("dashboard/package.json")
    if pkg.exists():
        ok("dashboard/package.json exists")
    else:
        fail("dashboard/package.json missing")

    vercel = Path("dashboard/vercel.json")
    if vercel.exists():
        ok("dashboard/vercel.json exists")
    else:
        warn("dashboard/vercel.json missing (needed for Vercel deploy)")


# ═══════════════════════════════════════════════════════════════════
# 10. NETWORK (optional)
# ═══════════════════════════════════════════════════════════════════

def check_network():
    section("Network (API Connectivity)")

    # yfinance
    try:
        import yfinance as yf
        ticker = yf.Ticker("SPY")
        hist = ticker.history(period="5d")
        if not hist.empty:
            price = round(float(hist["Close"].iloc[-1]), 2)
            ok(f"yfinance: SPY = ${price}")
        else:
            fail("yfinance returned empty data")
    except Exception as e:
        fail(f"yfinance: {e}")

    # Anthropic (only if key present)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key and not api_key.startswith("your_"):
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=10,
                messages=[{"role": "user", "content": "Reply with just OK"}],
            )
            ok("Anthropic API: connected")
        except Exception as e:
            fail(f"Anthropic API: {e}")
    else:
        warn("Anthropic API: no key set (skipping)")

    # Alpaca (only if configured)
    alpaca_key = os.getenv("ALPACA_API_KEY", "")
    if alpaca_key and not alpaca_key.startswith("your_"):
        try:
            import requests
            env = os.getenv("ALPACA_ENV", "paper")
            base = "https://paper-api.alpaca.markets" if env == "paper" else "https://api.alpaca.markets"
            r = requests.get(
                f"{base}/v2/account",
                headers={
                    "APCA-API-KEY-ID": alpaca_key,
                    "APCA-API-SECRET-KEY": os.getenv("ALPACA_API_SECRET", ""),
                },
                timeout=10,
            )
            if r.status_code == 200:
                acct = r.json()
                ok(f"Alpaca ({env}): ${float(acct['portfolio_value']):,.2f}")
            else:
                fail(f"Alpaca: HTTP {r.status_code}")
        except Exception as e:
            fail(f"Alpaca: {e}")
    else:
        warn("Alpaca API: no key set (skipping)")


# ═══════════════════════════════════════════════════════════════════
# RESET (delete all state for fresh start)
# ═══════════════════════════════════════════════════════════════════

def reset_all_state():
    section("Resetting All State")

    state_files = [
        "trades.json",
        "virtual_capital.json",
        "simulated_broker_state.json",
        "calibration_data.json",
        "accuracy_data.json",
        "accuracy_log.json",
        "portfolio_history.json",
        "equity_curve.json",
        "etf_review_history.json",
        "etf_review_pending.json",
        "etf_overrides.json",
        "etf_sell_queue.json",
        ".kill_switch",
        ".last_daily_summary",
        "trading_agent.log",
    ]

    deleted = 0
    for f in state_files:
        p = Path(f)
        if p.exists():
            p.unlink()
            print(f"  {RED}[DEL]{RESET} {f}")
            deleted += 1

    if deleted == 0:
        ok("No state files to delete (already clean)")
    else:
        ok(f"Deleted {deleted} state files")

    # Recreate virtual capital with fresh state
    print()
    print(f"  {DIM}State is clean. Next run will initialize fresh.{RESET}")
    print(f"  {DIM}Start date can be set by running the agent after the 23rd.{RESET}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Pre-Launch Verification")
    ap.add_argument("--quick", action="store_true", help="Skip network tests")
    ap.add_argument("--reset", action="store_true", help="Delete all state for fresh start")
    args = ap.parse_args()

    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv(SCRIPT_DIR / ".env")
    except ImportError:
        pass

    print(f"\n{BOLD}{'=' * 52}")
    print(f"  Quant Agent v2.1 -- Pre-Launch Verification")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'=' * 52}{RESET}")

    if args.reset:
        reset_all_state()
        print(f"\n{BOLD}{'=' * 52}{RESET}")
        print(f"  Reset complete. Run {BOLD}python preflight.py{RESET} to verify.")
        print(f"{BOLD}{'=' * 52}{RESET}\n")
        return

    check_files()
    check_secrets()
    check_config()
    check_imports()
    check_broker()
    check_virtual_capital()
    check_risk()
    check_tests()
    check_dashboard()

    if not args.quick:
        check_network()

    # Summary
    print(f"\n{BOLD}{'=' * 52}")
    total = passed + failed + warnings
    print(f"  Results: {GREEN}{passed} passed{RESET}, ", end="")
    if failed:
        print(f"{RED}{failed} failed{RESET}, ", end="")
    else:
        print(f"{DIM}0 failed{RESET}, ", end="")
    print(f"{YELLOW}{warnings} warnings{RESET}")

    if failed == 0:
        print(f"\n  {GREEN}{BOLD}[READY] All checks passed. Safe to deploy.{RESET}")
    else:
        print(f"\n  {RED}{BOLD}[NOT READY] Fix {failed} failure(s) before deploying.{RESET}")
    print(f"{'=' * 52}{RESET}\n")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
