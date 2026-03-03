# Quant Agent v2.1 -- Public Edition

Multi-strategy AI trading agent with regime-aware risk management, confidence calibration, and quantitative portfolio construction. Built for US equities via simulated broker (production version uses Alpaca).

> **Public Edition (QA-PE):** This is the sanitized showcase version. Production edge logic, proprietary prompts, exact risk calibration, and real broker adapters are not included. The architecture, quantitative modules, and intelligence layer are fully functional.

---

## Architecture

```
                    +------------------+
                    |   Market Hours   |
                    |      Gate        |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Market Screener |
                    | 250+ tickers/15m |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v-----+  +-----v------+
     | Short-Term |  |  Mid-Term  |  |  Long-Term |
     | Momentum   |  |   Trend    |  |  ETF DCA   |
     | 1-3 days   |  |  2-8 wks   |  |  Quarters  |
     +--------+---+  +------+-----+  +-----+------+
              |              |              |
              +--------------+--------------+
                             |
                    +--------v---------+
                    | Regime Detection |
                    | VIX + Realized   |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v-----+  +-----v------+
     |    Risk    |  | Volatility |  |    Beta     |
     |   Engine   |  |  Targeting |  |   Control   |
     +--------+---+  +------+-----+  +-----+------+
              |              |              |
              +--------------+--------------+
                             |
                    +--------v---------+
                    | Intelligence     |
                    | Calibration +    |
                    | Meta-Model       |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v-----+  +-----v------+
     | Execution  |  | Dashboard  |  |   Email    |
     | Sim Broker |  |  Next.js   |  | Notifier   |
     +------------+  +------------+  +------------+
```

---

## Features

### Three Independent Strategy Sleeves

Capital is dynamically allocated across sleeves based on account size:

| Account Size | Short-Term | Mid-Term | Long-Term |
|-------------|-----------|---------|----------|
| < $500      | 0%        | 5%      | 95%      |
| $500-1K     | 5%        | 15%     | 80%      |
| $1K-2K      | 10%       | 20%     | 70%      |
| $2K-5K      | 15%       | 25%     | 60%      |
| > $5K       | 20%       | 30%     | 50%      |

Small accounts prioritize ETF accumulation. Active trading scales up with capital.

**Short-Term (Momentum):** 1-3 day holds. Screens for RSI oversold bounces, volume spikes (>2x average), MACD bullish crossovers, and price near SMA20 support. Top 12 candidates forwarded to Claude.

**Mid-Term (Trend):** 2-8 week holds. Screens for confirmed uptrends (SMA20 > SMA50), healthy RSI range (40-65), volume confirmation, and pullback entries. Trailing stops for profit protection.

**Long-Term (ETF DCA):** Quarterly rebalancing. Dollar-cost averaging into a diversified ETF portfolio with automatic rebalancing when allocations drift >5% from targets.

### Market Screener

Pre-filters 250+ tickers before Claude analysis to reduce API costs:

**Momentum Score (Short-Term)**
- RSI oversold bounce (RSI < 30): +30 pts
- Volume spike (> 2x average): +25 pts
- MACD bullish crossover: +20 pts
- Price near SMA20 support: +15 pts

**Trend Score (Mid-Term)**
- Price above SMA20 and SMA50: +25 pts
- SMA20 > SMA50 (confirmed uptrend): +20 pts
- RSI in healthy range (40-65): +20 pts
- Volume confirmation: +20 pts

Universe: S&P 500 top 100 + Nasdaq 100 + value/dividend names. Results cached for 15 minutes. Falls back to static watchlists if scanning fails.

### Risk Architecture

LLM outputs never bypass risk rules. All trades must pass deterministic checks.

**Global Checks (Every Trade)**

| Check | Limit |
|-------|-------|
| Daily trade count | 15 max |
| Global daily loss | 2% of portfolio |
| Per-sleeve daily loss | 3% short / 4% mid / 6% long |
| Total exposure | 80% max invested |
| Cash reserve | 15% minimum |
| Sector concentration | 35% max per sector |
| Correlation overlap | Max 4 per correlated group |
| Minimum trade value | $5 or 0.5% of portfolio |
| Duplicate detection | Block if pending order exists |
| Confidence threshold | 30% short / 20% mid-long |

**Drawdown Kill Switch:** Trading halts if drawdown exceeds -20% from peak. Email alert sent. Manual unlock required:
```bash
python monitor.py --unlock
```

**Position Sizing:**
- ATR-based (short/mid): Risk 1-2% per trade, stop at 1.5-2.5x ATR
- Kelly (optional): Quarter-Kelly, capped at 20% of sleeve
- Fixed fractional (long): Percentage of sleeve per ETF

### Regime Detection

Four market regimes based on VIX + realized volatility composite:

