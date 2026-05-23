#!/usr/bin/env python3
"""
Cyberdeck TUI — Textual dashboard for the Cyberdeck Data Server.
Connects to ws://localhost:8765, authenticates with an empty token,
and renders a full-screen dashboard with system metrics, Nyx state,
and network counters.
"""

from __future__ import annotations

from __future__ import annotations

import asyncio
import json
import socket
import time

import websockets
import websockets
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import DataTable, Label, ProgressBar, RichLog, Static, Widget

# ── Colour Palette ──────────────────────────────────────────────────────────
# Dark neon on black: cyan primary, amber accents, magenta for Nyx/status.

CSS = """
Screen {
    background: #0a0a0a;
}

#dashboard {
    layout: grid;
    grid-size: 2 3;
    grid-rows: auto 1fr auto;
    grid-columns: 1fr 1fr;
    height: 100%;
}

/* ── Header — spans full width ────────────────────────────────────────── */
#header-panel {
    column-span: 2;
    height: 8;
    border: solid #00ffcc;
    border-title-align: center;
    background: #0d1a1a;
    padding: 0 1;
    content-align: center middle;
}

#header-text {
    width: 100%;
    text-align: center;
    color: #00ffcc;
}

#header-sub {
    color: #ffaa00;
}

/* ── System HUD ───────────────────────────────────────────────────────── */
#system-panel {
    border: solid #00ffcc;
    border-title-align: left;
    background: #0d1410;
    padding: 0 1;
    height: 100%;
}

.system-row {
    height: 1;
    margin: 0 0 1 0;
}

.system-label {
    width: 8;
    color: #00ffcc;
    text-style: bold;
}

.system-bar {
    width: 1fr;
    margin: 0 1;
}

.system-value {
    width: 6;
    color: #ffaa00;
    text-align: right;
}

#process-table {
    height: 1fr;
    margin: 1 0 0 0;
}

#process-table DataTable {
    height: 100%;
}

/* ── Nyx Panel ────────────────────────────────────────────────────────── */
#nyx-panel {
    border: solid #ff00aa;
    border-title-align: left;
    background: #140a0f;
    padding: 0 1;
    height: 100%;
}

#boredom-row {
    height: 3;
    align: center middle;
    margin: 0 0 1 0;
}

#boredom-label {
    color: #ff00aa;
    text-style: bold;
}

#boredom-bar {
    width: 1fr;
    margin: 0 1;
}

#boredom-value {
    width: 6;
    color: #ffaa00;
    text-align: right;
}

#monologue-label {
    color: #ff00aa;
    text-style: bold;
    margin: 1 0 0 0;
}

#monologue-log {
    border: none;
    background: #0d080b;
    color: #cc88bb;
    height: 1fr;
    margin: 0 0 0 0;
}

/* ── Network Panel ────────────────────────────────────────────────────── */
#network-panel {
    column-span: 2;
    border: solid #ffaa00;
    border-title-align: left;
    background: #14100a;
    height: 5;
    padding: 0 1;
    content-align: center middle;
}

#network-container {
    width: 100%;
    height: 3;
    align: center middle;
}

.network-stat {
    width: 1fr;
    height: 3;
    align: center middle;
}

.network-icon {
    color: #ffaa00;
    text-style: bold;
}

.network-value {
    color: #00ffcc;
}

/* ── Generic ──────────────────────────────────────────────────────────── */
.gauge-filled {
    color: #00ffcc;
    background: #003333;
}

.gauge-amber {
    color: #ffaa00;
    background: #332200;
}

.gauge-magenta {
    color: #ff00aa;
    background: #330022;
}
"""

# ── Helpers ────────────────────────────────────────────────────────────────

