# Quant Agent v2.1 - Public Edition

Multi‑strategy AI trading agent demonstrating a modular architecture for
quantitative research, AI‑assisted analysis, and automated portfolio
monitoring.

This **Public Edition (QA‑PE)** is a sanitized showcase version intended
for engineering demonstration and portfolio purposes. Certain components
such as proprietary signals, calibrated thresholds, production broker
integrations, and optimized portfolio parameters are intentionally
omitted or simplified.

The goal of this repository is to demonstrate **systems architecture, AI
integration, and quantitative engineering practices** without exposing
proprietary trading logic.

---

# System Architecture

                        +------------------+
                        |   Market Hours   |
                        |      Gate        |
                        +--------+---------+
                                 |
                        +--------v---------+
                        |  Market Screener |
                        | Periodic scans   |
                        +--------+---------+
                                 |
                  +--------------+--------------+
                  |              |              |
         +--------v---+  +------v-----+  +-----v------+
         | Short-Term |  |  Mid-Term  |  |  Long-Term |
         | Momentum   |  |   Trend    |  | Portfolio  |
         | Signals    |  |   Signals  |  | Allocation |
         +--------+---+  +------+-----+  +-----+------+
                  |              |              |
                  +--------------+--------------+
                                 |
                        +--------v---------+
                        | Regime Detection |
                        | Market Volatility|
                        +--------+---------+
                                 |
                  +--------------+--------------+
                  |              |              |
         +--------v---+  +------v-----+  +-----v------+
         |    Risk    |  | Volatility |  |    Beta     |
         |   Engine   |  | Management |  | Monitoring  |
         +--------+---+  +------+-----+  +-----+------+
                  |              |              |
                  +--------------+--------------+
                                 |
                        +--------v---------+
                        | Intelligence     |
                        | Calibration +    |
                        | Meta‑Model       |
                        +--------+---------+
                                 |
                  +--------------+--------------+
                  |              |              |
         +--------v---+  +------v-----+  +-----v------+
         | Execution  |  | Dashboard  |  | Notification|
         | Sim Broker |  |  Next.js   |  | System      |
         +------------+  +------------+  +-------------+

------------------------------------------------------------------------

# Core Concepts

## Multi‑Strategy Portfolio

The agent organizes trading logic into **independent strategy sleeves**
operating on different time horizons:

• Short‑term momentum signals\
• Mid‑term trend signals\
• Long‑term portfolio allocation

Capital distribution dynamically adapts based on **account
characteristics and market volatility regimes**.\
Specific allocation formulas and thresholds are intentionally excluded
from this public version.

------------------------------------------------------------------------

## Market Screening Layer

Before AI analysis occurs, the system performs **quantitative
pre‑filtering** across a filtered universe of liquid assets.

The screener evaluates multiple factors such as:

• volatility behaviour\
• momentum structure\
• volume expansion\
• trend confirmation\
• mean‑reversion signals

This filtering layer significantly reduces the number of assets
evaluated by the AI model and improves computational efficiency.

Specific scoring functions and thresholds are intentionally removed in
the public version.

------------------------------------------------------------------------

## Deterministic Risk Engine

A core design principle of Quant Agent is:

> **LLM outputs never bypass deterministic risk rules.**

Every trade recommendation is validated against a dedicated risk engine
responsible for:

• exposure management\
• position sizing\
• sector diversification\
• drawdown protection\
• trade frequency control\
• correlation management

Exact parameter values and limits are omitted in the public edition.

------------------------------------------------------------------------

## Market Regime Detection

The system continuously evaluates the market environment using
volatility‑based indicators.

Detected regimes influence:

• exposure levels\
• position sizing behaviour\
• portfolio beta targets\
• capital allocation across strategies

The specific classification thresholds used in the production system are
not included in this repository.

------------------------------------------------------------------------

## Volatility & Beta Management

Portfolio risk is dynamically managed using statistical risk estimation
methods including:

• exponentially weighted volatility estimation\
• adaptive exposure scaling\
• benchmark beta monitoring

These controls help maintain consistent portfolio behaviour across
varying market environments.

Detailed implementation parameters are intentionally excluded.

------------------------------------------------------------------------

# Intelligence Layer

The AI component of the system is designed to **learn from its
historical decision accuracy**.

Key elements include:

### Confidence Calibration

The system records each prediction along with:

• predicted direction\
• confidence score\
• entry and exit outcome

