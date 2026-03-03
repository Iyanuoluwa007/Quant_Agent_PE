"""
Market Screener
Scans the broad market (S&P 500 + Nasdaq 100 + extras) and pre-filters
the top candidates for each strategy sleeve.

Flow:
  1. Fetch universe (~600 tickers)
  2. Calculate quick technical signals for all
  3. Rank and filter by sleeve-specific criteria
  4. Return top N picks for Claude to analyze deeply

This runs BEFORE Claude — saving API costs by only sending
the best 10-15 candidates instead of 600.
"""
import logging
import time
from typing import Optional
from dataclasses import dataclass
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# UNIVERSE — tickers to scan
# ═══════════════════════════════════════════════════════════════════

# S&P 500 top 100 by market cap + Nasdaq 100 + popular mid-caps
# This gives ~250 unique liquid tickers without scanning every penny stock
UNIVERSE_SP500_TOP = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "LLY",
    "AVGO", "JPM", "TSLA", "UNH", "XOM", "V", "MA", "PG", "COST",
    "JNJ", "HD", "ABBV", "MRK", "WMT", "NFLX", "CRM", "BAC", "CVX",
    "AMD", "KO", "PEP", "TMO", "LIN", "ORCL", "ACN", "MCD", "CSCO",
    "ABT", "ADBE", "WFC", "GE", "PM", "TXN", "IBM", "DHR", "ISRG",
    "QCOM", "CAT", "INTU", "AMGN", "VZ", "AMAT", "GS", "AXP", "MS",
    "PFE", "BLK", "NOW", "LOW", "SPGI", "RTX", "BKNG", "HON", "T",
    "NEE", "UNP", "COP", "DE", "SYK", "MDT", "BA", "ELV", "BMY",
    "PLD", "LMT", "SCHW", "GILD", "CB", "MDLZ", "VRTX",
    "CI", "SO", "DUK", "SHW", "CME", "TGT", "ZTS", "BDX", "AON",
    "MO", "REGN", "ICE", "NOC", "CL", "USB", "PNC", "FDX", "EMR",
]

UNIVERSE_NASDAQ_EXTRA = [
    "MRVL", "PANW", "SNPS", "CDNS", "LRCX", "KLAC", "FTNT", "DDOG",
    "WDAY", "ZS", "CRWD", "TEAM", "TTD", "MDB", "DASH", "COIN",
    "PLTR", "MARA", "SOFI", "HOOD", "RBLX", "ROKU", "XYZ", "SHOP",
    "PYPL", "UBER", "ABNB", "RIVN", "LCID", "ARM", "SMCI", "MSTR",
    "AI", "PATH", "NET", "SNOW", "OKTA", "DKNG", "ENPH", "SEDG",
    "FSLR", "CEG", "VST", "ANET", "ON", "GFS", "MPWR", "ALGN",
]

UNIVERSE_VALUE_DIVIDEND = [
    "BRK-B", "JPM", "BAC", "WFC", "GS", "MS",  # Financials
    "XOM", "CVX", "COP", "EOG", "SLB", "OXY",    # Energy
    "PG", "KO", "PEP", "CL", "MDLZ",             # Consumer staples
    "JNJ", "PFE", "MRK", "ABBV", "BMY",           # Healthcare
    "T", "VZ",                                      # Telecom
    "NEE", "DUK", "SO",                            # Utilities
    "O", "AMT", "SPG",                              # REITs
]

# Combine and deduplicate
FULL_UNIVERSE = sorted(set(
    UNIVERSE_SP500_TOP + UNIVERSE_NASDAQ_EXTRA + UNIVERSE_VALUE_DIVIDEND
))


@dataclass
class ScreenResult:
    """Screened stock with quick metrics."""
    ticker: str
    price: float
    change_pct: float
    rsi: float
    volume_ratio: float   # current vol / avg vol
    above_sma20: bool
    above_sma50: bool
    macd_signal: str      # "bullish", "bearish", "neutral"
    atr: float
    market_cap: float
    sector: str
    # Composite scores
    momentum_score: float     # for short-term
    trend_score: float        # for mid-term