def format_bytes(n: int) -> str:
    """Format byte count into human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def get_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"

# ── Dashboard App ───────────────────────────────────────────────────────────

class CyberdeckTUI(App):
    """Full-screen cyberdeck dashboard TUI."""

    CSS = CSS

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
    ]

    # Reactive state
    connected = reactive(False)
    uptime_start = reactive(0.0)

    def __init__(self):
        super().__init__()
        self.hostname = get_hostname()
        self.uptime_start = time.time()
        self._ws_task: asyncio.Task | None = None
        self._last_net: tuple[int, int] = (0, 0)
        self._reconnect_delay = 1.0

    # ── Lifecycle ───────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.title = "CYBERDECK"
        self.sub_title = f"{self.hostname}"
        self._start_websocket()

    def _start_websocket(self) -> None:
        """Start the background websocket listener."""
        self._ws_task = asyncio.create_task(self._ws_loop())

    # ── WebSocket ───────────────────────────────────────────────────────

    async def _ws_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        uri = "ws://localhost:8765"
        while True:
            try:
                async with websockets.connect(uri) as ws:
                    # Authenticate with empty token
                    await ws.send(json.dumps({"token": ""}))
                    self.connected = True
                    self._reconnect_delay = 1.0
                    self._update_connection_status()

                    # Listen for messages
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            self._handle_update(data)
                        except json.JSONDecodeError:
                            continue
            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
                self.connected = False
                self._update_connection_status()
                # Exponential back-off, capped at 30 s
                self._reconnect_delay = min(self._reconnect_delay * 1.5, 30.0)
                await asyncio.sleep(self._reconnect_delay)

    def _handle_update(self, data: dict) -> None:
        """Process an incoming server payload and update widgets."""
        if data.get("type") != "cyberdeck_update":
            return

        system = data.get("system", {})
        nyx = data.get("nyx", {})

        # ── CPU ──
        cpu_data = system.get("cpu", {})
        cpu_pct = cpu_data.get("percent", 0)
        self._set_progress("cpu-bar", cpu_pct / 100.0)
        self._set_label("cpu-value", f"{cpu_pct:.0f}%")

        # ── RAM ──
        mem_data = system.get("memory", {})
        mem_pct = mem_data.get("percent", 0)
        mem_used = mem_data.get("used_gb", 0)
        mem_total = mem_data.get("total_gb", 0)
        self._set_progress("ram-bar", mem_pct / 100.0)
        self._set_label("ram-value", f"{mem_pct:.0f}% ({mem_used:.1f}/{mem_total:.1f} GB)")

        # ── Disk ──
        disk_data = system.get("disk", {})
        disk_pct = disk_data.get("percent", 0)
        disk_used = disk_data.get("used_gb", 0)
        disk_total = disk_data.get("total_gb", 0)
        self._set_progress("disk-bar", disk_pct / 100.0)
        self._set_label("disk-value", f"{disk_pct:.0f}% ({disk_used:.1f}/{disk_total:.1f} GB)")

        # ── Top Processes ──
        processes = system.get("top_processes", [])
        self._update_process_table(processes)

        # ── Network ──
        net_data = system.get("network", {})
        bytes_sent = net_data.get("bytes_sent", 0)
        bytes_recv = net_data.get("bytes_recv", 0)
        self._set_label("net-sent-value", format_bytes(bytes_sent))
        self._set_label("net-recv-value", format_bytes(bytes_recv))

        # ── Nyx Boredom ──
        boredom = nyx.get("boredom", {})
        if boredom and boredom.get("level") is not None:
            b_level = boredom["level"]
            b_max = boredom.get("threshold", 100)
            b_pct = min(b_level / max(b_max, 1), 1.0)
            self._set_progress("boredom-bar", b_pct)
            self._set_label("boredom-value", f"{b_level:.0f}/{b_max:.0f}")
            status = boredom.get("status", "unknown")
            self._set_label("boredom-label", f"▸ BOREDOM  [{status}]")

        # ── Nyx Monologue ──
        monologue = nyx.get("monologue", {})
        if monologue:
            text = monologue.get("text", "")
            if text:
                self._append_monologue(text)

        # ── Uptime ──
        uptime_secs = time.time() - self.uptime_start
        uptime_str = self._format_uptime(uptime_secs)
        self._set_label("header-uptime", f"UPTIME: {uptime_str}")

    # ── Widget Helpers ──────────────────────────────────────────────────

    def _set_progress(self, widget_id: str, fraction: float) -> None:
        """Set a ProgressBar's value, clamped to [0, 1]."""
        try:
            bar = self.query_one(f"#{widget_id}", ProgressBar)
            bar.progress = min(max(fraction, 0), 1)
        except NoMatches:
            pass

    def _set_label(self, widget_id: str, text: str) -> None:
        """Update a Static/Label widget's content."""
        try:
            widget = self.query_one(f"#{widget_id}", Widget)
            widget.update(text)
        except NoMatches:
            pass

    def _update_process_table(self, processes: list[dict]) -> None:
        """Refresh the top processes DataTable."""
        try:
            table = self.query_one("#process-table", DataTable)
            table.clear()
            if not table.columns:
                table.add_columns("PID", "NAME", "CPU%", "MEM%")
            for proc in processes:
                table.add_row(
                    str(proc.get("pid", "")),
                    proc.get("name", "?")[:18],
                    f"{proc.get('cpu', 0):.1f}",
                    f"{proc.get('mem', 0):.1f}",
                )
        except NoMatches:
            pass

    def _append_monologue(self, text: str) -> None:
        """Append a line to the Nyx monologue RichLog."""
        try:
            log = self.query_one("#monologue-log", RichLog)
            log.write(text)
        except NoMatches:
            pass

    def _update_connection_status(self) -> None:
        """Update the header to reflect connection state."""
        status = "☑ ONLINE" if self.connected else "☐ OFFLINE … reconnecting"
        colour = "[#00ffcc]" if self.connected else "[#ffaa00]"
        try:
            self.query_one("#header-conn", Label).update(f"{colour}{status}[/]")
        except NoMatches:
            pass

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        hours, rem = divmod(int(seconds), 3600)
        minutes, secs = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # ── Compose ─────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Container(
            # ── Header ──────────────────────────────────────────────
            Container(
                Static(
                    "╔══════════════════════════════════════════╗\n"
                    "║              CYBERDECK v1.0              ║\n"
                    "╚══════════════════════════════════════════╝",
                    id="header-text",
                ),
                Horizontal(
                    Label(f"HOST: {self.hostname}", id="header-host"),
                    Label("☐ OFFLINE", id="header-conn"),
                    Label("UPTIME: 00:00:00", id="header-uptime"),
                    id="header-sub",
                ),
                id="header-panel",
            ),
            # ── System HUD ─────────────────────────────────────────
            Container(
                Label("▸ CPU", classes="section-title"),
                Horizontal(
                    Label("CPU", classes="system-label"),
                    ProgressBar(id="cpu-bar", classes="system-bar"),
                    Label("0%", id="cpu-value", classes="system-value"),
                    classes="system-row",
                ),
                Horizontal(
                    Label("RAM", classes="system-label"),
                    ProgressBar(id="ram-bar", classes="system-bar"),
                    Label("0%", id="ram-value", classes="system-value"),
                    classes="system-row",
                ),
                Horizontal(
                    Label("DSK", classes="system-label"),
                    ProgressBar(id="disk-bar", classes="system-bar"),
                    Label("0%", id="disk-value", classes="system-value"),
                    classes="system-row",
                ),
                DataTable(id="process-table"),
                id="system-panel",
            ),
            # ── Nyx ────────────────────────────────────────────────
            Container(
                Label("▸ BOREDOM  [content]", id="boredom-label"),
                Horizontal(
                    ProgressBar(id="boredom-bar", classes="system-bar"),
                    Label("0/0", id="boredom-value", classes="system-value"),
                    id="boredom-row",
                ),
                Label("▸ MONOLOGUE", id="monologue-label"),
                RichLog(id="monologue-log", max_lines=100, highlight=True, markup=True, wrap=True),
                id="nyx-panel",
            ),
            # ── Network ─────────────────────────────────────────────
            Container(
                Horizontal(
                    Vertical(
                        Label("⬆ SENT", classes="network-icon"),
                        Label("0 B", id="net-sent-value", classes="network-value"),
                        classes="network-stat",
                    ),
                    Vertical(
                        Label("⬇ RECV", classes="network-icon"),
                        Label("0 B", id="net-recv-value", classes="network-value"),
                        classes="network-stat",
                    ),
                    id="network-container",
                ),
                id="network-panel",
            ),
            id="dashboard",
        )


# ── Entry Point ─────────────────────────────────────────────────────────────

def main():
    app = CyberdeckTUI()
    app.run()


if __name__ == "__main__":
    main()
