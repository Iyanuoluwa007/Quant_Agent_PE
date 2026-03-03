"""
Simulated Broker Adapter -- Public Edition
Paper trading interface that mimics a real broker API.

In production, this is swapped for the real broker client (Alpaca/T212).
The public repo ships with this simulator so anyone can run and test
the full system without API keys or real money.

Supports:
  - Account balance tracking
  - Position management (buy/sell with fractional shares)
  - Order book (market, limit, stop)
  - Market clock awareness (US market hours)
  - Realistic fill simulation (slippage, partial fills)
"""
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import yfinance as yf

logger = logging.getLogger(__name__)

SIMULATED_STATE_FILE = Path("simulated_broker_state.json")


@dataclass
class SimulatedOrder:
    id: str
    symbol: str
    side: str           # "buy" or "sell"
    quantity: float
    order_type: str     # "market", "limit", "stop", "stop_limit"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = "new"           # new, filled, cancelled, rejected
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    created_at: str = ""
    filled_at: Optional[str] = None


class BrokerAdapter:
    """
    Simulated broker for the public edition.

    Tracks a virtual portfolio with realistic market data.
    Drop-in replacement for the real broker client -- same interface.
    """

    def __init__(self, config):
        self.config = config
        self._state = self._load_state()
        self._order_counter = self._state.get("order_counter", 0)
        self._price_cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, timestamp)
        logger.info(
            f"[SIM] Broker adapter initialized | "
            f"Cash: ${self._state['cash']:,.2f} | "
            f"Positions: {len(self._state['positions'])}"
        )

    # ═══════════════════════════════════════════════════════════════
    # STATE PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def _load_state(self) -> dict:
        if SIMULATED_STATE_FILE.exists():
            try:
                return json.loads(SIMULATED_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        initial_cash = float(self.config.INITIAL_CAPITAL)
        return {
            "cash": initial_cash,
            "initial_capital": initial_cash,
            "positions": {},       # symbol -> {qty, avg_price, sleeve}
            "orders": [],          # order history
            "pending_orders": [],  # unfilled orders
            "order_counter": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _save_state(self):
        self._state["order_counter"] = self._order_counter
        SIMULATED_STATE_FILE.write_text(
            json.dumps(self._state, indent=2), encoding="utf-8"
        )

    def reset(self, capital: float = None):
        """Reset to initial state."""
        amount = capital or float(self.config.INITIAL_CAPITAL)
        self._state = {
            "cash": amount,
            "initial_capital": amount,
            "positions": {},
            "orders": [],
            "pending_orders": [],
            "order_counter": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_state()
        logger.info(f"[SIM] Reset to ${amount:,.2f}")

    # ═══════════════════════════════════════════════════════════════
    # ACCOUNT
    # ═══════════════════════════════════════════════════════════════

    def get_account_cash(self) -> dict:
        invested = self._total_invested()
        total = self._state["cash"] + invested
        return {
            "free": self._state["cash"],
            "total": total,
            "invested": invested,
            "result": total - self._state["initial_capital"],
            "buying_power": self._state["cash"],
        }

    def get_account_info(self) -> dict:
        return {
            "id": "SIM-PUBLIC-EDITION",
            "currencyCode": "USD",
            "status": "ACTIVE",
            "pattern_day_trader": False,
            "day_trade_count": 0,
            "equity": self._state["cash"] + self._total_invested(),
            "mode": "simulated",
        }

    def _total_invested(self) -> float:
        total = 0.0
        for symbol, pos in self._state["positions"].items():
            price = self._get_price(symbol)
            total += abs(pos["quantity"]) * price
        return total

    # ═══════════════════════════════════════════════════════════════
    # PORTFOLIO
    # ═══════════════════════════════════════════════════════════════

    def get_positions(self) -> list[dict]:
        result = []
        for symbol, pos in self._state["positions"].items():
            if pos["quantity"] <= 0:
                continue
            price = self._get_price(symbol)
            avg = pos["avg_price"]
            qty = pos["quantity"]
            pnl = (price - avg) * qty
            pnl_pct = ((price - avg) / avg * 100) if avg > 0 else 0
            result.append({
                "ticker": symbol,
                "quantity": qty,
                "averagePrice": round(avg, 2),
                "currentPrice": round(price, 2),
                "marketValue": round(qty * price, 2),
                "result": round(pnl, 2),
                "resultPct": round(pnl_pct, 2),
                "side": "long",
                "sleeve": pos.get("sleeve", "unknown"),
            })
        return result

    def get_position(self, symbol: str) -> Optional[dict]:
        positions = self.get_positions()
        for p in positions:
            if p["ticker"] == symbol:
                return p
        return None

    # ═══════════════════════════════════════════════════════════════
    # ORDERS
    # ═══════════════════════════════════════════════════════════════

    def place_market_order(self, symbol: str, quantity: float) -> dict:
        side = "buy" if quantity > 0 else "sell"
        qty = abs(quantity)
        price = self._get_price(symbol)

        if price <= 0:
            return self._reject_order(symbol, qty, side, "No price data")

        # Apply simulated slippage (5 bps)
        slippage = price * 0.0005
        fill_price = price + slippage if side == "buy" else price - slippage

        return self._execute_fill(symbol, qty, side, round(fill_price, 2), "market")

    def place_limit_order(
        self, symbol: str, quantity: float, limit_price: float,
        time_validity: str = "Day"
    ) -> dict:
        side = "buy" if quantity > 0 else "sell"
        qty = abs(quantity)
        price = self._get_price(symbol)

        # Simulate: fill immediately if price is favorable
        if side == "buy" and price <= limit_price:
            return self._execute_fill(symbol, qty, side, min(price, limit_price), "limit")
        elif side == "sell" and price >= limit_price:
            return self._execute_fill(symbol, qty, side, max(price, limit_price), "limit")

        # Otherwise, queue as pending
        return self._queue_order(symbol, qty, side, "limit", limit_price=limit_price)

    def place_stop_order(
        self, symbol: str, quantity: float, stop_price: float,
        time_validity: str = "Day"
    ) -> dict:
        side = "buy" if quantity > 0 else "sell"
        qty = abs(quantity)
        return self._queue_order(symbol, qty, side, "stop", stop_price=stop_price)

    def place_stop_limit_order(
        self, symbol: str, quantity: float,
        stop_price: float, limit_price: float,
        time_validity: str = "Day"
    ) -> dict:
        side = "buy" if quantity > 0 else "sell"
        qty = abs(quantity)
        return self._queue_order(
            symbol, qty, side, "stop_limit",
            stop_price=stop_price, limit_price=limit_price,
        )

    def cancel_order(self, order_id: str) -> dict:
        pending = self._state["pending_orders"]
        self._state["pending_orders"] = [
            o for o in pending if o["id"] != order_id
        ]
        self._save_state()
        logger.info(f"[SIM] Cancelled order {order_id}")
        return {"status": "cancelled", "id": order_id}

    def get_pending_orders(self) -> list[dict]:
        return self._state.get("pending_orders", [])

    # ═══════════════════════════════════════════════════════════════
    # MARKET CLOCK
    # ═══════════════════════════════════════════════════════════════

    def get_market_clock(self) -> dict:
        now_utc = datetime.now(timezone.utc)
        et_offset = timedelta(hours=-5)
        now_et = now_utc + et_offset

        weekday = now_et.weekday()
        hour = now_et.hour
        minute = now_et.minute
        time_min = hour * 60 + minute

        is_open = (weekday < 5 and 570 <= time_min <= 960)

        # Calculate next open/close
        if is_open:
            next_close = now_et.replace(hour=16, minute=0, second=0)
            next_open = next_close + timedelta(hours=17, minutes=30)
        else:
            if weekday >= 5:
                days_until_monday = 7 - weekday
                next_open = (now_et + timedelta(days=days_until_monday)).replace(
                    hour=9, minute=30, second=0
                )
            elif time_min < 570:
                next_open = now_et.replace(hour=9, minute=30, second=0)
            else:
                next_open = (now_et + timedelta(days=1)).replace(
                    hour=9, minute=30, second=0
                )
            next_close = next_open.replace(hour=16, minute=0)

        return {
            "is_open": is_open,
            "next_open": next_open.isoformat(),
            "next_close": next_close.isoformat(),
            "timestamp": now_utc.isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════
    # HISTORY
    # ═══════════════════════════════════════════════════════════════

    def get_order_history(self, limit: int = 50) -> dict:
        orders = self._state.get("orders", [])
        return {"items": orders[-limit:]}

    # ═══════════════════════════════════════════════════════════════
    # INTERNALS
    # ═══════════════════════════════════════════════════════════════

    def _get_price(self, symbol: str) -> float:
        """Get current price with 60s cache."""
        now = time.time()
        if symbol in self._price_cache:
            price, ts = self._price_cache[symbol]
            if now - ts < 60:
                return price
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="5d")
            if not hist.empty:
                price = round(float(hist["Close"].iloc[-1]), 2)
                self._price_cache[symbol] = (price, now)
                return price
        except Exception as e:
            logger.warning(f"[SIM] Price fetch failed for {symbol}: {e}")
        return 0.0

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"SIM-{self._order_counter:06d}"

    def _execute_fill(
        self, symbol: str, qty: float, side: str,
        fill_price: float, order_type: str,
    ) -> dict:
        """Execute a fill immediately."""
        order_id = self._next_order_id()
        cost = qty * fill_price

        if side == "buy":
            if cost > self._state["cash"]:
                return self._reject_order(symbol, qty, side, "Insufficient funds")
            self._state["cash"] -= cost
            pos = self._state["positions"].get(symbol, {"quantity": 0, "avg_price": 0})
            old_qty = pos["quantity"]
            old_cost = old_qty * pos["avg_price"]
            new_qty = old_qty + qty
            new_avg = (old_cost + cost) / new_qty if new_qty > 0 else 0
            self._state["positions"][symbol] = {
                "quantity": round(new_qty, 4),
                "avg_price": round(new_avg, 4),
                "sleeve": pos.get("sleeve", "unknown"),
            }
        else:
            pos = self._state["positions"].get(symbol)
            if not pos or pos["quantity"] < qty:
                return self._reject_order(symbol, qty, side, "Insufficient shares")
            self._state["cash"] += cost
            pos["quantity"] = round(pos["quantity"] - qty, 4)
            if pos["quantity"] <= 0.0001:
                del self._state["positions"][symbol]

        order = {
            "id": order_id,
            "ticker": symbol,
            "side": side,
            "type": order_type,
            "quantity": qty,
            "filledQuantity": qty,
            "fillPrice": fill_price,
            "limitPrice": None,
            "stopPrice": None,
            "status": "filled",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "filledAt": datetime.now(timezone.utc).isoformat(),
        }
        self._state["orders"].append(order)
        self._save_state()

        logger.info(
            f"[SIM] FILLED {side.upper()} {qty} {symbol} "
            f"@ ${fill_price:.2f} (${cost:.2f})"
        )
        return order

    def _queue_order(
        self, symbol: str, qty: float, side: str, order_type: str,
        limit_price: float = None, stop_price: float = None,
    ) -> dict:
        order_id = self._next_order_id()
        order = {
            "id": order_id,
            "ticker": symbol,
            "side": side,
            "type": order_type,
            "quantity": qty,
            "filledQuantity": 0,
            "fillPrice": None,
            "limitPrice": limit_price,
            "stopPrice": stop_price,
            "status": "new",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "filledAt": None,
        }
        self._state["pending_orders"].append(order)
        self._save_state()
        logger.info(
            f"[SIM] QUEUED {side.upper()} {qty} {symbol} "
            f"({order_type} limit={limit_price} stop={stop_price})"
        )
        return order

    def _reject_order(self, symbol: str, qty: float, side: str, reason: str) -> dict:
        order_id = self._next_order_id()
        order = {
            "id": order_id,
            "ticker": symbol,
            "side": side,
            "quantity": qty,
            "status": "rejected",
            "reason": reason,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        self._state["orders"].append(order)
        self._save_state()
        logger.warning(f"[SIM] REJECTED {side.upper()} {qty} {symbol}: {reason}")
        return order

    def set_sleeve(self, symbol: str, sleeve: str):
        """Tag a position with its strategy sleeve."""
        if symbol in self._state["positions"]:
            self._state["positions"][symbol]["sleeve"] = sleeve
            self._save_state()
