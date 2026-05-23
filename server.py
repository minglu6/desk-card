"""Desk Card local server. Serves the latest rendered PNG over HTTP.

Bind 127.0.0.1; the Likebook reaches us via `adb reverse tcp:8765 tcp:8765`.

Endpoints
---------
GET  /etag.json        {"etag": "<mtime-ns>", "ts": "<iso>"} — for polling
GET  /current.png      The latest rendered PNG (1404x1872, grayscale)
POST /render           JSON payload → re-render via render.py
GET  /health           "ok"

Background loop: a daemon thread re-renders the card every RENDER_INTERVAL_S
seconds. Time + Claude usage refresh on every render (usage_api has its own
60 s cache); weather_api has a 1-hour cache so it only hits the network once
per hour.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from datetime import datetime
from flask import Flask, jsonify, request, send_file

ROOT = Path(__file__).parent
OUT = ROOT / "out" / "current.png"
RENDER = ROOT / "render.py"

RENDER_INTERVAL_S = 60   # re-render the card every minute

# Windows: hide the brief console window that subprocess.run flashes when
# spawning child processes from a GUI parent (pythonw). Without this, every
# render and adb-devices poll causes a black window to pop up and vanish.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

# Night-mode quiet hours — no renders between [QUIET_START, QUIET_END) local time.
# E-ink keeps the last frame without power, so the card stays readable; we just
# stop wasting CPU + Anthropic / Caiyun API quota while the user is asleep.
QUIET_START_HOUR = 0     # 00:00 inclusive
QUIET_END_HOUR = 7       # 07:00 exclusive — first render happens at 07:00

# adb auto-rebind: when the Likebook reconnects via USB, we silently re-add
# `adb reverse tcp:8765 tcp:8765` so the on-device APK can keep reaching us
# without any manual setup.
ADB_EXE = r"D:\Program Files\adb-fastboot\adb.exe"
ADB_WATCH_INTERVAL_S = 15

app = Flask(__name__)


@app.get("/health")
def health():
    return "ok"


@app.get("/etag.json")
def etag():
    if not OUT.exists():
        return jsonify({"etag": "0", "exists": False}), 200
    st = OUT.stat()
    return jsonify({
        "etag": str(st.st_mtime_ns),
        "size": st.st_size,
        "exists": True,
    })


@app.get("/current.png")
def current_png():
    if not OUT.exists():
        return "no image yet", 404
    return send_file(OUT, mimetype="image/png", max_age=0)


@app.post("/render")
def do_render():
    payload = request.get_json(force=True, silent=True) or {}
    proc = subprocess.run(
        [sys.executable, str(RENDER), "--stdin"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        return jsonify({"ok": False, "stderr": proc.stderr}), 500
    return jsonify({"ok": True, "out": str(OUT), "stdout": proc.stdout.strip()})


def _render_once() -> bool:
    """Invoke render.py with no payload (uses defaults). True if successful."""
    try:
        proc = subprocess.run(
            [sys.executable, str(RENDER)],
            capture_output=True, text=True, timeout=30,
            creationflags=_NO_WINDOW,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _is_quiet_hours() -> bool:
    """True when the local time is in the user's nightly sleep window."""
    h = datetime.now().hour
    if QUIET_START_HOUR <= QUIET_END_HOUR:
        return QUIET_START_HOUR <= h < QUIET_END_HOUR
    # wrap-around (e.g. 22 → 6 next day)
    return h >= QUIET_START_HOUR or h < QUIET_END_HOUR


def _render_loop():
    """Background loop that re-renders the card on a fixed interval.

    Quiet between QUIET_START_HOUR and QUIET_END_HOUR — the e-ink display
    keeps showing the last frame so the user wakes up to whatever was
    drawn at midnight; no API calls happen overnight.
    """
    while True:
        if not _is_quiet_hours():
            _render_once()
        time.sleep(RENDER_INTERVAL_S)


def _adb_watchdog():
    """Re-bind `adb reverse tcp:8765 tcp:8765` whenever the device reappears.

    Polls every ADB_WATCH_INTERVAL_S seconds. If a device is listed as
    'device' (i.e. plugged in and authorised) but the reverse forward is
    missing, we silently bind it. Cheap operation; safe to call repeatedly.
    """
    if not Path(ADB_EXE).exists():
        return
    while True:
        try:
            r = subprocess.run([ADB_EXE, "devices"],
                               capture_output=True, text=True, timeout=5,
                               creationflags=_NO_WINDOW)
            connected = any("\tdevice" in ln for ln in r.stdout.splitlines()[1:])
            if connected:
                rev = subprocess.run([ADB_EXE, "reverse", "--list"],
                                     capture_output=True, text=True, timeout=5,
                                     creationflags=_NO_WINDOW)
                if "tcp:8765" not in rev.stdout:
                    subprocess.run(
                        [ADB_EXE, "reverse", "tcp:8765", "tcp:8765"],
                        capture_output=True, text=True, timeout=5,
                        creationflags=_NO_WINDOW,
                    )
        except Exception:
            pass
        time.sleep(ADB_WATCH_INTERVAL_S)


def _start_background():
    threading.Thread(target=_render_loop, daemon=True,
                     name="desk-card-render-loop").start()
    threading.Thread(target=_adb_watchdog, daemon=True,
                     name="desk-card-adb-watchdog").start()


if __name__ == "__main__":
    _start_background()
    # Bind on all interfaces so the Likebook can reach us via the LAN.
    # (Windows firewall must allow inbound TCP 8765.)
    app.run(host="0.0.0.0", port=8765, debug=False, use_reloader=False)