| Regime | VIX Range | Risk Multiplier | Behavior |
|--------|----------|----------------|----------|
| LOW_VOL | < 15 | 1.2x | Slightly increase exposure |
| NORMAL | 15-25 | 1.0x | Standard risk parameters |
| HIGH_VOL | 25-35 | 0.6x | Reduce positions, tighten stops |
| CRISIS | > 35 | 0.3x | Defensive, long-term sleeve only |

Regime adjustments automatically modify sleeve allocations, position sizes, and beta targets.

### Volatility Targeting

Targets 12% annualized portfolio volatility using EWMA (20-day half-life). Exposure scalar ranges from 0.20 to 1.00 -- when realized vol is high, the system automatically reduces position sizes.

### Portfolio Beta Control

Rolling 60-day beta vs SPY with regime-specific targets:

| Regime | Beta Range |
|--------|-----------|
| CRISIS | 0.2 - 0.6 |
| HIGH_VOL | 0.4 - 0.8 |
| NORMAL | 0.6 - 1.2 |
| LOW_VOL | 0.8 - 1.3 |

When portfolio beta drifts outside range, the system suggests adjustments (reduce high-beta, add defensive positions).

### Intelligence Layer

**Confidence Calibration:** Records every Claude prediction (ticker, confidence, entry, stop, target, regime). On exit, resolves whether target or stop was hit. Builds calibration curves in 10% bins. Tracks Brier score and per-sleeve/regime accuracy.

**Meta-Model:** Dynamically adjusts Claude's influence based on historical accuracy:

| Trust Level | Claude Weight | Position Multiplier |
|------------|--------------|-------------------|
| High | 85% | 1.0x |
| Moderate | 65% | 0.75x |
| Low | 40% | 0.5x |
| Minimal | 20% | 0.25x |

If Claude's recent accuracy drops below thresholds, the meta-model automatically reduces position sizes and increases reliance on quantitative signals.

**Accuracy Tracker:** Tracks direction correctness, target/stop hit rates, average hold days, and performance by sleeve and regime.

### Quarterly ETF Review

The long-term sleeve uses a fixed ETF lineup, but the agent automatically reviews performance every 90 days and suggests changes. All changes require user approval.

**How It Works:**
1. Agent checks: last review > 90 days ago? Run Claude analysis
2. Fetch 3mo/6mo/1y performance for all 8 ETFs + benchmarks
3. Claude evaluates: KEEP / SWAP / REDUCE / INCREASE per ETF
4. If >30% of tickers have no data, skip analysis and email DATA ISSUE alert
5. Save recommendations to pending file
6. Send email notification

**User Approval:**
```bash
python etf_review.py --pending     # View suggestions
python etf_review.py --approve     # y/n each change individually
python etf_review.py --history     # Past reviews
python etf_review.py --clear       # Revert to defaults
```

**Safety:**
- Conservative by default -- Claude is told to favour KEEP for core index funds
- Individual approval -- each change needs its own y/n
- Data quality gate -- if >30% of tickers return no data, analysis is skipped
- Auto-sell on swap -- approved swaps queue sell orders, executed next cycle
- Easy revert -- delete `etf_overrides.json` to return to defaults

### Email Notifications

Alerts without checking logs. No Claude API cost -- reads local data only.

- **Daily Summary** (9 PM UK, Mon-Fri): Trade count, P&L, positions, risk state
- **ETF Review Alert:** When quarterly review proposes changes
- **Kill Switch Alert:** When drawdown exceeds threshold
- **Error Alerts:** Critical failures

### Market Hours Gate

Skips cycles when US markets are closed to save Claude API costs. Pre-market buffer (default 30 min before open) allows analysis before trading begins.

### Walk-Forward Backtester

Validates strategies against historical data with realistic simulation:
- Momentum and trend-following strategies
- ATR-based position sizing
- Transaction costs and slippage modelling
- Sharpe, Sortino, Calmar ratios
- Max drawdown and profit factor
- Win rate by strategy

---

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/quant-agent-v2.1.git
cd quant-agent-v2.1

# Setup
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env -- add ANTHROPIC_API_KEY at minimum

# Run (simulated broker, $100K paper capital)
python run.py --status             # Check everything works
python run.py --once               # Single analysis cycle
python run.py --backtest           # Run historical backtests
python run.py                      # Continuous mode

# Reset simulated broker
python run.py --reset 50000        # Start with $50K instead

# Monitor
python monitor.py --check          # Snapshot + drawdown check
python monitor.py --report daily   # Daily performance
python monitor.py --unlock         # Deactivate kill switch

# ETF Review
python etf_review.py --pending     # View pending changes
python etf_review.py --approve     # Approve/reject each change

