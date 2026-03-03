"""
Virtual Capital Manager
Tracks the agent's allocated capital within a larger broker account.

Problem:
  Alpaca paper account has $20,000, but the agent is only allocated
  $12,500 initially + $625/month deposits. The agent must only trade
  with its virtual allocation, not the full broker balance.

How it works:
  1. On first run, initializes with VIRTUAL_INITIAL_CAPITAL
  2. Tracks all deposits (initial + monthly DCA)
  3. Tracks positions bought/sold by the agent
  4. Agent uses virtual cash for all sizing decisions
  5. Monthly deposit auto-credited on configurable day

State file: virtual_capital.json
  {
    "initial_deposit": 12500.0,
    "monthly_deposit": 625.0,
    "deposits": [
      {"date": "2025-09-01", "amount": 12500.0, "type": "initial"},
      {"date": "2025-10-01", "amount": 625.0, "type": "monthly"},
      ...
    ],
    "total_deposited": 13750.0,
    "virtual_cash": 4250.0,
    "positions": {
      "NVDA": {"quantity": 10, "avg_price": 125.0, "cost_basis": 1250.0},
      ...
    },
    "last_monthly_deposit": "2025-10-01",
    "created_at": "2025-09-01T00:00:00Z"
  }

Usage:
  python virtual_capital.py --status       # Show virtual portfolio
  python virtual_capital.py --deposit 625  # Manual deposit
  python virtual_capital.py --reset        # Reset to initial state
  python virtual_capital.py --history      # Deposit history
"""
import json
import sys
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = Path("virtual_capital.json")


