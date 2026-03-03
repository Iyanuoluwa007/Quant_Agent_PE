"""
Historical Backtester
Walk-forward backtesting engine for strategy validation.

Features:
- Configurable lookback period and walk-forward windows
- Transaction cost and slippage modeling
- Per-sleeve and aggregate performance metrics
- Regime-conditional analysis
- Equity curve generation for dashboard visualization

Usage:
    python -m quant.backtester --strategy momentum --period 1y
    python -m quant.backtester --strategy trend --period 2y --slippage 0.1
"""
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

TRADING_DAYS = 252


@dataclass
class BacktestTrade:
    """Single trade in backtest."""
    ticker: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: float
    side: str                # BUY or SELL
    pnl: float
    pnl_pct: float
    hold_days: int
    sleeve: str
    signal_type: str         # momentum, trend, rebalance, etc.


@dataclass
class BacktestResult:
    """Complete backtest result with performance metrics."""
    strategy_name: str
    period_start: str
    period_end: str
    initial_capital: float
    final_value: float
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    avg_trade_pnl: float
    total_trades: int
    avg_hold_days: float
    exposure_pct: float           # % of time with positions
    equity_curve: list[dict]      # [{date, value, drawdown}]
    trades: list[BacktestTrade]
    monthly_returns: dict         # {YYYY-MM: return_pct}
    regime_performance: dict      # {regime: {return, sharpe, trades}}

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "period": f"{self.period_start} to {self.period_end}",
            "initial_capital": self.initial_capital,
            "final_value": round(self.final_value, 2),
            "total_return": f"{self.total_return_pct:.2f}%",
            "annualized_return": f"{self.annualized_return_pct:.2f}%",
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "max_drawdown": f"{self.max_drawdown_pct:.2f}%",
            "calmar_ratio": round(self.calmar_ratio, 3),
            "win_rate": f"{self.win_rate:.1f}%",
            "profit_factor": round(self.profit_factor, 2),
            "total_trades": self.total_trades,
            "avg_hold_days": round(self.avg_hold_days, 1),
        }

    def summary(self) -> str:
        lines = [
            f"Backtest: {self.strategy_name}",
            f"Period: {self.period_start} to {self.period_end}",
            f"Initial: ${self.initial_capital:,.2f} -> Final: ${self.final_value:,.2f}",
            f"Return: {self.total_return_pct:+.2f}% (Ann: {self.annualized_return_pct:+.2f}%)",
            f"Sharpe: {self.sharpe_ratio:.3f} | Sortino: {self.sortino_ratio:.3f}",
            f"Max DD: {self.max_drawdown_pct:.2f}% | Calmar: {self.calmar_ratio:.3f}",
            f"Win Rate: {self.win_rate:.1f}% | Profit Factor: {self.profit_factor:.2f}",
            f"Trades: {self.total_trades} | Avg Hold: {self.avg_hold_days:.1f} days",
        ]
        return "\n  ".join(lines)


