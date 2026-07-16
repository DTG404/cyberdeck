#!/bin/bash
# Cyberdeck systemd service installer
# Installs both the data server and TUI launcher
set -e
umask 077

REPO_DIR="/root/projects/cyberdeck"
SERVER_SERVICE="cyberdeck-server.service"
TUI_SERVICE="cyberdeck-tui.service"
SERVER_PORT="${CYBERDECK_PORT:-8765}"
AUTH_TOKEN="${CYBERDECK_AUTH_TOKEN:-${CYBERDECK_TOKEN:-}}"
PYTHON_BIN="${REPO_DIR}/server/.venv/bin/python"
TUI_PYTHON="${REPO_DIR}/tui/.venv/bin/python"

echo "==> Installing Cyberdeck systemd services..."

# Generate auth token if not provided
if [ -z "$AUTH_TOKEN" ]; then
    AUTH_TOKEN=$(openssl rand -hex 32)
    echo "    Generated a new auth token (value not printed)."
fi

# Write auth token to config
install -d -m 0700 "$REPO_DIR/config"
cat > "$REPO_DIR/config/server.conf" << EOFCONF
CYBERDECK_HOST=0.0.0.0
CYBERDECK_PORT=$SERVER_PORT
CYBERDECK_AUTH_TOKEN=$AUTH_TOKEN
CYBERDECK_INTERVAL=2.0
EOFCONF
chmod 600 "$REPO_DIR/config/server.conf"

# --- Data Server Service ---
cat > "/etc/systemd/system/$SERVER_SERVICE" << EOFSRV
[Unit]
Description=Cyberdeck Dashboard - Data Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_DIR/server
ExecStart=$PYTHON_BIN server.py
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$REPO_DIR/config/server.conf
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

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
ExecStart=$TUI_PYTHON tui.py
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$REPO_DIR/config/server.conf

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
echo "To set a custom token: CYBERDECK_AUTH_TOKEN=<token> ./install.sh"
