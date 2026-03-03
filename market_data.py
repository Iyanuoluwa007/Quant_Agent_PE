"""
Market Data Service
Fetches real-time and historical market data from free sources.
Uses Yahoo Finance (yfinance) and news via web search.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class StockSnapshot:
    """Current snapshot of a stock's data."""
    ticker: str
    name: str
    current_price: float
    open_price: float
    high: float
    low: float
    volume: int
    market_cap: Optional[float]
    pe_ratio: Optional[float]
    fifty_two_week_high: Optional[float]
    fifty_two_week_low: Optional[float]
    avg_volume: Optional[int]
    dividend_yield: Optional[float]
    sector: Optional[str]
    industry: Optional[str]
    change_pct: float  # % change today

    def to_summary(self) -> str:
        """Human-readable summary for Claude analysis."""
        mcap_str = f"${self.market_cap / 1e9:.1f}B" if self.market_cap else "N/A"
        avg_vol_str = f"{self.avg_volume:,}" if self.avg_volume else "N/A"
        low_52 = f"${self.fifty_two_week_low:.2f}" if self.fifty_two_week_low else "?"
        high_52 = f"${self.fifty_two_week_high:.2f}" if self.fifty_two_week_high else "?"
        return (
            f"**{self.name} ({self.ticker})**\n"
            f"Price: ${self.current_price:.2f} ({self.change_pct:+.2f}%)\n"
            f"Open: ${self.open_price:.2f} | High: ${self.high:.2f} | Low: ${self.low:.2f}\n"
            f"Volume: {self.volume:,} (Avg: {avg_vol_str})\n"
            f"Market Cap: {mcap_str}\n"
            f"P/E: {self.pe_ratio or 'N/A'} | "
            f"52W: {low_52}-{high_52}\n"
            f"Sector: {self.sector or 'N/A'}"
        )


def ticker_t212_to_yahoo(t212_ticker: str) -> str:
    """Convert Trading212 ticker format to Yahoo Finance format.
    e.g., 'AAPL_US_EQ' -> 'AAPL'
    """
    return t212_ticker.split("_")[0]