class MarketScreener:
    """Scans the market and returns top picks per sleeve."""

    def __init__(self, universe: list[str] = None):
        self.universe = universe or FULL_UNIVERSE
        self._cache: dict[str, ScreenResult] = {}
        self._last_scan_time: float = 0
        self._cache_ttl: int = 900  # 15 min cache

    def scan(self, force: bool = False) -> dict[str, ScreenResult]:
        """
        Scan the full universe. Returns dict of ticker -> ScreenResult.
        Caches results for 15 minutes.
        """
        now = time.time()
        if not force and self._cache and (now - self._last_scan_time < self._cache_ttl):
            logger.info(f"[SCREENER] Using cached scan ({len(self._cache)} tickers)")
            return self._cache

        logger.info(f"[SCREENER] Scanning {len(self.universe)} tickers...")
        results = {}

        # Batch download — yfinance supports multiple tickers at once
        # Process in chunks to avoid timeouts
        chunk_size = 50
        for i in range(0, len(self.universe), chunk_size):
            chunk = self.universe[i:i + chunk_size]
            try:
                results.update(self._scan_chunk(chunk))
            except Exception as e:
                logger.warning(f"[SCREENER] Chunk {i}-{i+chunk_size} failed: {e}")
                continue

        self._cache = results
        self._last_scan_time = now
        logger.info(f"[SCREENER] Scan complete: {len(results)} tickers analyzed")
        return results

    def _scan_chunk(self, tickers: list[str]) -> dict[str, ScreenResult]:
        """Scan a chunk of tickers using batch download with retry."""
        results = {}
        ticker_str = " ".join(tickers)

        data = None
        for attempt in range(3):  # 3 attempts with backoff
            try:
                data = yf.download(
                    ticker_str,
                    period="3mo",
                    interval="1d",
                    group_by="ticker",
                    progress=False,
                    threads=True,
                )
                if data is not None and not data.empty:
                    break
            except Exception as e:
                if attempt < 2:
                    wait = (attempt + 1) * 2  # 2s, 4s backoff
                    logger.warning(
                        f"[SCREENER] Download attempt {attempt+1} failed: {e} "
                        f"— retrying in {wait}s"
                    )
                    time.sleep(wait)
                else:
                    logger.warning(f"[SCREENER] Download failed after 3 attempts: {e}")
                    return results

        if data is None or data.empty:
            return results

        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    df = data
                else:
                    if ticker not in data.columns.get_level_values(0):
                        continue
                    df = data[ticker]

                if df.empty or len(df) < 20:
                    continue

                df = df.dropna(subset=["Close"])
                if len(df) < 20:
                    continue

                result = self._analyze_ticker(ticker, df)
                if result:
                    results[ticker] = result
            except Exception:
                continue

        return results

    def _analyze_ticker(self, ticker: str, df: pd.DataFrame) -> Optional[ScreenResult]:
        """Calculate quick technical signals for a single ticker."""
        try:
            close = df["Close"].values
            volume = df["Volume"].values
            high = df["High"].values
            low = df["Low"].values

            if len(close) < 20:
                return None

            price = float(close[-1])
            if price <= 0:
                return None

            prev_close = float(close[-2]) if len(close) > 1 else price
            change_pct = ((price - prev_close) / prev_close) * 100

            # RSI (14-period)
            rsi = self._calc_rsi(close, 14)

            # Volume ratio
            avg_vol = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
            curr_vol = float(volume[-1])
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

            # SMAs
            sma20 = float(close[-20:].mean())
            sma50 = float(close[-50:].mean()) if len(close) >= 50 else sma20
            above_sma20 = price > sma20
            above_sma50 = price > sma50

            # MACD
            macd_signal = self._calc_macd_signal(close)

            # ATR (14-period)
            atr = self._calc_atr(high, low, close, 14)

            # Market cap (approximate from info cache)
            market_cap = 0
            sector = "Unknown"
            try:
                info = yf.Ticker(ticker).fast_info
                market_cap = getattr(info, "market_cap", 0) or 0
            except Exception:
                pass

            # ── Composite Scores ────────────────────────────────────

            # MOMENTUM SCORE (for short-term sleeve)
            # High score = good momentum entry candidate
            momentum_score = 0.0

            # RSI oversold bounce (RSI < 30 but recovering)
            if rsi < 25:
                momentum_score += 30
            elif rsi < 35:
                momentum_score += 20
            elif rsi > 70:
                momentum_score -= 20  # overbought, avoid

            # Volume spike (something happening)
            if vol_ratio > 2.0:
                momentum_score += 25
            elif vol_ratio > 1.5:
                momentum_score += 15

            # MACD bullish crossover
            if macd_signal == "bullish":
                momentum_score += 20
            elif macd_signal == "bearish":
                momentum_score -= 10

            # Price near SMA20 support
            if above_sma20 and (price - sma20) / sma20 < 0.02:
                momentum_score += 15  # just above support

            # Intraday move
            if abs(change_pct) > 2:
                momentum_score += 10  # volatility = opportunity

            # TREND SCORE (for mid-term sleeve)
            # High score = confirmed uptrend with pullback entry
            trend_score = 0.0

            # Price above both MAs = uptrend
            if above_sma20 and above_sma50:
                trend_score += 25
            elif above_sma50 and not above_sma20:
                trend_score += 15  # pullback in uptrend — good entry
            elif not above_sma20 and not above_sma50:
                trend_score -= 10  # downtrend

            # SMA20 > SMA50 = trend confirmed
            if sma20 > sma50:
                trend_score += 20
            else:
                trend_score -= 15

            # MACD direction
            if macd_signal == "bullish":
                trend_score += 20
            elif macd_signal == "bearish":
                trend_score -= 15

            # RSI healthy range for trends (40-65)
            if 40 <= rsi <= 65:
                trend_score += 15
            elif rsi < 30:
                trend_score += 10  # deep value
            elif rsi > 75:
                trend_score -= 20  # exhaustion

            # Volume confirmation
            if vol_ratio > 1.2:
                trend_score += 10

            return ScreenResult(
                ticker=ticker,
                price=round(price, 2),
                change_pct=round(change_pct, 2),
                rsi=round(rsi, 1),
                volume_ratio=round(vol_ratio, 2),
                above_sma20=above_sma20,
                above_sma50=above_sma50,
                macd_signal=macd_signal,
                atr=round(atr, 2),
                market_cap=market_cap,
                sector=sector,
                momentum_score=round(momentum_score, 1),
                trend_score=round(trend_score, 1),
            )
        except Exception:
            return None

    # ── Technical Helpers ───────────────────────────────────────

    def _calc_rsi(self, prices, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        deltas = pd.Series(prices).diff().dropna()
        gains = deltas.where(deltas > 0, 0.0)
        losses = -deltas.where(deltas < 0, 0.0)
        avg_gain = gains.rolling(period).mean().iloc[-1]
        avg_loss = losses.rolling(period).mean().iloc[-1]
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - (100 / (1 + rs)))

    def _calc_macd_signal(self, prices) -> str:
        if len(prices) < 26:
            return "neutral"
        s = pd.Series(prices)
        ema12 = s.ewm(span=12).mean()
        ema26 = s.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        hist = macd - signal
        if len(hist) < 2:
            return "neutral"
        if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0:
            return "bullish"
        elif hist.iloc[-1] < 0 and hist.iloc[-2] >= 0:
            return "bearish"
        elif hist.iloc[-1] > 0:
            return "bullish"
        elif hist.iloc[-1] < 0:
            return "bearish"
        return "neutral"

    def _calc_atr(self, high, low, close, period: int = 14) -> float:
        if len(high) < period + 1:
            return 0.0
        tr_values = []
        for i in range(1, len(high)):
            tr = max(
                float(high[i]) - float(low[i]),
                abs(float(high[i]) - float(close[i - 1])),
                abs(float(low[i]) - float(close[i - 1])),
            )
            tr_values.append(tr)
        if len(tr_values) < period:
            return sum(tr_values) / len(tr_values) if tr_values else 0
        return sum(tr_values[-period:]) / period

    # ── Sleeve-Specific Filters ─────────────────────────────────

    def get_short_term_picks(self, top_n: int = 12) -> list[ScreenResult]:
        """
        Top momentum candidates for short-term sleeve.
        Filters: liquid, high momentum score, not overbought.
        """
        results = self.scan()
        candidates = [
            r for r in results.values()
            if r.momentum_score > 15
            and r.rsi < 75           # not overbought
            and r.volume_ratio > 0.3  # minimum liquidity
            and r.price > 5           # no penny stocks
        ]
        candidates.sort(key=lambda x: x.momentum_score, reverse=True)

        picks = candidates[:top_n]
        if picks:
            logger.info(
                f"[SCREENER] Short-term top {len(picks)}: "
                + ", ".join(f"{p.ticker}({p.momentum_score:.0f})" for p in picks[:5])
                + ("..." if len(picks) > 5 else "")
            )
        return picks

    def get_mid_term_picks(self, top_n: int = 12) -> list[ScreenResult]:
        """
        Top trend candidates for mid-term sleeve.
        Filters: confirmed trend, healthy RSI, decent volume.
        """
        results = self.scan()
        candidates = [
            r for r in results.values()
            if r.trend_score > 20
            and r.rsi < 80
            and r.price > 10          # no small caps
            and r.volume_ratio > 0.2
        ]
        candidates.sort(key=lambda x: x.trend_score, reverse=True)

        picks = candidates[:top_n]
        if picks:
            logger.info(
                f"[SCREENER] Mid-term top {len(picks)}: "
                + ", ".join(f"{p.ticker}({p.trend_score:.0f})" for p in picks[:5])
                + ("..." if len(picks) > 5 else "")
            )
        return picks

    def format_picks_for_claude(self, picks: list[ScreenResult]) -> str:
        """Format screener picks as a summary for Claude context."""
        if not picks:
            return "No screener picks available."

        lines = ["## Pre-Screened Candidates (ranked by score):"]
        for i, p in enumerate(picks, 1):
            trend_status = "UP" if p.above_sma20 and p.above_sma50 else (
                "PULLBACK" if p.above_sma50 else "DOWN"
            )
            lines.append(
                f"{i}. {p.ticker}: ${p.price:.2f} ({p.change_pct:+.1f}%) | "
                f"RSI {p.rsi:.0f} | Vol {p.volume_ratio:.1f}x | "
                f"MACD {p.macd_signal} | Trend: {trend_status} | "
                f"ATR ${p.atr:.2f}"
            )
        return "\n".join(lines)