# Tests
python -m pytest tests/ -v
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev                        # http://localhost:3000
```

Read-only Next.js 14 dashboard: equity curve, allocation pie chart, positions table, calibration display, regime panel, meta-model state, recent trades, sleeve comparison.

API server (for dashboard):
```bash
uvicorn api_server:app --port 8000
```

---

## Project Structure

```
quant-agent-v2.1/
├── agent.py                 # Main orchestrator (market hours, regime, execution)
├── config.py                # All configuration (dynamic allocation, risk limits)
├── run.py                   # CLI launcher
├── broker_adapter.py        # Simulated broker (paper trading)
├── screener.py              # Market scanner (250+ tickers, momentum + trend)
├── market_data.py           # Yahoo Finance data formatting for Claude
├── monitor.py               # Portfolio monitor + drawdown kill switch
├── etf_review.py            # Quarterly ETF review with approval CLI
├── notifications.py         # Email alerts (daily summary, kill switch, errors)
├── api_server.py            # FastAPI endpoints for dashboard
├── dashboard_cli.py         # Terminal-based dashboard
│
├── risk/                    # Deterministic risk engine
│   ├── global_risk.py       # Trade approval + daily limits
│   ├── position_sizing.py   # ATR, Kelly, fixed fractional
│   ├── regime_detection.py  # VIX + realized vol, 4 regimes
│   ├── volatility_target.py # 12% annualized vol target, EWMA
│   └── beta_control.py      # Portfolio beta vs SPY
│
├── intelligence/            # AI confidence tracking
│   ├── calibration.py       # Prediction recording + calibration curves
│   ├── meta_model.py        # Dynamic Claude weight adjustment
│   └── accuracy_tracker.py  # Direction/target/stop hit rates
│
├── strategies/              # Three independent sleeves
│   ├── short_term.py        # Momentum (1-3 day holds)
│   ├── mid_term.py          # Trend (2-8 week holds)
│   └── long_term.py         # ETF DCA + rebalance
│
├── quant/                   # Quantitative analysis
│   └── backtester.py        # Walk-forward engine, Sharpe/Sortino/Calmar
│
├── dashboard/               # Next.js 14 read-only dashboard
│   ├── app/
│   │   ├── page.tsx         # Single-page dashboard
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── lib/api.ts
│   ├── package.json
│   └── ...config files
│
├── deploy/                  # Deployment scripts
│   ├── setup_vps.sh         # Hetzner VPS provisioning (systemd)
│   └── run_agent.bat        # Windows Task Scheduler
│
├── tests/
│   └── test_risk_and_intelligence.py
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Automated Scheduling

### Windows (Task Scheduler)

```
schtasks /create /tn "Quant Agent" /tr "C:\path\run_agent.bat" /sc daily /st 09:00 /ri 180 /du 12:00 /f
```

| Run | UK Time | Markets |
|-----|---------|---------|
| 1 | 09:00 | Pre-market analysis |
| 2 | 14:30 | US market open |
| 3 | 18:00 | US afternoon session |
| 4 | 21:00 | End of day / daily summary |

### Linux VPS (systemd)

```bash
bash deploy/setup_vps.sh
```

Services: `trading-bot` (agent loop), `trading-api` (dashboard), `trading-monitor.timer` (hourly snapshots).

---

## Configuration

All parameters are in `config.py` with environment variable overrides in `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKER` | `simulated` | `simulated` or `alpaca` |
| `INITIAL_CAPITAL` | `100000` | Starting capital for simulated broker |
| `MARKET_HOURS_ONLY` | `true` | Skip cycles when markets closed |
| `PRE_MARKET_BUFFER_MIN` | `30` | Minutes before open to start analysis |
| `KILL_SWITCH_DRAWDOWN_PCT` | `20.0` | Halt trading at this drawdown |
| `VOL_TARGET_PCT` | `12.0` | Target annualized volatility |
| `EMAIL_ENABLED` | `false` | Enable email notifications |

---

## Public Edition vs Production

This is the public showcase version. Key differences:

| Feature | Public Edition | Production |
|---------|---------------|-----------|
| Broker | Simulated adapter | Alpaca + Trading212 |
| Watchlists | Subset (12-17 tickers) | Full universe (250+) |
| Claude prompts | Simplified | Proprietary, calibrated |
| Risk parameters | Example values | Tuned to portfolio |
| ETF review | Framework + CLI | Multi-broker, auto-notify |
| Allocation logic | Dynamic split | Additional factors |

---

## Technical Highlights

- **Zero trust in LLM outputs:** Every trade passes deterministic risk checks regardless of Claude's confidence level
- **Regime-adaptive:** Position sizes, beta targets, sleeve allocations, and stop distances all adjust to market conditions
- **Self-correcting AI:** Meta-model tracks Claude's accuracy and automatically reduces influence when performance degrades
- **Cost-efficient:** Market hours gate + screener pre-filter minimize Claude API calls
- **Walk-forward validation:** Backtester prevents overfitting by testing on out-of-sample data

---

## Risk Disclosure

Trading involves significant risk of loss. Past performance does not guarantee future results. AI models can be wrong or inconsistent. Market gaps can bypass stop logic. Deploy only capital you can afford to lose.

## License

MIT License -- use at your own risk.

---

## Attribution

```text
Built using Quant Agent(QA_PE) v2 by Iyanuoluwa Oke
https://github.com/Iyanuoluwa007/Quant_Agent_PE.git
```