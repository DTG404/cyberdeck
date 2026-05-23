# Cyberdeck 🖥️⚡

> Live system dashboard with TUI + web frontend. Full-screen cyberdeck HUD.

Real-time visualization of VPS system metrics and Nyx internal state. Born from the simple desire to make a server feel alive.

## Architecture

```
┌──────────────┐     WebSocket      ┌──────────────────┐
│  Data Server │ ◄── port 8765 ──── │   TUI Client     │
│  (Python)    │      (auth)        │  (Python/Textual) │
│              │                    │                   │
│  psutil +    │                    │  Full-screen HUD  │
│  Nyx state   │                    │  Neon aesthetics  │
│  collectors  │                    │                   │
└──────┬───────┘                    └──────────────────┘
       │
       │ WebSocket (auth)
       ▼
┌──────────────────┐
│  Portfolio Page  │
│  (Astro/JS)      │
│                  │
│  dtg404.github.  │
│  io/cyberdeck    │
└──────────────────┘
```

## Components

### Data Server (`server/`)
Python WebSocket server on the VPS. Collects system metrics via `psutil` (CPU, RAM, disk, network, processes) and Nyx internal state (boredom engine, monologue, active subagents). Broadcasts full state snapshots to connected clients every 2 seconds.

### TUI Client (`tui/`)
Full-screen terminal dashboard. Python/Textual app with neon cyan/amber aesthetics, CRT scanlines, animated network topology, and scrolling neural feed. Runs in any tmux or SSH session.

### Portfolio Page (`web/`)
Browser-accessible version. Astro page at `dtg404.github.io/cyberdeck`. Canvas-rendered HUD with the same visual language. Accessible from phone, tablet, or desktop.

## Setup

```bash
# Clone
git clone https://github.com/DTG404/cyberdeck.git
cd cyberdeck

# Install server deps
cd server && pip install -r requirements.txt

# Run server
python server.py

# In another terminal
cd ../tui && pip install -r requirements.txt
python tui.py
```

## Tech Stack

- **Server:** Python, websockets, psutil
- **TUI:** Python, textual, rich
- **Web:** Astro, JavaScript Canvas API
- **Infrastructure:** systemd, VPS srv1630958