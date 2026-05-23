# 🕹️ Cyberdeck Dashboard

**A live system HUD for Nyx's home (VPS srv1630958).**

Real-time TUI and web dashboard showing system metrics, Nyx internal state, and network activity — all streaming over WebSocket from the VPS.

## Architecture

```
┌──────────────────────────────────────────────┐
│                  VPS (srv1630958)              │
│                                                │
│  ┌─────────────┐    ┌─────────────────────┐   │
│  │  server.py   │────│  WebSocket :8765     │   │
│  │  (psutil +   │    │  JSON frames         │   │
│  │   nyx state) │    │  every 2s            │   │
│  └──────┬───────┘    └──────────┬──────────┘   │
│         │                       │               │
│         ▼                       ▼               │
│  ┌─────────────┐    ┌─────────────────────┐   │
│  │  tui.py      │    │  Portfolio Page      │   │
│  │  (Textual)   │    │  (dtg404.github.io)  │   │
│  │  tmux session│    │  JS WebSocket client │   │
│  └─────────────┘    └─────────────────────┘   │
└──────────────────────────────────────────────┘
```

## Components

### Data Server (`server/server.py`)
- WebSocket server on port 8765
- Auth token required for connections
- Broadcasts JSON frames every 2 seconds:
  - CPU (percent, frequency, cores)
  - Memory (RAM + swap)
  - Disk (usage per mount)
  - Network (bytes sent/received, connections)
  - Top processes (top 10 by CPU)
  - Nyx state (boredom, mood, monologue)

### TUI Client (`tui/tui.py`)
- Full-screen Textual dashboard
- Runs in tmux session (`cyberdeck`)
- Dark cyberpunk aesthetic (cyan/amber/magenta)
- Sections: System HUD, Processes, Nyx State, Network

### Portfolio Page (dtg404.github.io/cyberdeck)
- WebSocket client in JavaScript
- Same data, browser renderable
- Dark cyberpunk CSS theme matching the TUI
- Responsive layout
- Connection URLs:
  - `wss://srv1630958.tailscale.ts.net/` — Tailscale Funnel (requires [enabling in admin console](https://login.tailscale.com/f/funnel?node=nwmmxCK7QB11CNTRL))
  - `ws://177.7.50.53:8765` — Direct IP (blocked on HTTPS pages due to mixed content)

## Usage

```bash
# Start the server
systemctl start cyberdeck-server.service

# Launch the TUI
systemctl start cyberdeck-tui.service
tmux attach -t cyberdeck

# Or manually:
cd /root/projects/cyberdeck/server
CYBERDECK_AUTH_TOKEN=your-token .venv/bin/python server.py

cd /root/projects/cyberdeck/tui
.venv/bin/python tui.py
```

## Configuration

- `config/server.conf` — port and auth token
- Auth token: `openssl rand -hex 32`

## Repo

- GitHub: DTG404/cyberdeck
- Working dir: /root/projects/cyberdeck