class BacktestEngine:
    """
    Walk-forward backtesting engine.

    Supports multiple signal generators (momentum, trend, mean-reversion)
    applied to historical data with realistic execution modeling.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        transaction_cost_pct: float = 0.0,     # Alpaca: commission-free
        slippage_pct: float = 0.05,             # 5 bps slippage estimate
        max_positions: int = 10,
        risk_per_trade_pct: float = 2.0,
    ):
        self.initial_capital = initial_capital
        self.tx_cost_pct = transaction_cost_pct
        self.slippage_pct = slippage_pct
        self.max_positions = max_positions
        self.risk_per_trade = risk_per_trade_pct

    def run_momentum_backtest(
        self,
        tickers: list[str],
        period: str = "2y",
        rsi_entry: float = 30.0,
        rsi_exit: float = 70.0,
        hold_limit: int = 3,
    ) -> BacktestResult:
        """
        Backtest short-term momentum strategy.
        Entry: RSI < rsi_entry with volume spike
        Exit: RSI > rsi_exit or hold_limit days
        """
        logger.info(f"[BACKTEST] Momentum: {len(tickers)} tickers, period={period}")
        data = self._fetch_data(tickers, period)
        if data is None:
            return self._empty_result("momentum")

        capital = self.initial_capital
        positions: dict[str, dict] = {}
        trades: list[BacktestTrade] = []
        equity_curve: list[dict] = []
        daily_returns: list[float] = []

        dates = data.index
        prev_equity = capital

        for i, date in enumerate(dates):
            if i < 20:
                continue

            # Calculate portfolio value
            position_value = sum(
                p["qty"] * float(data.loc[date, (p["ticker"], "Close")])
                for p in positions.values()
                if (p["ticker"], "Close") in data.columns
            )
            total_value = capital + position_value
            daily_ret = (total_value - prev_equity) / prev_equity if prev_equity > 0 else 0
            daily_returns.append(daily_ret)
            prev_equity = total_value

            equity_curve.append({
                "date": str(date.date()) if hasattr(date, "date") else str(date),
                "value": round(total_value, 2),
            })

            # Check exits first
            tickers_to_close = []
            for ticker, pos in positions.items():
                try:
                    current_price = float(data.loc[date, (ticker, "Close")])
                    hold_days = (date - pd.Timestamp(pos["entry_date"])).days
                    close_data = data[(ticker, "Close")].iloc[max(0, i-14):i+1]
                    rsi = self._calc_rsi(close_data.values)

                    if rsi > rsi_exit or hold_days >= hold_limit:
                        exit_price = current_price * (1 - self.slippage_pct / 100)
                        pnl = (exit_price - pos["entry_price"]) * pos["qty"]
                        pnl -= abs(exit_price * pos["qty"]) * (self.tx_cost_pct / 100)

                        trades.append(BacktestTrade(
                            ticker=ticker,
                            entry_date=str(pos["entry_date"]),
                            exit_date=str(date),
                            entry_price=pos["entry_price"],
                            exit_price=round(exit_price, 2),
                            quantity=pos["qty"],
                            side="BUY",
                            pnl=round(pnl, 2),
                            pnl_pct=round((exit_price / pos["entry_price"] - 1) * 100, 2),
                            hold_days=hold_days,
                            sleeve="short_term",
                            signal_type="momentum_exit",
                        ))
                        capital += pos["qty"] * exit_price
                        tickers_to_close.append(ticker)
                except (KeyError, IndexError):
                    continue

            for t in tickers_to_close:
                del positions[t]

            # Check entries
            if len(positions) >= self.max_positions:
                continue

            for ticker in tickers:
                if ticker in positions:
                    continue
                if len(positions) >= self.max_positions:
                    break

                try:
                    close_series = data[(ticker, "Close")].iloc[max(0, i-20):i+1]
                    vol_series = data[(ticker, "Volume")].iloc[max(0, i-20):i+1]

                    if len(close_series) < 15:
                        continue

                    rsi = self._calc_rsi(close_series.values)
                    avg_vol = vol_series.iloc[:-1].mean()
                    curr_vol = vol_series.iloc[-1]
                    vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

                    if rsi < rsi_entry and vol_ratio > 1.5:
                        current_price = float(close_series.iloc[-1])
                        entry_price = current_price * (1 + self.slippage_pct / 100)

                        risk_amount = total_value * (self.risk_per_trade / 100)
                        atr = self._calc_atr_series(data, ticker, i)
                        stop_distance = atr * 1.5 if atr > 0 else current_price * 0.02
                        qty = risk_amount / stop_distance if stop_distance > 0 else 0
                        qty = min(qty, (total_value * 0.15) / entry_price)

                        if qty > 0 and entry_price * qty <= capital:
                            capital -= entry_price * qty
                            capital -= abs(entry_price * qty) * (self.tx_cost_pct / 100)
                            positions[ticker] = {
                                "ticker": ticker,
                                "entry_price": round(entry_price, 2),
                                "entry_date": date,
                                "qty": round(qty, 4),
                            }
                except (KeyError, IndexError):
                    continue

        # Close remaining positions at end
        last_date = dates[-1]
        for ticker, pos in positions.items():
            try:
                exit_price = float(data.loc[last_date, (ticker, "Close")])
                pnl = (exit_price - pos["entry_price"]) * pos["qty"]
                hold_days = (last_date - pd.Timestamp(pos["entry_date"])).days
                trades.append(BacktestTrade(
                    ticker=ticker, entry_date=str(pos["entry_date"]),
                    exit_date=str(last_date), entry_price=pos["entry_price"],
                    exit_price=round(exit_price, 2), quantity=pos["qty"],
                    side="BUY", pnl=round(pnl, 2),
                    pnl_pct=round((exit_price / pos["entry_price"] - 1) * 100, 2),
                    hold_days=hold_days, sleeve="short_term",
                    signal_type="backtest_close",
                ))
                capital += pos["qty"] * exit_price
            except (KeyError, IndexError):
                continue

        final_value = capital
        return self._compute_metrics(
            "momentum", trades, equity_curve, daily_returns, final_value, dates
        )

    def run_trend_backtest(
        self,
        tickers: list[str],
        period: str = "2y",
        sma_fast: int = 20,
        sma_slow: int = 50,
    ) -> BacktestResult:
        """
        Backtest mid-term trend-following strategy.
        Entry: SMA20 crosses above SMA50, RSI 40-65
        Exit: SMA20 crosses below SMA50 or trailing stop
        """
        logger.info(f"[BACKTEST] Trend: {len(tickers)} tickers, period={period}")
        data = self._fetch_data(tickers, period)
        if data is None:
            return self._empty_result("trend")

        capital = self.initial_capital
        positions: dict[str, dict] = {}
        trades: list[BacktestTrade] = []
        equity_curve: list[dict] = []
        daily_returns: list[float] = []

        dates = data.index
        prev_equity = capital

        for i, date in enumerate(dates):
            if i < sma_slow + 5:
                continue

            position_value = sum(
                p["qty"] * float(data.loc[date, (p["ticker"], "Close")])
                for p in positions.values()
                if (p["ticker"], "Close") in data.columns
            )
            total_value = capital + position_value
            daily_ret = (total_value - prev_equity) / prev_equity if prev_equity > 0 else 0
            daily_returns.append(daily_ret)
            prev_equity = total_value

            equity_curve.append({
                "date": str(date.date()) if hasattr(date, "date") else str(date),
                "value": round(total_value, 2),
            })

            # Check exits
            tickers_to_close = []
            for ticker, pos in positions.items():
                try:
                    close_series = data[(ticker, "Close")].iloc[:i+1]
                    current_price = float(close_series.iloc[-1])
                    sma_f = close_series.rolling(sma_fast).mean().iloc[-1]
                    sma_s = close_series.rolling(sma_slow).mean().iloc[-1]

                    # Trailing stop
                    pos["peak"] = max(pos.get("peak", current_price), current_price)
                    trailing_stop = pos["peak"] * 0.96  # 4% trailing

                    if sma_f < sma_s or current_price < trailing_stop:
                        exit_price = current_price * (1 - self.slippage_pct / 100)
                        pnl = (exit_price - pos["entry_price"]) * pos["qty"]
                        hold_days = (date - pd.Timestamp(pos["entry_date"])).days
                        trades.append(BacktestTrade(
                            ticker=ticker, entry_date=str(pos["entry_date"]),
                            exit_date=str(date), entry_price=pos["entry_price"],
                            exit_price=round(exit_price, 2), quantity=pos["qty"],
                            side="BUY", pnl=round(pnl, 2),
                            pnl_pct=round((exit_price / pos["entry_price"] - 1) * 100, 2),
                            hold_days=hold_days, sleeve="mid_term",
                            signal_type="trend_exit",
                        ))
                        capital += pos["qty"] * exit_price
                        tickers_to_close.append(ticker)
                except (KeyError, IndexError):
                    continue

            for t in tickers_to_close:
                del positions[t]

            # Check entries
            for ticker in tickers:
                if ticker in positions or len(positions) >= self.max_positions:
                    continue
                try:
                    close_series = data[(ticker, "Close")].iloc[:i+1]
                    if len(close_series) < sma_slow + 1:
                        continue

                    sma_f = close_series.rolling(sma_fast).mean()
                    sma_s = close_series.rolling(sma_slow).mean()
                    rsi = self._calc_rsi(close_series.values[-15:])

                    # Golden cross + healthy RSI
                    if (sma_f.iloc[-1] > sma_s.iloc[-1] and
                        sma_f.iloc[-2] <= sma_s.iloc[-2] and
                        40 <= rsi <= 65):

                        current_price = float(close_series.iloc[-1])
                        entry_price = current_price * (1 + self.slippage_pct / 100)
                        risk_amount = total_value * (self.risk_per_trade / 100)
                        atr = self._calc_atr_series(data, ticker, i)
                        stop_distance = atr * 2.5 if atr > 0 else current_price * 0.05
                        qty = risk_amount / stop_distance if stop_distance > 0 else 0
                        qty = min(qty, (total_value * 0.20) / entry_price)

                        if qty > 0 and entry_price * qty <= capital:
                            capital -= entry_price * qty
                            positions[ticker] = {
                                "ticker": ticker,
                                "entry_price": round(entry_price, 2),
                                "entry_date": date,
                                "qty": round(qty, 4),
                                "peak": entry_price,
                            }
                except (KeyError, IndexError):
                    continue

        # Close remaining
        last_date = dates[-1]
        for ticker, pos in list(positions.items()):
            try:
                exit_price = float(data.loc[last_date, (ticker, "Close")])
                pnl = (exit_price - pos["entry_price"]) * pos["qty"]
                hold_days = (last_date - pd.Timestamp(pos["entry_date"])).days
                trades.append(BacktestTrade(
                    ticker=ticker, entry_date=str(pos["entry_date"]),
                    exit_date=str(last_date), entry_price=pos["entry_price"],
                    exit_price=round(exit_price, 2), quantity=pos["qty"],
                    side="BUY", pnl=round(pnl, 2),
                    pnl_pct=round((exit_price / pos["entry_price"] - 1) * 100, 2),
                    hold_days=hold_days, sleeve="mid_term",
                    signal_type="backtest_close",
                ))
                capital += pos["qty"] * exit_price
            except (KeyError, IndexError):
                continue

        final_value = capital
        return self._compute_metrics(
            "trend", trades, equity_curve, daily_returns, final_value, dates
        )

    # ── DATA FETCHING ─────────────────────────────────────────────

    def _fetch_data(
        self, tickers: list[str], period: str
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for multiple tickers."""
        try:
            ticker_str = " ".join(tickers)
            data = yf.download(
                ticker_str, period=period, interval="1d",
                group_by="ticker", progress=False, threads=True,
            )
            if data is None or data.empty:
                logger.error("[BACKTEST] No data returned")
                return None
            return data
        except Exception as e:
            logger.error(f"[BACKTEST] Data fetch failed: {e}")
            return None

    # ── INDICATORS ────────────────────────────────────────────────

    def _calc_rsi(self, prices, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - (100 / (1 + rs)))

    def _calc_atr_series(self, data, ticker: str, idx: int, period: int = 14) -> float:
        try:
            high = data[(ticker, "High")].iloc[max(0, idx-period):idx+1].values
            low = data[(ticker, "Low")].iloc[max(0, idx-period):idx+1].values
            close = data[(ticker, "Close")].iloc[max(0, idx-period):idx+1].values
            if len(high) < 2:
                return 0.0
            tr_vals = []
            for j in range(1, len(high)):
                tr = max(
                    float(high[j]) - float(low[j]),
                    abs(float(high[j]) - float(close[j-1])),
                    abs(float(low[j]) - float(close[j-1])),
                )
                tr_vals.append(tr)
            return sum(tr_vals) / len(tr_vals) if tr_vals else 0.0
        except Exception:
            return 0.0

    # ── METRICS COMPUTATION ───────────────────────────────────────

    def _compute_metrics(
        self,
        name: str,
        trades: list[BacktestTrade],
        equity_curve: list[dict],
        daily_returns: list[float],
        final_value: float,
        dates: pd.DatetimeIndex,
    ) -> BacktestResult:
        """Compute all performance metrics from backtest data."""
        total_return = (final_value / self.initial_capital - 1) * 100
        days = (dates[-1] - dates[0]).days if len(dates) > 1 else 1
        years = days / 365.25
        ann_return = ((final_value / self.initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

        returns_arr = np.array(daily_returns) if daily_returns else np.array([0])
        rf_daily = 0.04 / 252   # 4% risk-free rate

        # Sharpe ratio
        excess = returns_arr - rf_daily
        sharpe = (np.mean(excess) / np.std(excess) * math.sqrt(252)) if np.std(excess) > 0 else 0

        # Sortino ratio (only penalize downside deviation)
        downside = excess[excess < 0]
        downside_std = np.std(downside) if len(downside) > 0 else np.std(excess)
        sortino = (np.mean(excess) / downside_std * math.sqrt(252)) if downside_std > 0 else 0

        # Max drawdown
        max_dd = self._max_drawdown(equity_curve)

        # Calmar ratio
        calmar = ann_return / abs(max_dd) if max_dd != 0 else 0

        # Trade statistics
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        win_rate = (len(winning) / len(trades) * 100) if trades else 0
        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        avg_pnl = sum(t.pnl for t in trades) / len(trades) if trades else 0
        avg_hold = sum(t.hold_days for t in trades) / len(trades) if trades else 0

        # Exposure
        days_with_positions = sum(1 for e in equity_curve if e["value"] != self.initial_capital)
        exposure = (days_with_positions / len(equity_curve) * 100) if equity_curve else 0

        # Monthly returns
        monthly = self._monthly_returns(equity_curve)

        # Compute drawdown for each point in equity curve
        peak = 0
        for point in equity_curve:
            peak = max(peak, point["value"])
            dd = ((point["value"] - peak) / peak * 100) if peak > 0 else 0
            point["drawdown"] = round(dd, 2)

        period_start = equity_curve[0]["date"] if equity_curve else ""
        period_end = equity_curve[-1]["date"] if equity_curve else ""

        return BacktestResult(
            strategy_name=name,
            period_start=period_start,
            period_end=period_end,
            initial_capital=self.initial_capital,
            final_value=round(final_value, 2),
            total_return_pct=round(total_return, 2),
            annualized_return_pct=round(ann_return, 2),
            sharpe_ratio=round(sharpe, 3),
            sortino_ratio=round(sortino, 3),
            max_drawdown_pct=round(max_dd, 2),
            calmar_ratio=round(calmar, 3),
            win_rate=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            avg_trade_pnl=round(avg_pnl, 2),
            total_trades=len(trades),
            avg_hold_days=round(avg_hold, 1),
            exposure_pct=round(exposure, 1),
            equity_curve=equity_curve,
            trades=trades,
            monthly_returns=monthly,
            regime_performance={},
        )

    def _max_drawdown(self, curve: list[dict]) -> float:
        if not curve:
            return 0.0
        peak = 0
        max_dd = 0
        for point in curve:
            v = point["value"]
            peak = max(peak, v)
            dd = ((v - peak) / peak * 100) if peak > 0 else 0
            max_dd = min(max_dd, dd)
        return max_dd

    def _monthly_returns(self, curve: list[dict]) -> dict:
        if not curve:
            return {}
        monthly = {}
        prev_month_end = None
        for point in curve:
            month = point["date"][:7]  # YYYY-MM
            if month not in monthly:
                if prev_month_end is not None:
                    ret = (point["value"] / prev_month_end - 1) * 100
                    monthly[month] = round(ret, 2)
                prev_month_end = point["value"]
            else:
                prev_month_end = point["value"]
        return monthly

    def _empty_result(self, name: str) -> BacktestResult:
        return BacktestResult(
            strategy_name=name, period_start="", period_end="",
            initial_capital=self.initial_capital,
            final_value=self.initial_capital,
            total_return_pct=0, annualized_return_pct=0,
            sharpe_ratio=0, sortino_ratio=0, max_drawdown_pct=0,
            calmar_ratio=0, win_rate=0, profit_factor=0,
            avg_trade_pnl=0, total_trades=0, avg_hold_days=0,
            exposure_pct=0, equity_curve=[], trades=[],
            monthly_returns={}, regime_performance={},
        )
