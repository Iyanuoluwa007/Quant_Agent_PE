"""
Market Screener (Demo Edition)
Scans a universe of tickers and produces top candidates.
Uses dummy data when real downloads fail to avoid exposing API usage.
"""
import logging
import time
from typing import Optional
from dataclasses import dataclass
import pandas as pd

logger = logging.getLogger(__name__)

# ──────────────────────────────
# UNIVERSE
# ──────────────────────────────
FULL_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM",
    "BRK-B", "XOM", "JNJ", "V", "PG", "KO", "PEP", "TMO", "ORCL",
    "CSCO", "ADBE", "IBM", "INTU", "AMGN", "VZ", "GS", "MS", "PFE",
    "MRK", "DUK", "SO", "NEE", "LMT", "RTX", "BA", "SHOP", "PYPL",
    "UBER", "ABNB", "RIVN", "LCID"
]

@dataclass
class ScreenResult:
    ticker: str
    price: float
    change_pct: float
    rsi: float
    volume_ratio: float
    above_sma20: bool
    above_sma50: bool
    macd_signal: str
    atr: float
    market_cap: float
    sector: str
    momentum_score: float
    trend_score: float

class MarketScreener:
    """Demo market screener."""

    def __init__(self, universe: list[str] = None):
        self.universe = universe or FULL_UNIVERSE
        self._cache: dict[str, ScreenResult] = {}
        self._last_scan_time: float = 0
        self._cache_ttl: int = 900  # 15 min

    def scan(self, force: bool = False) -> dict[str, ScreenResult]:
        now = time.time()
        if not force and self._cache and (now - self._last_scan_time < self._cache_ttl):
            logger.info(f"[SCREENER DEMO] Using cached scan ({len(self._cache)} tickers)")
            return self._cache

        logger.info(f"[SCREENER DEMO] Scanning {len(self.universe)} tickers...")
        results = {}
        for ticker in self.universe:
            result = self._analyze_ticker_demo(ticker)
            if result:
                results[ticker] = result

        self._cache = results
        self._last_scan_time = now
        logger.info(f"[SCREENER DEMO] Scan complete: {len(results)} tickers analyzed")
        return results

    def _analyze_ticker_demo(self, ticker: str) -> Optional[ScreenResult]:
        """Generate dummy signals for public demo."""
        import random
        price = round(random.uniform(10, 500), 2)
        change_pct = round(random.uniform(-3, 3), 2)
        rsi = round(random.uniform(20, 80), 1)
        volume_ratio = round(random.uniform(0.5, 3.0), 2)
        above_sma20 = random.choice([True, False])
        above_sma50 = random.choice([True, False])
        macd_signal = random.choice(["bullish", "bearish", "neutral"])
        atr = round(random.uniform(0.5, 5.0), 2)
        market_cap = round(random.uniform(1e9, 5e11))
        sector = "DemoSector"
        momentum_score = round(random.uniform(0, 100), 1)
        trend_score = round(random.uniform(0, 100), 1)
        return ScreenResult(
            ticker=ticker,
            price=price,
            change_pct=change_pct,
            rsi=rsi,
            volume_ratio=volume_ratio,
            above_sma20=above_sma20,
            above_sma50=above_sma50,
            macd_signal=macd_signal,
            atr=atr,
            market_cap=market_cap,
            sector=sector,
            momentum_score=momentum_score,
            trend_score=trend_score,
        )

    def get_short_term_picks(self, top_n: int = 12) -> list[ScreenResult]:
        results = self.scan()
        candidates = [r for r in results.values() if r.momentum_score > 15 and r.rsi < 75 and r.price > 5]
        candidates.sort(key=lambda x: x.momentum_score, reverse=True)
        picks = candidates[:top_n]
        if picks:
            logger.info("[SCREENER DEMO] Short-term picks: " + ", ".join(p.ticker for p in picks[:5]))
        return picks

    def get_mid_term_picks(self, top_n: int = 12) -> list[ScreenResult]:
        results = self.scan()
        candidates = [r for r in results.values() if r.trend_score > 20 and r.rsi < 80 and r.price > 10]
        candidates.sort(key=lambda x: x.trend_score, reverse=True)
        picks = candidates[:top_n]
        if picks:
            logger.info("[SCREENER DEMO] Mid-term picks: " + ", ".join(p.ticker for p in picks[:5]))
        return picks

    def format_picks_for_claude(self, picks: list[ScreenResult]) -> str:
        if not picks:
            return "No screener picks available."
        lines = ["## Pre-Screened Candidates (Demo):"]
        for i, p in enumerate(picks, 1):
            trend_status = "UP" if p.above_sma20 and p.above_sma50 else "PULLBACK" if p.above_sma50 else "DOWN"
            lines.append(
                f"{i}. {p.ticker}: ${p.price:.2f} ({p.change_pct:+.1f}%) | "
                f"RSI {p.rsi:.0f} | Vol {p.volume_ratio:.1f}x | "
                f"MACD {p.macd_signal} | Trend: {trend_status} | ATR ${p.atr:.2f}"
            )
        return "\n".join(lines)