class VirtualCapitalManager:
    """
    Tracks the agent's virtual allocation within a broker account.

    The broker account may have more capital than the agent is allowed
    to use. This manager enforces the virtual boundary.
    """

    def __init__(
        self,
        initial_capital: float = 12500.0,
        monthly_deposit: float = 625.0,
        deposit_day: int = 1,
        currency: str = "USD",
        currency_symbol: str = "$",
    ):
        self.initial_capital = initial_capital
        self.monthly_deposit = monthly_deposit
        self.deposit_day = deposit_day
        self.currency = currency
        self.currency_symbol = currency_symbol
        self._state = self._load()

    # ═══════════════════════════════════════════════════════════════
    # STATE
    # ═══════════════════════════════════════════════════════════════

    def _load(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self._initialize()

    def _initialize(self) -> dict:
        now = datetime.now(timezone.utc)
        state = {
            "initial_deposit": self.initial_capital,
            "monthly_deposit": self.monthly_deposit,
            "currency": self.currency,
            "deposits": [
                {
                    "date": now.strftime("%Y-%m-%d"),
                    "amount": self.initial_capital,
                    "type": "initial",
                }
            ],
            "total_deposited": self.initial_capital,
            "virtual_cash": self.initial_capital,
            "positions": {},
            "last_monthly_deposit": None,
            "created_at": now.isoformat(),
        }
        self._save(state)
        logger.info(
            f"[VCAP] Initialized: {self.currency_symbol}"
            f"{self.initial_capital:,.2f} initial"
        )
        return state

    def _save(self, state: dict = None):
        if state is None:
            state = self._state
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def reset(self):
        """Reset to initial state. Wipes all history."""
        STATE_FILE.unlink(missing_ok=True)
        self._state = self._initialize()
        logger.info("[VCAP] Reset to initial state")

    # ═══════════════════════════════════════════════════════════════
    # DEPOSITS
    # ═══════════════════════════════════════════════════════════════

    def check_monthly_deposit(self) -> Optional[float]:
        """
        Check if monthly deposit is due and credit it.
        Called each agent cycle. Returns deposit amount or None.
        """
        if self.monthly_deposit <= 0:
            return None

        now = datetime.now(timezone.utc)
        current_month = now.strftime("%Y-%m")
        last = self._state.get("last_monthly_deposit")

        # Already deposited this month?
        if last and last.startswith(current_month):
            return None

        # Is it deposit day or later?
        if now.day < self.deposit_day:
            return None

        return self.deposit(self.monthly_deposit, deposit_type="monthly")

    def deposit(self, amount: float, deposit_type: str = "manual") -> float:
        """Credit a deposit to virtual cash."""
        now = datetime.now(timezone.utc)
        self._state["deposits"].append({
            "date": now.strftime("%Y-%m-%d"),
            "amount": amount,
            "type": deposit_type,
        })
        self._state["total_deposited"] += amount
        self._state["virtual_cash"] += amount

        if deposit_type == "monthly":
            self._state["last_monthly_deposit"] = now.strftime("%Y-%m-%d")

        self._save()
        logger.info(
            f"[VCAP] Deposit: {self.currency_symbol}{amount:,.2f} "
            f"({deposit_type}) | Cash: {self.currency_symbol}"
            f"{self._state['virtual_cash']:,.2f}"
        )
        return amount

    # ═══════════════════════════════════════════════════════════════
    # TRADING
    # ═══════════════════════════════════════════════════════════════

    def record_buy(
        self, ticker: str, quantity: float,
        fill_price: float, sleeve: str = ""
    ) -> bool:
        """
        Record a buy. Deducts from virtual cash.
        Returns False if insufficient virtual cash.
        """
        cost = quantity * fill_price

        if cost > self._state["virtual_cash"] + 0.01:
            logger.warning(
                f"[VCAP] Insufficient virtual cash for "
                f"{ticker}: need {self.currency_symbol}{cost:,.2f}, "
                f"have {self.currency_symbol}{self._state['virtual_cash']:,.2f}"
            )
            return False

        self._state["virtual_cash"] -= cost

        pos = self._state["positions"].get(ticker, {
            "quantity": 0, "avg_price": 0, "cost_basis": 0, "sleeve": sleeve,
        })
        old_qty = pos["quantity"]
        old_basis = pos["cost_basis"]
        new_qty = old_qty + quantity
        new_basis = old_basis + cost
        new_avg = new_basis / new_qty if new_qty > 0 else 0

        pos.update({
            "quantity": round(new_qty, 6),
            "avg_price": round(new_avg, 4),
            "cost_basis": round(new_basis, 2),
            "sleeve": sleeve or pos.get("sleeve", ""),
        })
        self._state["positions"][ticker] = pos
        self._save()

        logger.info(
            f"[VCAP] BUY {quantity} {ticker} @ {self.currency_symbol}"
            f"{fill_price:.2f} | Cash: {self.currency_symbol}"
            f"{self._state['virtual_cash']:,.2f}"
        )
        return True

    def record_sell(
        self, ticker: str, quantity: float, fill_price: float
    ) -> bool:
        """
        Record a sell. Credits virtual cash.
        Returns False if position doesn't exist or insufficient quantity.
        """
        pos = self._state["positions"].get(ticker)
        if not pos or pos["quantity"] < quantity - 0.001:
            logger.warning(
                f"[VCAP] Cannot sell {quantity} {ticker}: "
                f"have {pos['quantity'] if pos else 0}"
            )
            return False

        proceeds = quantity * fill_price
        self._state["virtual_cash"] += proceeds

        # Update position
        sold_fraction = quantity / pos["quantity"]
        pos["cost_basis"] -= pos["cost_basis"] * sold_fraction
        pos["quantity"] = round(pos["quantity"] - quantity, 6)

        if pos["quantity"] <= 0.001:
            del self._state["positions"][ticker]
        else:
            pos["cost_basis"] = round(pos["cost_basis"], 2)
            self._state["positions"][ticker] = pos

        self._save()

        logger.info(
            f"[VCAP] SELL {quantity} {ticker} @ {self.currency_symbol}"
            f"{fill_price:.2f} | Cash: {self.currency_symbol}"
            f"{self._state['virtual_cash']:,.2f}"
        )
        return True

    # ═══════════════════════════════════════════════════════════════
    # QUERIES
    # ═══════════════════════════════════════════════════════════════

    def get_virtual_cash(self) -> float:
        """Available virtual cash for new trades."""
        return self._state["virtual_cash"]

    def get_total_deposited(self) -> float:
        """Total amount deposited (initial + all monthly)."""
        return self._state["total_deposited"]

    def get_positions(self) -> dict:
        """Virtual positions. {ticker: {quantity, avg_price, cost_basis, sleeve}}"""
        return dict(self._state.get("positions", {}))

    def get_invested_value(self, price_fn=None) -> float:
        """
        Total current value of positions.
        price_fn(ticker) -> float provides live prices.
        Falls back to cost_basis if no price_fn.
        """
        total = 0.0
        for ticker, pos in self._state["positions"].items():
            if price_fn:
                try:
                    price = price_fn(ticker)
                    total += pos["quantity"] * price
                    continue
                except Exception:
                    pass
            total += pos["cost_basis"]
        return total

    def get_portfolio_value(self, price_fn=None) -> float:
        """Total virtual portfolio value = cash + invested."""
        return self.get_virtual_cash() + self.get_invested_value(price_fn)

    def get_return_pct(self, price_fn=None) -> float:
        """Return as percentage of total deposited."""
        deposited = self.get_total_deposited()
        if deposited <= 0:
            return 0.0
        current = self.get_portfolio_value(price_fn)
        return ((current - deposited) / deposited) * 100

    def get_status(self, price_fn=None) -> dict:
        """Complete status summary."""
        invested = self.get_invested_value(price_fn)
        portfolio = self.get_virtual_cash() + invested
        deposited = self.get_total_deposited()
        pnl = portfolio - deposited
        pnl_pct = (pnl / deposited * 100) if deposited > 0 else 0

        return {
            "virtual_cash": round(self.get_virtual_cash(), 2),
            "invested_value": round(invested, 2),
            "portfolio_value": round(portfolio, 2),
            "total_deposited": round(deposited, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "positions_count": len(self._state["positions"]),
            "deposits_count": len(self._state["deposits"]),
            "currency": self.currency,
        }

    def get_deposit_history(self) -> list[dict]:
        """All deposits (initial + monthly + manual)."""
        return list(self._state.get("deposits", []))

    # ═══════════════════════════════════════════════════════════════
    # AGENT INTERFACE
    # ═══════════════════════════════════════════════════════════════

    def get_account_cash_for_agent(self) -> dict:
        """
        Returns cash info in the same format as broker.get_account_cash().
        Drop-in replacement so the agent sees virtual capital, not
        the full broker balance.
        """
        invested = self.get_invested_value()
        total = self.get_virtual_cash() + invested
        deposited = self.get_total_deposited()

        return {
            "free": self.get_virtual_cash(),
            "total": total,
            "invested": invested,
            "result": total - deposited,
            "buying_power": self.get_virtual_cash(),
        }


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Virtual Capital Manager")
    ap.add_argument("--status", action="store_true", help="Show virtual portfolio")
    ap.add_argument("--deposit", type=float, help="Manual deposit amount")
    ap.add_argument("--reset", action="store_true", help="Reset to initial state")
    ap.add_argument("--history", action="store_true", help="Deposit history")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent / ".env")
    except ImportError:
        pass

    import os
    vcm = VirtualCapitalManager(
        initial_capital=float(os.getenv("VIRTUAL_INITIAL_CAPITAL", "12500")),
        monthly_deposit=float(os.getenv("VIRTUAL_MONTHLY_DEPOSIT", "625")),
        deposit_day=int(os.getenv("VIRTUAL_DEPOSIT_DAY", "1")),
        currency=os.getenv("CURRENCY", "USD"),
        currency_symbol=os.getenv("CURRENCY_SYMBOL", "$"),
    )

    if args.reset:
        vcm.reset()
        print("[OK] Virtual capital reset.")
        return

    if args.deposit:
        vcm.deposit(args.deposit, deposit_type="manual")
        print(f"[OK] Deposited {vcm.currency_symbol}{args.deposit:,.2f}")

    if args.history:
        deposits = vcm.get_deposit_history()
        print(f"\n{'Date':<14} {'Amount':>12} {'Type':<10}")
        print("-" * 38)
        for d in deposits:
            sym = vcm.currency_symbol
            print(f"{d['date']:<14} {sym}{d['amount']:>10,.2f} {d['type']:<10}")
        total = vcm.get_total_deposited()
        print("-" * 38)
        print(f"{'Total':<14} {sym}{total:>10,.2f}")
        return

    # Default: show status
    status = vcm.get_status()
    sym = vcm.currency_symbol
    sign = "+" if status["pnl"] >= 0 else ""

    print(f"\n{'=' * 44}")
    print(f"  Virtual Capital Status ({status['currency']})")
    print(f"{'=' * 44}")
    print(f"  Cash:           {sym}{status['virtual_cash']:>12,.2f}")
    print(f"  Invested:       {sym}{status['invested_value']:>12,.2f}")
    print(f"  Portfolio:      {sym}{status['portfolio_value']:>12,.2f}")
    print(f"  Total Deposited:{sym}{status['total_deposited']:>12,.2f}")
    print(f"  P&L:            {sign}{sym}{status['pnl']:>11,.2f} ({sign}{status['pnl_pct']:.2f}%)")
    print(f"  Positions:      {status['positions_count']:>13}")
    print(f"  Deposits:       {status['deposits_count']:>13}")
    print(f"{'=' * 44}\n")

    # Show positions if any
    positions = vcm.get_positions()
    if positions:
        print(f"  {'Ticker':<8} {'Qty':>8} {'Avg':>10} {'Basis':>10} {'Sleeve':<12}")
        print(f"  {'-' * 50}")
        for ticker, pos in positions.items():
            print(
                f"  {ticker:<8} {pos['quantity']:>8.2f} "
                f"{sym}{pos['avg_price']:>9.2f} "
                f"{sym}{pos['cost_basis']:>9.2f} "
                f"{pos.get('sleeve', ''):<12}"
            )


if __name__ == "__main__":
    main()
