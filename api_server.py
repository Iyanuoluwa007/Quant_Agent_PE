"""
Quant Agent v2.1 -- Read-Only Demo API Server

This API exposes sanitized, read-only data for a demo dashboard.
All live broker integrations, proprietary analytics, and private
data sources have been removed.

Endpoints:
  GET /api/health
  GET /api/status
  GET /api/trades
  GET /api/positions
  GET /api/regime
  GET /api/equity-curve

Run:
  uvicorn api_server:app --host 0.0.0.0 --port 8000
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.resolve()))

TRADES_FILE = Path("trades_demo.json")
HISTORY_FILE = Path("portfolio_history_demo.json")

START_TIME = datetime.now(timezone.utc)

app = FastAPI(
    title="Quant Agent Demo API",
    version="2.1-public"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ===============================================================
# UTILITIES
# ===============================================================

def _load_json(path: Path):

    if not path.exists():
        return []

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


# ===============================================================
# HEALTH
# ===============================================================

@app.get("/api/health")
def health():

    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()

    return {
        "ok": True,
        "version": "2.1-public",
        "uptime_seconds": int(uptime),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


# ===============================================================
# STATUS
# ===============================================================

@app.get("/api/status")
def status():

    trades = _load_json(TRADES_FILE)

    if not isinstance(trades, list):
        trades = []

    executed = [t for t in trades if t.get("status") == "EXECUTED"]

    broker_info = {
        "cash": 50000,
        "total_value": 100000,
        "invested": 50000,
        "positions_count": 2,
        "sleeve_split": {
            "short_term": "30%",
            "mid_term": "40%",
            "long_term": "30%",
        },
    }

    regime_info = {
        "regime": "NORMAL",
        "risk_multiplier": 1.0,
        "description": "Demo market regime state"
    }

    meta_model_info = {
        "confidence_weight": 0.5,
        "mode": "demo"
    }

    return {
        "ok": True,
        "version": "2.1-public",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "total_decisions": len(trades),
        "total_executed": len(executed),
        "last_trade": trades[-1] if trades else None,
        "broker": broker_info,
        "regime": regime_info,
        "meta_model": meta_model_info,
    }


# ===============================================================
# TRADES
# ===============================================================

@app.get("/api/trades")
def recent_trades(
    limit: int = 50,
    sleeve: Optional[str] = None,
):

    trades = _load_json(TRADES_FILE)

    if not isinstance(trades, list):
        trades = []

    if sleeve:
        trades = [t for t in trades if t.get("sleeve") == sleeve]

    return {
        "trades": trades[-limit:],
        "total": len(trades)
    }


# ===============================================================
# POSITIONS
# ===============================================================

@app.get("/api/positions")
def positions():

    positions = {
        "short_term": [
            {"ticker": "DEMO1", "quantity": 10, "avg_price": 100}
        ],
        "mid_term": [
            {"ticker": "DEMO2", "quantity": 5, "avg_price": 120}
        ],
        "long_term": [
            {"ticker": "DEMOETF", "quantity": 20, "avg_price": 90}
        ],
    }

    return {
        "ok": True,
        "positions": positions
    }


# ===============================================================
# REGIME
# ===============================================================

@app.get("/api/regime")
def regime():

    return {
        "ok": True,
        "regime": {
            "regime": "NORMAL",
            "risk_multiplier": 1.0,
            "description": "Demo regime detection output"
        }
    }


# ===============================================================
# EQUITY CURVE
# ===============================================================

@app.get("/api/equity-curve")
def equity_curve(days: int = Query(default=30)):

    history = _load_json(HISTORY_FILE)

    if not isinstance(history, list):
        history = []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filtered = []

    for h in history:

        try:

            ts = datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))

            if ts >= cutoff:

                filtered.append(
                    {
                        "date": h["timestamp"][:16],
                        "value": h.get("total_value", 0),
                        "cash": h.get("cash", 0),
                        "invested": h.get("invested", 0),
                        "positions": h.get("positions_count", 0),
                    }
                )

        except Exception:
            continue

    return {
        "ok": True,
        "curve": filtered,
        "total_snapshots": len(history),
    }