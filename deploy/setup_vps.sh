#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AI Trading Agent — Hetzner VPS Setup Script
# Run this ONCE after SSH-ing into your fresh Hetzner server
#
# Usage:
#   1. SSH into your server: ssh root@YOUR_SERVER_IP
#   2. Upload this script:   scp setup_vps.sh root@YOUR_IP:~
#   3. Run it:               bash setup_vps.sh
# ═══════════════════════════════════════════════════════════════

set -e  # Exit on any error

echo "================================================"
echo "  AI Trading Agent — VPS Setup"
echo "================================================"

# ── Step 1: System update ───────────────────────────────────
echo ""
echo "[1/8] Updating system..."
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip git ufw curl

# ── Step 2: Create bot user ─────────────────────────────────
echo ""
echo "[2/8] Creating bot user..."
if id "bot" &>/dev/null; then
    echo "  User 'bot' already exists"
else
    adduser --disabled-password --gecos "" bot
    usermod -aG sudo bot
    echo "  Created user 'bot'"
fi

# ── Step 3: Firewall ────────────────────────────────────────
echo ""
echo "[3/8] Configuring firewall..."
ufw allow OpenSSH
ufw allow 8000/tcp  # API server
ufw allow 443/tcp   # HTTPS (for Caddy later)
ufw --force enable
echo "  Firewall: SSH + port 8000 + HTTPS allowed"

# ── Step 4: Create project directory ────────────────────────
echo ""
echo "[4/8] Setting up project directory..."
PROJECT_DIR="/home/bot/trading-agent"
mkdir -p $PROJECT_DIR
chown bot:bot $PROJECT_DIR

# ── Step 5: Create systemd service for the trading bot ──────
echo ""
echo "[5/8] Creating trading bot service..."
cat > /etc/systemd/system/trading-bot.service << 'BOTSERVICE'
[Unit]
Description=AI Trading Agent
After=network-online.target
Wants=network-online.target
# Only run during US market hours (13:30-21:00 UTC / 9:30 AM - 4:00 PM ET)
# The agent handles market hours internally, but this prevents wasted cycles

[Service]
User=bot
WorkingDirectory=/home/bot/trading-agent
EnvironmentFile=/home/bot/trading-agent/.env
ExecStart=/home/bot/trading-agent/.venv/bin/python run.py
Restart=on-failure
RestartSec=30
# Safety: restart up to 5 times, then stop
StartLimitBurst=5
StartLimitIntervalSec=300
# Resource limits
MemoryMax=512M
CPUQuota=50%
# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=trading-bot

[Install]
WantedBy=multi-user.target
BOTSERVICE

# ── Step 6: Create systemd service for the API server ───────
echo ""
echo "[6/8] Creating API server service..."
cat > /etc/systemd/system/trading-api.service << 'APISERVICE'
[Unit]
Description=Trading Bot Read-Only API
After=network-online.target
Wants=network-online.target

[Service]
User=bot
WorkingDirectory=/home/bot/trading-agent
EnvironmentFile=/home/bot/trading-agent/.env
ExecStart=/home/bot/trading-agent/.venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
MemoryMax=256M
CPUQuota=25%
StandardOutput=journal
StandardError=journal
SyslogIdentifier=trading-api

[Install]
WantedBy=multi-user.target
APISERVICE

# ── Step 7: Create systemd timer for monitor snapshots ──────
echo ""
echo "[7/8] Creating monitor timer..."
cat > /etc/systemd/system/trading-monitor.service << 'MONSERVICE'
[Unit]
Description=Trading Agent Portfolio Monitor Snapshot

[Service]
User=bot
WorkingDirectory=/home/bot/trading-agent
EnvironmentFile=/home/bot/trading-agent/.env
ExecStart=/home/bot/trading-agent/.venv/bin/python monitor.py --check
Type=oneshot
MONSERVICE

cat > /etc/systemd/system/trading-monitor.timer << 'MONTIMER'
[Unit]
Description=Run portfolio monitor every hour

[Timer]
OnCalendar=*:00:00
Persistent=true

[Install]
WantedBy=timers.target
MONTIMER

# ── Step 8: Create helper scripts ───────────────────────────
echo ""
echo "[8/8] Creating helper scripts..."

# Quick status script
cat > /home/bot/status.sh << 'STATUS'
#!/bin/bash
echo "=== Trading Bot ==="
systemctl status trading-bot --no-pager | head -5
echo ""
echo "=== API Server ==="
systemctl status trading-api --no-pager | head -5
echo ""
echo "=== Recent Logs (last 20 lines) ==="
journalctl -u trading-bot --no-pager -n 20
echo ""
echo "=== Monitor ==="
cd /home/bot/trading-agent && .venv/bin/python monitor.py --check 2>/dev/null
STATUS
chmod +x /home/bot/status.sh

# Deploy script (pull latest code)
cat > /home/bot/deploy.sh << 'DEPLOY'
#!/bin/bash
echo "Deploying latest code..."
cd /home/bot/trading-agent
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt --quiet
echo "Restarting services..."
sudo systemctl restart trading-bot
sudo systemctl restart trading-api
echo "Done. Checking status..."
sleep 3
systemctl status trading-bot --no-pager | head -5
systemctl status trading-api --no-pager | head -5
DEPLOY
chmod +x /home/bot/deploy.sh

# Logs shortcut
cat > /home/bot/logs.sh << 'LOGS'
#!/bin/bash
echo "=== Live Bot Logs (Ctrl+C to exit) ==="
journalctl -u trading-bot -f
LOGS
chmod +x /home/bot/logs.sh

chown bot:bot /home/bot/*.sh

# ── Reload systemd ──────────────────────────────────────────
systemctl daemon-reload

echo ""
echo "================================================"
echo "  VPS Setup Complete!"
echo "================================================"
echo ""
echo "  NEXT STEPS (as user 'bot'):"
echo ""
echo "  1. Switch to bot user:"
echo "     su - bot"
echo ""
echo "  2. Clone your repo:"
echo "     git clone https://github.com/YOURNAME/trading-agent.git"
echo "     cd trading-agent"
echo ""
echo "  3. Create Python environment:"
echo "     python3 -m venv .venv"
echo "     source .venv/bin/activate"
echo "     pip install -r requirements.txt"
echo ""
echo "  4. Create .env file:"
echo "     nano .env"
echo "     (paste your API keys — see .env.production template)"
echo ""
echo "  5. Test it:"
echo "     python run.py --once"
echo "     python monitor.py"
echo ""
echo "  6. Start services:"
echo "     sudo systemctl start trading-bot"
echo "     sudo systemctl start trading-api"
echo "     sudo systemctl enable trading-bot"
echo "     sudo systemctl enable trading-api"
echo "     sudo systemctl enable trading-monitor.timer"
echo "     sudo systemctl start trading-monitor.timer"
echo ""
echo "  7. Check everything:"
echo "     bash ~/status.sh"
echo ""
echo "  HELPER COMMANDS:"
echo "     bash ~/status.sh    — Quick status check"
echo "     bash ~/logs.sh      — Live log stream"
echo "     bash ~/deploy.sh    — Pull + restart after code changes"
echo ""
echo "================================================"
