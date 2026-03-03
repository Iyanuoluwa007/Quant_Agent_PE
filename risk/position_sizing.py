"""
Position Sizing Module
Determines how much capital to allocate per trade using:
- ATR-based sizing (risk per trade)
- Kelly criterion (edge-based)
- Fixed fractional (fallback)
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def atr_position_size(
    sleeve_capital: float,
    risk_per_trade_pct: float,
    entry_price: float,
    atr: float,
    atr_multiplier: float = 2.0,
) -> dict:
    """
    ATR-based position sizing.
    Sizes the position so that a move of (atr_multiplier * ATR) against you
    equals exactly risk_per_trade_pct of sleeve capital.

    Returns: {quantity, stop_loss, risk_dollars}
    """
    if atr <= 0 or entry_price <= 0:
        return {"quantity": 0, "stop_loss": 0, "risk_dollars": 0}

    risk_dollars = sleeve_capital * (risk_per_trade_pct / 100)
    stop_distance = atr * atr_multiplier
    quantity = risk_dollars / stop_distance

    # Cap at max affordable
    max_affordable = sleeve_capital * 0.25 / entry_price  # never more than 25% of sleeve
    quantity = min(quantity, max_affordable)
    quantity = round(quantity, 4)

    stop_loss = round(entry_price - stop_distance, 2)

    return {
        "quantity": quantity,
        "stop_loss": stop_loss,
        "risk_dollars": round(risk_dollars, 2),
        "stop_distance": round(stop_distance, 2),
    }


def kelly_position_size(
    sleeve_capital: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    entry_price: float,
    kelly_fraction: float = 0.25,  # use quarter-Kelly for safety
) -> dict:
    """
    Kelly criterion position sizing.
    kelly_fraction < 1.0 for fractional Kelly (more conservative).

    Returns: {quantity, allocation_pct, kelly_full}
    """
    if avg_loss == 0 or entry_price <= 0:
        return {"quantity": 0, "allocation_pct": 0, "kelly_full": 0}

    # Kelly formula: f = (bp - q) / b
    # where b = avg_win/avg_loss, p = win_rate, q = 1-p
    b = avg_win / avg_loss
    p = win_rate
    q = 1 - p
    kelly_full = (b * p - q) / b

    if kelly_full <= 0:
        # Negative edge — don't trade
        return {"quantity": 0, "allocation_pct": 0, "kelly_full": kelly_full}

    allocation_pct = kelly_full * kelly_fraction
    allocation_pct = min(allocation_pct, 0.20)  # cap at 20% of sleeve
    allocation_dollars = sleeve_capital * allocation_pct
    quantity = round(allocation_dollars / entry_price, 4)

    return {
        "quantity": quantity,
        "allocation_pct": round(allocation_pct * 100, 2),
        "kelly_full": round(kelly_full * 100, 2),
    }


def fixed_fractional_size(
    sleeve_capital: float,
    fraction_pct: float,
    entry_price: float,
    max_position_pct: float = 15.0,
) -> dict:
    """
    Simple fixed fractional sizing.
    Allocates fraction_pct of sleeve capital per trade.

    Returns: {quantity, allocation_dollars}
    """
    if entry_price <= 0:
        return {"quantity": 0, "allocation_dollars": 0}

    allocation = sleeve_capital * (fraction_pct / 100)
    max_alloc = sleeve_capital * (max_position_pct / 100)
    allocation = min(allocation, max_alloc)
    quantity = round(allocation / entry_price, 4)

    return {
        "quantity": quantity,
        "allocation_dollars": round(allocation, 2),
    }


def calculate_position_size(
    sleeve_name: str,
    sleeve_capital: float,
    entry_price: float,
    atr: Optional[float] = None,
    confidence: float = 0.5,
    max_position_pct: float = 15.0,
) -> dict:
    """
    Master sizing function — picks the right method per sleeve.

    Short-term: ATR-based (tight risk control)
    Mid-term: ATR-based with wider multiplier
    Long-term: Fixed fractional (DCA style)
    """
    if sleeve_name == "short_term":
        if atr and atr > 0:
            sizing = atr_position_size(
                sleeve_capital=sleeve_capital,
                risk_per_trade_pct=1.0,  # risk 1% of sleeve per trade
                entry_price=entry_price,
                atr=atr,
                atr_multiplier=1.5,  # tight stop at 1.5x ATR
            )
        else:
            sizing = fixed_fractional_size(
                sleeve_capital, 5.0, entry_price, max_position_pct
            )
        # Scale by confidence
        sizing["quantity"] = round(sizing["quantity"] * min(confidence + 0.3, 1.0), 4)
        return sizing

    elif sleeve_name == "mid_term":
        if atr and atr > 0:
            sizing = atr_position_size(
                sleeve_capital=sleeve_capital,
                risk_per_trade_pct=2.0,  # risk 2% of sleeve per trade
                entry_price=entry_price,
                atr=atr,
                atr_multiplier=2.5,  # wider stop at 2.5x ATR
            )
        else:
            sizing = fixed_fractional_size(
                sleeve_capital, 10.0, entry_price, max_position_pct
            )
        sizing["quantity"] = round(sizing["quantity"] * min(confidence + 0.2, 1.0), 4)
        return sizing

    elif sleeve_name == "long_term":
        # DCA / fixed fractional — no ATR needed
        sizing = fixed_fractional_size(
            sleeve_capital,
            fraction_pct=10.0,
            entry_price=entry_price,
            max_position_pct=max_position_pct,
        )
        return sizing

    else:
        return fixed_fractional_size(sleeve_capital, 5.0, entry_price, max_position_pct)