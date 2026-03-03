"""
Quant Agent v2.1 -- Read-Only API Server
Serves portfolio state, regime info, calibration data, and backtest results
to the Next.js web dashboard.

Endpoints:
  GET /api/health           -- Uptime check
  GET /api/status           -- Full agent status + regime + meta-model
  GET /api/trades           -- Recent trade history
  GET /api/positions        -- Current positions by sleeve
  GET /api/regime           -- Current market regime analysis
  GET /api/calibration      -- Claude calibration report
  GET /api/equity-curve     -- Portfolio history for charting
  GET /api/backtest         -- Latest backtest results

Usage:
  uvicorn api_server:app --host 0.0.0.0 --port 8000
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

TRADES_FILE = Path(os.getenv("TRADE_LOG_FILE", "trades.json"))
HISTORY_FILE = Path("portfolio_history.json")
CALIBRATION_FILE = Path("calibration_data.json")
DASH_TOKEN = os.getenv("DASHBOARD_TOKEN", "")
START_TIME = datetime.now(timezone.utc)

app = FastAPI(title="Quant Agent v2.1 API", version="2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("DASHBOARD_URL", "http://localhost:3000"),
        "https://*.vercel.app",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _auth(token: Optional[str]):
    if not DASH_TOKEN:
        return
    if token != DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _load_json(path: Path) -> list | dict:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


@app.get("/api/health")
def health():
    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()
    return {
        "ok": True,
        "version": "2.1",
        "uptime_seconds": int(uptime),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/status")
def status(x_dashboard_token: Optional[str] = Header(default=None)):
    _auth(x_dashboard_token)
    trades = _load_json(TRADES_FILE)
    if not isinstance(trades, list):
        trades = []

    broker_info = {}
    regime_info = {}
    meta_info = {}
    vol_info = {}

    try:
        from config import TradingConfig
        from alpaca_client import AlpacaClient
        from risk.regime_detection import RegimeDetector
        from risk.volatility_target import VolatilityTargeter
        from intelligence.calibration import CalibrationTracker
        from intelligence.meta_model import MetaModel

        config = TradingConfig()
        client = AlpacaClient(config)
        cash = client.get_account_cash()
        positions = client.get_positions()
        total_value = cash.get("total", 0)
        split = config.get_dynamic_split(total_value)

        broker_info = {
            "cash": cash.get("free", 0),
            "total_value": total_value,
            "invested": cash.get("invested", 0),
            "positions_count": len(positions),
            "sleeve_split": {k: f"{v:.0f}%" for k, v in split.items()},
        }

        detector = RegimeDetector()
        regime = detector.detect()
        regime_info = regime.to_dict()

        targeter = VolatilityTargeter(target_vol_pct=config.VOL_TARGET_PCT)
        vol = targeter.compute()
        vol_info = vol.to_dict()

        calibration = CalibrationTracker()
        meta = MetaModel(calibration)
        meta_state = meta.get_state(regime.regime)
        meta_info = meta_state.to_dict()

    except Exception as e:
        broker_info = {"error": str(e)}

    executed = [t for t in trades if t.get("status") == "EXECUTED"]
    return {
        "ok": True,
        "version": "2.1",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "total_decisions": len(trades),
        "total_executed": len(executed),
        "last_trade": trades[-1] if trades else None,
        "broker": broker_info,
        "regime": regime_info,
        "volatility": vol_info,
        "meta_model": meta_info,
    }


@app.get("/api/trades")
def recent_trades(
    limit: int = 50,
    sleeve: Optional[str] = None,
    x_dashboard_token: Optional[str] = Header(default=None),
):
    _auth(x_dashboard_token)
    trades = _load_json(TRADES_FILE)
    if not isinstance(trades, list):
        trades = []
    if sleeve:
        trades = [t for t in trades if t.get("sleeve") == sleeve]
    return {"trades": trades[-limit:], "total": len(trades)}


@app.get("/api/positions")
def positions(x_dashboard_token: Optional[str] = Header(default=None)):
    _auth(x_dashboard_token)
    try:
        from config import TradingConfig
        from alpaca_client import AlpacaClient
        config = TradingConfig()
        client = AlpacaClient(config)
        all_positions = client.get_positions()

        trades = _load_json(TRADES_FILE)
        if not isinstance(trades, list):
            trades = []
        sleeve_map = {}
        for t in trades:
            if t.get("status") == "EXECUTED" and t.get("action") == "BUY":
                ticker = config.get_plain_symbol(t.get("ticker", ""))
                sleeve_map[ticker] = t.get("sleeve", "unknown")

        etf_tickers = set(config.LONG_TERM_ETF_TARGETS.keys())
        classified = {"short_term": [], "mid_term": [], "long_term": []}

        for p in all_positions:
            ticker = config.get_plain_symbol(p.get("ticker", ""))
            sleeve = sleeve_map.get(ticker)
            if not sleeve:
                sleeve = "long_term" if ticker in etf_tickers else "mid_term"
            p["sleeve"] = sleeve
            if sleeve in classified:
                classified[sleeve].append(p)

        return {"ok": True, "positions": classified}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/regime")
def regime(x_dashboard_token: Optional[str] = Header(default=None)):
    _auth(x_dashboard_token)
    try:
        from risk.regime_detection import RegimeDetector
        detector = RegimeDetector()
        state = detector.detect()
        return {"ok": True, "regime": state.to_dict()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/calibration")
def calibration(
    days: int = Query(default=90),
    x_dashboard_token: Optional[str] = Header(default=None),
):
    _auth(x_dashboard_token)
    try:
        from intelligence.calibration import CalibrationTracker
        tracker = CalibrationTracker()
        report = tracker.get_calibration_report(days=days)
        return {"ok": True, "calibration": report.to_dict()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/equity-curve")
def equity_curve(
    days: int = Query(default=30),
    x_dashboard_token: Optional[str] = Header(default=None),
):
    _auth(x_dashboard_token)
    history = _load_json(HISTORY_FILE)
    if not isinstance(history, list):
        history = []

    # Return last N days of snapshots
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = []
    for h in history:
        try:
            ts = datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
            if ts >= cutoff:
                filtered.append({
                    "date": h["timestamp"][:16],
                    "value": h["total_value"],
                    "cash": h.get("cash", 0),
                    "invested": h.get("invested", 0),
                    "positions": h.get("positions_count", 0),
                })
        except Exception:
            continue

    return {"ok": True, "curve": filtered, "total_snapshots": len(history)}
