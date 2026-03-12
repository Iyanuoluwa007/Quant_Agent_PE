#!/usr/bin/env python3
"""
Quant Agent v2.1 -- Public Edition Launcher

This script launches the demo version of the trading agent.

Usage:
    python run.py              # Continuous demo mode
    python run.py --once       # Run a single demo cycle
    python run.py --status     # Display agent status
"""

import sys
import os
from pathlib import Path

# -------------------------------------------------------------------
# Ensure project root is on the Python path
# -------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

os.chdir(SCRIPT_DIR)

# -------------------------------------------------------------------
# Optional environment loading (safe for demo use)
# -------------------------------------------------------------------

try:
    from dotenv import load_dotenv
    load_dotenv(SCRIPT_DIR / ".env")
except ImportError:
    pass


# -------------------------------------------------------------------
# Launch agent
# -------------------------------------------------------------------

from agent import main


if __name__ == "__main__":
    main()