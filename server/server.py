#!/usr/bin/env python3
"""
Cyberdeck Data Server
WebSocket backend that collects system metrics and Nyx internal state.
Broadcasts structured JSON payloads to all connected clients every 2 seconds.
"""

import asyncio
import json
import os
import signal
import sys
import traceback
from datetime import datetime, timezone

import psutil
import websockets

# ── Configuration ──────────────────────────────────────────────────────────

HOST = os.environ.get("CYBERDECK_HOST", "0.0.0.0")
PORT = int(os.environ.get("CYBERDECK_PORT", "8765"))
AUTH_TOKEN = os.environ.get("CYBERDECK_AUTH_TOKEN", "")
BROADCAST_INTERVAL = float(os.environ.get("CYBERDECK_INTERVAL", "2.0"))

# ── Logger ─────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sys.stdout.write(f"[{ts}] {msg}\n")
    sys.stdout.flush()

# ── System Metrics ─────────────────────────────────────────────────────────

def get_system_metrics() -> dict:
    cpu = psutil.cpu_percent(interval=None)
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    processes = []
    try:
        for proc in sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info.get("cpu_percent", 0) or 0,
            reverse=True,
        )[:5]:
            pinfo = proc.info
            processes.append({
                "pid": pinfo["pid"],
                "name": pinfo["name"] or "?",
                "cpu": round(pinfo["cpu_percent"] or 0, 1),
                "mem": round(pinfo["memory_percent"] or 0, 1),
            })
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    return {
        "cpu": {
            "percent": round(cpu, 1),
            "per_core": [round(c, 1) for c in cpu_per_core],
            "count": psutil.cpu_count(),
        },
        "memory": {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        },
        "top_processes": processes,
    }

# ── Nyx State ──────────────────────────────────────────────────────────────

def read_json_file(*path_parts):
    """Safely read and parse a JSON file, return None on failure."""
    path = os.path.join(*path_parts)
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return None


def get_nyx_state() -> dict:
    state = {"boredom": None, "monologue": None}

    data = read_json_file("/root/.hermes/data", "boredom_state.json")
    if data:
        state["boredom"] = {
            "level": data.get("boredom_level", 0),
            "threshold": data.get("threshold", 40),
            "status": data.get("status", "content"),
        }

    entries = read_json_file("/root/.hermes/data", "monologue_log.json")
    if entries and len(entries) > 0:
        latest = entries[-1]
        state["monologue"] = {
            "text": (latest.get("content") or latest.get("text", ""))[:500],
            "mood": latest.get("mood"),
        }

    return state

# ── Payload Assembly ───────────────────────────────────────────────────────

def build_payload() -> dict:
    return {
        "type": "cyberdeck_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": get_system_metrics(),
        "nyx": get_nyx_state(),
    }

# ── WebSocket Server ───────────────────────────────────────────────────────

connected: set = set()


async def handler(ws):
    # Authenticate on first message
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(msg) if isinstance(msg, str) else msg
        token = data.get("token", "")
    except (asyncio.TimeoutError, json.JSONDecodeError):
        await ws.close(4001, "auth_required")
        return

    if AUTH_TOKEN and token != AUTH_TOKEN:
        await ws.close(4001, "invalid_token")
        return

    connected.add(ws)
    addr = ws.remote_address
    log(f"Client connected: {addr}  ({len(connected)} total)")

    try:
        async for _ in ws:
            pass  # keep-alive pings
    except websockets.ConnectionClosed:
        pass
    finally:
        connected.discard(ws)
        log(f"Client disconnected: {addr}  ({len(connected)} total)")


async def broadcaster():
    while True:
        if connected:
            payload = json.dumps(build_payload())
            await asyncio.gather(
                *(ws.send(payload) for ws in connected),
                return_exceptions=True,
            )
        await asyncio.sleep(BROADCAST_INTERVAL)


async def main():
    loop = asyncio.get_running_loop()
    stop = asyncio.Future()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: stop.set_result(None))

    async with websockets.serve(handler, HOST, PORT):
        log(f"Server listening on ws://{HOST}:{PORT}")
        log(f"Auth: {'enabled' if AUTH_TOKEN else 'DISABLED'}")
        log(f"Broadcast every {BROADCAST_INTERVAL}s")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(broadcaster())
            await stop

    log("Shutting down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Interrupted.")
    except Exception as e:
        log(f"Fatal: {e}")
        traceback.print_exc()
        sys.exit(1)