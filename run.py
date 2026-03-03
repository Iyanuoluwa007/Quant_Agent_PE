#!/usr/bin/env python3
"""
Quant Agent v2.1 -- Public Edition Launcher

Usage:
    python run.py              # Continuous mode
    python run.py --once       # Single cycle
    python run.py --status     # Check status
    python run.py --backtest   # Run historical backtests
    python run.py --reset N    # Reset simulated broker to $N
"""
import sys
import os
from pathlib import Path

SCRIPT_DIR = str(Path(__file__).parent.resolve())
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from agent import main

if __name__ == "__main__":
    main()
