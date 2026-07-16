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
    state = {
        "boredom": None,
        "monologue": None,
        "mood": None,
        "goals": [],
        "finds": [],
        "mood_history": [],
        "agents": None,
        "interest_weights": [],
        "energy": None,
        "wandering": [],
    }

    # ── Boredom + Mood + Interest Weights + Wandering ──
    data = read_json_file("/root/.hermes", "boredom.json")
    if data:
        b_level = data.get("boredom", 0)
        if isinstance(b_level, (int, float)):
            state["boredom"] = {
                "level": b_level,
                "threshold": 100,
                "status": "hunting" if b_level >= 60 else "wandering" if b_level >= 40 else "mild" if b_level >= 20 else "content",
            }
        state["mood"] = data.get("current_mood") or data.get("mood")

        # ── Finds (anticipation list) ──
        ant = data.get("anticipation", [])
        finds = []
        for a in ant[-12:]:
            finds.append({
                "title": a.get("title", "?"),
                "source": a.get("source", ""),
                "interest": a.get("interest", ""),
                "time": a.get("time", ""),
            })
        state["finds"] = finds

        # ── Interest Weights ──
        weights = data.get("interest_weights", {})
        if weights:
            sorted_w = sorted(weights.items(), key=lambda x: x[1], reverse=True)
            state["interest_weights"] = [
                {"name": k, "weight": round(v, 1)} for k, v in sorted_w
            ]

        # ── Wandering History ──
        wh = data.get("wandering_history", [])
        state["wandering"] = [{
            "time": w.get("time", ""),
            "interest": w.get("interest", ""),
            "note": w.get("note", "")[:100],
            "found": w.get("found", False),
        } for w in wh[-10:]]

    # ── Monologue ──
    entries = read_json_file("/root/.hermes", "monologue_log.json")
    if entries and isinstance(entries, dict):
        entry_list = entries.get("entries", [])
        if entry_list and len(entry_list) > 0:
            latest = entry_list[-1]
            state["monologue"] = {
                "text": (latest.get("thought") or latest.get("content") or latest.get("text", ""))[:500],
            }

    # ── Goals ──
    goals_data = read_json_file("/root/.hermes", "goals.json")
    if goals_data:
        goals_list = goals_data.get("goals", [])
        active = [g for g in goals_list if g.get("status") in ("in_progress", "pending")]
        active.sort(key=lambda g: g.get("priority", 99))
        state["goals"] = [{
            "name": g.get("description", g.get("name", "?"))[:80],
            "status": g.get("status", "?"),
            "progress": int(g.get("progress", 0) * 100),
            "priority": g.get("priority", 99),
        } for g in active[:8]]

    # ── Mood History + Energy ──
    mood_data = read_json_file("/root/.hermes", "mood.json")
    if mood_data:
        history = mood_data.get("history", [])
        state["mood_history"] = [{
            "mood": h.get("mood", "?"),
            "when": h.get("when", ""),
            "note": h.get("note", ""),
        } for h in history[-24:]]
        state["energy"] = {
            "current": mood_data.get("energy", 70),
            "max": mood_data.get("energy_max", 100),
        }

    # ── Agent Mesh ──
    agent_snap = read_json_file("/root/.hermes/data", "agent_snapshot.json")
    if agent_snap:
        mesh = agent_snap.get("mesh", {})
        state["agents"] = {
            "count": agent_snap.get("active_count", 0),
            "timestamp": agent_snap.get("timestamp", ""),
            "mesh": {
                "nodes": mesh.get("nodes", []),
                "edges": mesh.get("edges", []),
            },
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
    if not AUTH_TOKEN:
        raise RuntimeError("CYBERDECK_AUTH_TOKEN is required; refusing to start without authentication")

    loop = asyncio.get_running_loop()
    stop = asyncio.Future()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: stop.set_result(None))

    async with websockets.serve(handler, HOST, PORT):
        log(f"Server listening on ws://{HOST}:{PORT}")
        log(f"Auth: {'enabled' if AUTH_TOKEN else 'DISABLED'}")
        log(f"Broadcast every {BROADCAST_INTERVAL}s")

        async with asyncio.TaskGroup() as tg:
            broadcast_task = tg.create_task(broadcaster())
            await stop
            broadcast_task.cancel()

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
