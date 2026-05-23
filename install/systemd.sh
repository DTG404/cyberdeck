#!/bin/bash
# Cyberdeck systemd service installer
# Installs both the data server and TUI launcher

set -e

REPO_DIR="/root/projects/cyberdeck"
SERVER_SERVICE="cyberdeck-server.service"
TUI_SERVICE="cyberdeck-tui.service"
SERVER_PORT="${CYBERDECK_PORT:-8765}"
AUTH_TOKEN="${CYBERDECK_TOKEN:-}"

echo "==> Installing Cyberdeck systemd services..."

# Generate auth token if not provided
if [ -z "$AUTH_TOKEN" ]; then
    AUTH_TOKEN=$(openssl rand -hex 32)
    echo "    Generated auth token: $AUTH_TOKEN"
    echo "    Save this for the TUI and portfolio page config."
fi

# Write auth token to config
mkdir -p "$REPO_DIR/config"
cat > "$REPO_DIR/config/server.conf" << EOFCONF
CYBERDECK_PORT=$SERVER_PORT
CYBERDECK_TOKEN=$AUTH_TOKEN
EOFCONF
chmod 600 "$REPO_DIR/config/server.conf"

# --- Data Server Service ---
cat > "/etc/systemd/system/$SERVER_SERVICE" << EOFSRV
[Unit]
Description=Cyberdeck Dashboard - Data Server
After=network.target hermes.service
Requires=hermes.service

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_DIR/server
ExecStart=/root/.hermes/venv/bin/python server.py $SERVER_PORT $AUTH_TOKEN
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOFSRV

# --- TUI Launcher Service (runs in tmux) ---
cat > "/etc/systemd/system/$TUI_SERVICE" << EOFSRV2
[Unit]
Description=Cyberdeck Dashboard - TUI (tmux)
After=cyberdeck-server.service
Requires=cyberdeck-server.service

[Service]
Type=oneshot
User=root
WorkingDirectory=$REPO_DIR/tui
ExecStartPre=/usr/bin/tmux new-session -d -s cyberdeck -x 120 -y 40
ExecStart=/root/.hermes/venv/bin/python tui.py
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOFSRV2

echo "==> Enabling services..."
systemctl daemon-reload
systemctl enable "$SERVER_SERVICE"

echo ""
echo "=== Done ==="
echo "Server service: $SERVER_SERVICE (enabled, start with: systemctl start $SERVER_SERVICE)"
echo "TUI launcher: $TUI_SERVICE (run with: systemctl start $TUI_SERVICE)"
echo "TUI tmux session: tmux attach -t cyberdeck"
echo "Auth token saved to: $REPO_DIR/config/server.conf"
echo ""
echo "To set a custom port: CYBERDECK_PORT=8888 ./install.sh"
echo "To set a custom token: CYBERDECK_TOKEN=mysecret ./install.sh"