class MarketDataService:
    """Fetches and processes market data."""

    def __init__(self):
        self._cache: dict[str, tuple[datetime, any]] = {}
        self._cache_ttl = 60  # seconds

    def get_stock_snapshot(self, ticker_t212: str) -> Optional[StockSnapshot]:
        """Get current stock data snapshot."""
        yahoo_ticker = ticker_t212_to_yahoo(ticker_t212)

        try:
            stock = yf.Ticker(yahoo_ticker)
            info = stock.info

            if not info or "currentPrice" not in info:
                # Fallback: use fast_info or history
                hist = stock.history(period="2d")
                if hist.empty:
                    logger.warning(f"No data for {yahoo_ticker}")
                    return None
                current = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else current
                change_pct = ((current - prev_close) / prev_close) * 100
                return StockSnapshot(
                    ticker=ticker_t212,
                    name=info.get("shortName", yahoo_ticker),
                    current_price=round(current, 2),
                    open_price=round(hist["Open"].iloc[-1], 2),
                    high=round(hist["High"].iloc[-1], 2),
                    low=round(hist["Low"].iloc[-1], 2),
                    volume=int(hist["Volume"].iloc[-1]),
                    market_cap=info.get("marketCap"),
                    pe_ratio=info.get("trailingPE"),
                    fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
                    fifty_two_week_low=info.get("fiftyTwoWeekLow"),
                    avg_volume=info.get("averageVolume"),
                    dividend_yield=info.get("dividendYield"),
                    sector=info.get("sector"),
                    industry=info.get("industry"),
                    change_pct=round(change_pct, 2),
                )

            current = info["currentPrice"]
            prev_close = info.get("previousClose", current)
            change_pct = ((current - prev_close) / prev_close) * 100

            return StockSnapshot(
                ticker=ticker_t212,
                name=info.get("shortName", yahoo_ticker),
                current_price=round(current, 2),
                open_price=round(info.get("open", current), 2),
                high=round(info.get("dayHigh", current), 2),
                low=round(info.get("dayLow", current), 2),
                volume=info.get("volume", 0),
                market_cap=info.get("marketCap"),
                pe_ratio=info.get("trailingPE"),
                fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
                fifty_two_week_low=info.get("fiftyTwoWeekLow"),
                avg_volume=info.get("averageVolume"),
                dividend_yield=info.get("dividendYield"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                change_pct=round(change_pct, 2),
            )
        except Exception as e:
            logger.error(f"Error fetching data for {yahoo_ticker}: {e}")
            return None

    def get_technical_indicators(
        self, ticker_t212: str, period: str = "3mo"
    ) -> Optional[dict]:
        """Calculate technical indicators from historical data."""
        yahoo_ticker = ticker_t212_to_yahoo(ticker_t212)

        try:
            stock = yf.Ticker(yahoo_ticker)
            hist = stock.history(period=period)

            if hist.empty or len(hist) < 20:
                return None

            close = hist["Close"]
            volume = hist["Volume"]

            # Moving Averages
            sma_20 = close.rolling(20).mean().iloc[-1]
            sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
            ema_12 = close.ewm(span=12).mean().iloc[-1]
            ema_26 = close.ewm(span=26).mean().iloc[-1]

            # MACD
            macd_line = ema_12 - ema_26
            signal_line = (
                (close.ewm(span=12).mean() - close.ewm(span=26).mean())
                .ewm(span=9).mean().iloc[-1]
            )

            # RSI (14-period)
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
            rsi = 100 - (100 / (1 + gain / loss)) if loss != 0 else 50

            # Bollinger Bands
            bb_mid = sma_20
            bb_std = close.rolling(20).std().iloc[-1]
            bb_upper = bb_mid + 2 * bb_std
            bb_lower = bb_mid - 2 * bb_std

            # Volume trend
            avg_vol_20 = volume.rolling(20).mean().iloc[-1]
            vol_ratio = volume.iloc[-1] / avg_vol_20 if avg_vol_20 > 0 else 1

            # Price momentum
            returns_5d = ((close.iloc[-1] / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
            returns_20d = ((close.iloc[-1] / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

            current_price = close.iloc[-1]

            return {
                "current_price": round(current_price, 2),
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2) if sma_50 else None,
                "ema_12": round(ema_12, 2),
                "ema_26": round(ema_26, 2),
                "macd": round(macd_line, 4),
                "macd_signal": round(signal_line, 4),
                "macd_histogram": round(macd_line - signal_line, 4),
                "rsi_14": round(rsi, 2),
                "bollinger_upper": round(bb_upper, 2),
                "bollinger_mid": round(bb_mid, 2),
                "bollinger_lower": round(bb_lower, 2),
                "volume_ratio": round(vol_ratio, 2),
                "returns_5d_pct": round(returns_5d, 2),
                "returns_20d_pct": round(returns_20d, 2),
                "price_vs_sma20": round(
                    ((current_price / sma_20) - 1) * 100, 2
                ),
                "price_vs_sma50": round(
                    ((current_price / sma_50) - 1) * 100, 2
                ) if sma_50 else None,
            }
        except Exception as e:
            logger.error(f"Error computing indicators for {yahoo_ticker}: {e}")
            return None

    def format_for_claude(
        self, ticker_t212: str
    ) -> str:
        """Get a full formatted analysis string for Claude to reason about."""
        snapshot = self.get_stock_snapshot(ticker_t212)
        technicals = self.get_technical_indicators(ticker_t212)

        if not snapshot:
            return f"[No data available for {ticker_t212}]"

        parts = [snapshot.to_summary(), ""]

        if technicals:
            parts.append("**Technical Indicators:**")
            parts.append(f"  RSI(14): {technicals['rsi_14']}")
            parts.append(f"  MACD: {technicals['macd']} (Signal: {technicals['macd_signal']})")
            parts.append(f"  SMA20: ${technicals['sma_20']} (Price {technicals['price_vs_sma20']:+.2f}%)")
            if technicals['sma_50']:
                parts.append(f"  SMA50: ${technicals['sma_50']} (Price {technicals['price_vs_sma50']:+.2f}%)")
            parts.append(
                f"  Bollinger: ${technicals['bollinger_lower']:.2f} - "
                f"${technicals['bollinger_upper']:.2f}"
            )
            parts.append(f"  Volume Ratio: {technicals['volume_ratio']}x avg")
            parts.append(f"  5D Return: {technicals['returns_5d_pct']:+.2f}%")
            parts.append(f"  20D Return: {technicals['returns_20d_pct']:+.2f}%")

        return "\n".join(parts)