#!/usr/bin/env python3
"""
port_probe.py — Capture all Wine network connections every second.
Run while logging in, selecting characters, zoning, and docking.
Logs any change in connections to logs/port_probe.log.
Ctrl+C to stop.

Usage: python3 port_probe.py
"""

import subprocess
import time
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE   = os.path.join(SCRIPT_DIR, "logs", "port_probe.log")

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def snapshot():
    """Return sorted list of 'proto localport remoteIP:remoteport state' strings for Wine procs."""
    try:
        r = subprocess.run(
            ["ss", "-tunp"],
            capture_output=True, text=True, timeout=3
        )
        lines = []
        for line in r.stdout.splitlines():
            if "wine" not in line.lower():
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            proto    = parts[0]          # tcp / udp
            local    = parts[4]          # local addr:port
            remote   = parts[5]          # remote addr:port
            state    = parts[1] if proto.startswith("tcp") else "UDP"
            lines.append(f"{proto:<5} {state:<14} {local:<25} → {remote}")
        return sorted(lines)
    except Exception as e:
        return [f"ERROR: {e}"]


def log(msg):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def main():
    log(f"START — logging Wine connections to {LOG_FILE}")
    print(f"Watching Wine connections every 1s. Log: {LOG_FILE}")
    print("Now: log in, select characters, zone, dock. Ctrl+C when done.\n")

    prev = None

    while True:
        tick = time.time()
        curr = snapshot()

        if curr != prev:
            if prev is None:
                log("=== Initial state ===")
                for line in curr:
                    log(f"  {line}")
            else:
                added   = [l for l in curr if l not in prev]
                removed = [l for l in prev if l not in curr]
                if added or removed:
                    log("=== Connection change ===")
                    for l in removed:
                        log(f"  REMOVED: {l}")
                    for l in added:
                        log(f"  ADDED:   {l}")
                    log(f"  Current ({len(curr)} conns):")
                    for l in curr:
                        log(f"    {l}")
            prev = curr

        elapsed = time.time() - tick
        time.sleep(max(0.0, 1.0 - elapsed))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("STOP")
        print("\nDone.")
        sys.exit(0)