This data is used to build **calibration curves** and evaluate
probabilistic reliability.

### Meta‑Model

A supervisory model dynamically adjusts the influence of AI predictions
depending on recent performance metrics.

When predictive accuracy declines, the system automatically reduces AI
influence and increases reliance on quantitative signals.

### Accuracy Analytics

The system tracks:

• directional accuracy\
• profit‑target hit rates\
• stop‑loss frequency\
• performance by strategy sleeve\
• performance by market regime

------------------------------------------------------------------------

# Long‑Term Portfolio Review

The long‑term sleeve periodically reviews the portfolio composition
using data‑driven analysis.

The review process:

1.  evaluates asset performance across multiple horizons
2.  compares assets against benchmark behaviour
3.  proposes allocation adjustments

All proposed changes require **explicit user approval** before
execution.

------------------------------------------------------------------------

# Engineering Features

The project emphasizes **production‑grade engineering practices** rather
than exposing proprietary alpha signals.

Highlights include:

• modular architecture separating strategies, risk, AI, and execution\
• deterministic safety controls for AI‑generated signals\
• walk‑forward backtesting infrastructure\
• portfolio monitoring and analytics\
• web‑based dashboard for system visibility\
• CLI management tools for monitoring and control

------------------------------------------------------------------------

# Walk‑Forward Backtesting

The repository includes a backtesting framework supporting:

• historical strategy simulation\
• transaction cost modelling\
• risk‑adjusted performance metrics\
• walk‑forward validation to reduce overfitting

Metrics reported include:

• Sharpe ratio\
• Sortino ratio\
• Calmar ratio\
• maximum drawdown\
• strategy win rates

------------------------------------------------------------------------

# Dashboard

The project includes a **read‑only Next.js dashboard** for monitoring
system behaviour.

Dashboard panels include:

• equity curve visualization\
• portfolio allocation view\
• active positions table\
• calibration analytics\
• market regime display\
• AI meta‑model state

------------------------------------------------------------------------

# Quick Start

Clone the repository:

    git clone https://github.com/Iyanuoluwa007/Quant_Agent_PE.git
    cd Quant_Agent_PE

Environment setup:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

Run the system:

    python run.py --status
    python run.py --once
    python run.py

Dashboard:

    cd dashboard
    npm install
    npm run dev

------------------------------------------------------------------------

# Project Structure

    quant-agent/
    │
    ├── agent.py
    ├── run.py
    ├── config.py
    ├── broker_adapter.py
    ├── market_data.py
    ├── screener.py
    ├── monitor.py
    ├── notifications.py
    │
    ├── risk/
    ├── strategies/
    ├── intelligence/
    ├── quant/
    │
    ├── dashboard/
    ├── deploy/
    ├── tests/
    │
    └── README.md

The architecture separates **strategy logic, risk enforcement, AI
evaluation, and system orchestration** to maintain clear engineering
boundaries.

------------------------------------------------------------------------

# Public Edition vs Production System

  Feature           Public Edition          Production System
  ----------------- ----------------------- ---------------------------------
  Broker            Simulated environment   Live broker integrations
  Signals           Simplified / partial    Proprietary signal models
  Risk parameters   Generic examples        Calibrated portfolio parameters
  Universe size     Reduced                 Full research universe
  AI prompts        Simplified              Tuned and optimized
  Infrastructure    Demonstration           Production deployment

------------------------------------------------------------------------

# Technical Highlights

• Zero‑trust architecture for AI‑generated signals\
• Regime‑adaptive portfolio behaviour\
• AI confidence calibration and self‑correction\
• Modular quant research framework\
• Walk‑forward validation tools\
• Engineering‑focused system design

------------------------------------------------------------------------

# Risk Disclosure

Trading financial markets involves substantial risk.\
This repository is intended for **research and educational purposes
only**.

The public implementation is not intended for live trading and does not
represent financial advice.

------------------------------------------------------------------------

# License

MIT License

------------------------------------------------------------------------

# Attribution

Quant Agent - Public Engineering Showcase\
Developed by **Iyanuoluwa Oke**

GitHub: https://github.com/Iyanuoluwa007

## Feedback

If you explore the project and have suggestions or comments, feedback is welcome:

**Google Form:**  
https://forms.gle/jKDN18pMzP3mCpJU6

Feedback from researchers, engineers, and quantitative developers is especially appreciated.