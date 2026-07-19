#!/usr/bin/env python3
"""
enb_monitor.py — Monitor Earth & Beyond Net-7 client process states.
Displays a GUI window so keyboard events won't disrupt the game.

State detection based on empirical port_probe data:

  OFFLINE      — no net7proxy process for this slot
  STARTING     — process exists, no server/localhost connections yet
  LOGIN SCREEN — UDP to server:3806 only; no TCP 3805, no localhost pairs
  CHAR SELECT  — TCP to server:3805 present (global server = avatar list)
  IN GAME      — localhost TCP pairs present (net7proxy ↔ client.exe); no 3805
  ZONING       — ALL localhost pairs replaced simultaneously in one tick
  FROZEN?      — localhost pairs present, near-zero combined CPU sustained

  Dock/undock and combat are indistinguishable at the network level.

Windows version: identifies game instances by process name + launch order
(no Wine prefixes). net7proxy.exe instances are numbered 1-6 in order of
their PID (ascending), which matches the order they were launched.
"""

import os
import re
import sys
import time
import socket
import json
import threading
import psutil
import tkinter as tk
from tkinter import font as tkfont
from collections import defaultdict
from datetime import datetime

# ── Slot → Wine prefix (Linux only) ──────────────────────────────────────
SLOT_PREFIXES = {
    1: os.path.expanduser("~/.wine-enb"),
    2: os.path.expanduser("~/.wine-enb-2"),
    3: os.path.expanduser("~/.wine-enb-3"),
    4: os.path.expanduser("~/.wine-enb-4"),
    5: os.path.expanduser("~/.wine-enb-5"),
    6: os.path.expanduser("~/.wine-enb-6"),
}
MAX_SLOTS = 6

# ── Net-7 server ──────────────────────────────────────────────────────
NET7_HOSTS  = ["play.net-7.org", "sunrise.net-7.org", "local.net-7.org"]
FALLBACK_IP = "216.219.87.147"
PORT_LOGIN  = 3806
PORT_GLOBAL = 3805

# ── Thresholds ────────────────────────────────────────────────────────
REFRESH_S      = 1.0
FROZEN_CPU_PCT = 2.0
FROZEN_SECS    = 20
ZONE_MIN_PAIRS = 2

# ── Zone freeze detection ─────────────────────────────────────────────
# Each Wine prefix has its own real chat.log (setup_prefixes.sh no longer
# symlinks it from the base prefix — see docs/LESSONS.md "chat.log sharing
# across Wine prefixes causes structural data loss"). Each slot watches only
# its own log, so there's no cross-client interleaving/garbling to account for.
CHAT_LOG_SUBPATH = "drive_c/Program Files/EA GAMES/Earth & Beyond/release/chat.log"

# Windows: all slots share a single native install, so there's only one
# chat.log for all clients (unlike Linux's per-prefix copies). Any new line
# in it — from any slot — is treated as an "arrival" signal for every slot
# currently being watched for zone freeze.
CHAT_LOG_PATH_WINDOWS = r"C:\Program Files (x86)\EA GAMES\Earth & Beyond\release\chat.log"

# ── Log paths ─────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR    = os.path.join(SCRIPT_DIR, "logs")
LOG_FILE   = os.path.join(LOG_DIR, "monitor.log")
STATE_FILE = os.path.join(LOG_DIR, "monitor_state.json")

# ── GUI colours ───────────────────────────────────────────────────────
BG_COLOUR = "#1c1c1c"
FG_COLOUR = "#d0d0d0"
STATE_COLOUR = {
    "OFFLINE":      "#666666",
    "STARTING":     "#888888",
    "LOGIN SCREEN": "#00cccc",
    "CHAR SELECT":  "#44aaff",
    "IN GAME":      "#44cc44",
    "ZONING":       "#dddd00",
    "ZONE FREEZE":  "#ff8800",  # orange — frozen mid-zone while group zoned successfully
    "FROZEN?":      "#ff4444",
    "CRASHED?":     "#ff4444",
    "ZOMBIE":       "#ff4444",
    "ERROR":        "#ff4444",
}
STATE_TAG = {s: f"st_{i}" for i, s in enumerate(STATE_COLOUR)}

# ── Shared state (monitor thread → GUI thread) ────────────────────────
_lock         = threading.Lock()
_display_rows = []


# ── Logging ───────────────────────────────────────────────────────────
def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Server IP resolution ──────────────────────────────────────────────
def resolve_server_ips() -> set:
    ips = {FALLBACK_IP}
    for host in NET7_HOSTS:
        try:
            for res in socket.getaddrinfo(host, None, socket.AF_INET):
                ip = res[4][0]
                if not ip.startswith('127.'):   # local.net-7.org → 127.0.0.1, must exclude
                    ips.add(ip)
        except Exception:
            pass
    return ips


# ── Chat log tail reader ──────────────────────────────────────────────
class _ChatLogReader:
    """Tail a chat.log file — only yields lines added after construction."""

    def __init__(self, path: str):
        self._path = path
        self._pos  = 0
        try:
            self._pos = os.path.getsize(path)
        except OSError:
            pass

    def new_lines(self) -> list[str]:
        try:
            size = os.path.getsize(self._path)
        except OSError:
            return []
        if size < self._pos:
            self._pos = 0  # log was rotated/truncated
        if size == self._pos:
            return []
        try:
            with open(self._path, encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                data = f.read(size - self._pos)
            self._pos = size
            return data.splitlines()
        except OSError:
            return []


# ── Connection gathering (Linux — WINEPREFIX-based) ───────────────────
def scan_all_wine_conns(server_ips: set) -> dict:
    """
    Single pass over all processes. Returns:
      {prefix: {'server': [...], 'pairs': set(frozenset), 'procs': [...]}}
    """
    result = defaultdict(lambda: {'server': [], 'pairs': set(), 'procs': []})
    for proc in psutil.process_iter(['pid', 'name', 'status']):
        try:
            env    = proc.environ()
            prefix = env.get('WINEPREFIX', '')
            if not prefix:
                continue
            result[prefix]['procs'].append(
                (proc.info['name'] or '?', proc.info['pid'], proc.info['status'] or '?')
            )
            for c in proc.connections(kind='inet'):
                if not c.raddr:
                    continue
                lip, rip = c.laddr.ip, c.raddr.ip
                if rip in server_ips:
                    result[prefix]['server'].append(c)
                elif lip == '127.0.0.1' and rip == '127.0.0.1':
                    result[prefix]['pairs'].add(frozenset([c.laddr.port, c.raddr.port]))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return result


def find_game_procs() -> tuple[dict, dict]:
    """Linux: returns ({prefix: net7proxy proc}, {prefix: client.exe proc})."""
    proxies, clients = {}, {}
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = (proc.info['name'] or '').lower()
            if 'net7proxy' not in name and name != 'client.exe':
                continue
            prefix = proc.environ().get('WINEPREFIX', '')
            if not prefix:
                continue
            if 'net7proxy' in name:
                proxies[prefix] = proc
            else:
                clients[prefix] = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return proxies, clients


# ── Process discovery (Windows native) ───────────────────────────────
def _find_game_procs_win(slot_proxy_pid: dict, slot_client_pid: dict,
                          excluded_pids: set | None = None) -> tuple[dict, dict]:
    """
    Windows: returns ({slot_num: net7proxy proc}, {slot_num: client.exe proc}).

    Slot-to-PID assignments are sticky: once a PID is assigned to a slot, it
    keeps that slot until its process exits. Newly-appeared PIDs (initial
    launch, or a relaunch freeing a slot) fill unassigned slot numbers in
    ascending-PID order. This avoids the old behavior of re-sorting ALL PIDs
    every tick, which reassigned every slot number after any single relaunch.

    slot_proxy_pid / slot_client_pid are mutated in place to persist the
    mapping across ticks.

    excluded_pids: net7proxy.exe/client.exe PIDs to never assign a slot to
    (e.g. an untracked "Launch Independent Client" instance) — otherwise it
    would fill a free slot number and show up as a phantom tracked slot.
    """
    proxies_by_pid = {}
    clients_by_pid = {}
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            pid = proc.info['pid']
            if excluded_pids and pid in excluded_pids:
                continue
            name = (proc.info['name'] or '').lower()
            if 'net7proxy' in name:
                proxies_by_pid[pid] = proc
            elif name == 'client.exe':
                clients_by_pid[pid] = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def _assign(by_pid: dict, slot_pid: dict) -> dict:
        for slot_num in list(slot_pid):
            if slot_pid[slot_num] not in by_pid:
                del slot_pid[slot_num]

        unassigned_pids = sorted(pid for pid in by_pid if pid not in slot_pid.values())
        free_slots = sorted(set(range(1, MAX_SLOTS + 1)) - set(slot_pid))
        for pid, slot_num in zip(unassigned_pids, free_slots):
            slot_pid[slot_num] = pid

        return {slot_num: by_pid[pid] for slot_num, pid in slot_pid.items()}

    proxies = _assign(proxies_by_pid, slot_proxy_pid)
    clients = _assign(clients_by_pid, slot_client_pid)
    return proxies, clients


def _scan_all_conns_win(server_ips: set, proxy_procs: dict, client_procs: dict) -> dict:
    """
    Windows: gather network connections for each slot. Returns:
      {slot_num: {'server': [...], 'pairs': set(frozenset), 'procs': [...]}}
    """
    result = defaultdict(lambda: {'server': [], 'pairs': set(), 'procs': []})

    all_slot_procs: dict[int, list] = {}
    for slot_num, proc in proxy_procs.items():
        all_slot_procs.setdefault(slot_num, []).append(proc)
    for slot_num, proc in client_procs.items():
        all_slot_procs.setdefault(slot_num, []).append(proc)

    for slot_num, procs in all_slot_procs.items():
        for proc in procs:
            try:
                result[slot_num]['procs'].append(
                    (proc.name() or '?', proc.pid, proc.status() or '?')
                )
                for c in proc.connections(kind='inet'):
                    if not c.raddr:
                        continue
                    lip, rip = c.laddr.ip, c.raddr.ip
                    if rip in server_ips:
                        result[slot_num]['server'].append(c)
                    elif lip == '127.0.0.1' and rip == '127.0.0.1':
                        result[slot_num]['pairs'].add(
                            frozenset([c.laddr.port, c.raddr.port])
                        )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    return result


# ── State inference ───────────────────────────────────────────────────
def infer_state(proc, server_conns: list, pairs: set,
                prev_pairs, proxy_cpu: list, client_cpu: list) -> str:
    try:
        if proc.status() == psutil.STATUS_ZOMBIE:
            return "ZOMBIE"

        all_samples = proxy_cpu + client_cpu
        avg_cpu     = sum(all_samples) / len(all_samples) if all_samples else 0.0
        enough_data = len(proxy_cpu) >= int(FROZEN_SECS / REFRESH_S)

        server_ports = {c.raddr.port for c in server_conns if c.raddr}
        pair_count   = len(pairs)

        if not server_ports and pair_count == 0:
            if enough_data and avg_cpu < FROZEN_CPU_PCT:
                return "CRASHED?"
            return "STARTING"

        if PORT_GLOBAL in server_ports:
            return "CHAR SELECT"

        if PORT_LOGIN in server_ports and pair_count == 0:
            return "LOGIN SCREEN"

        if pair_count > 0:
            # A zone swaps exactly one localhost pair for a fresh one while the
            # other persists (overlap == 1 of 2) — proven live 2026-06-07 across
            # 5 simultaneous zones (see docs/LESSONS.md). The old "ALL pairs
            # replaced" (overlap == 0) condition never occurs in practice.
            if (prev_pairs is not None
                    and len(prev_pairs) >= ZONE_MIN_PAIRS
                    and pairs != prev_pairs
                    and len(pairs - prev_pairs) > 0):
                return "ZONING"
            if enough_data and avg_cpu < FROZEN_CPU_PCT:
                return "FROZEN?"
            return "IN GAME"

        return "STARTING"

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return "ERROR"


# ── Formatting helpers ────────────────────────────────────────────────
def fmt_uptime(proc):
    try:
        secs = int(time.time() - proc.create_time())
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"
    except Exception:
        return "?"

def fmt_mem(proc):
    try:
        return f"{proc.memory_info().rss / 1048576:.0f}MB"
    except Exception:
        return "?"

def fmt_cpu(proxy_samples: list, client_samples: list) -> str:
    if not proxy_samples and not client_samples:
        return "—"
    now = ((proxy_samples[-1] if proxy_samples else 0.0) +
           (client_samples[-1] if client_samples else 0.0))
    all_s = proxy_samples + client_samples
    avg   = sum(all_s) / len(all_s)
    return f"{now:4.1f}% ~{avg:4.1f}%"

def fmt_conns(server_conns, pairs):
    parts = []
    server_ports = sorted({c.raddr.port for c in server_conns if c.raddr})
    if server_ports:
        parts.append(f"srv:{','.join(str(p) for p in server_ports)}")
    if pairs:
        parts.append(f"{len(pairs)}pair{'s' if len(pairs) != 1 else ''}")
    return " ".join(parts) if parts else "—"

def fmt_proc_states(procs: list) -> str:
    if not procs:
        return "—"
    abnormal = [(n, s) for n, p, s in procs
                if s not in ('sleeping', 'running', 'idle', '?')]
    if abnormal:
        return " ".join(f"{n}:{s}" for n, s in abnormal)
    names = {}
    for n, p, s in procs:
        base = n.split('.')[0].lower()
        names[base] = names.get(base, 0) + 1
    return " ".join(f"{k}×{v}" for k, v in sorted(names.items()))

def fmt_dur(state_since_ts: str, now_ts: str) -> str:
    """Format seconds spent in current state as '5s', '2m30s', '1h05m'."""
    try:
        since = datetime.fromisoformat(state_since_ts)
        secs  = int((datetime.fromisoformat(now_ts) - since).total_seconds())
        if secs < 0:
            secs = 0
        if secs < 60:
            return f"{secs}s"
        elif secs < 3600:
            return f"{secs // 60}m{secs % 60:02d}s"
        else:
            return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"
    except Exception:
        return "?"

def detail_str(server_conns, pairs, procs):
    srv      = ", ".join(f"{c.raddr.ip}:{c.raddr.port}" for c in server_conns if c.raddr)
    proc_str = " ".join(f"{name}({status})" for name, pid, status in procs)
    return f"srv=[{srv or 'none'}] pairs={len(pairs)} procs=[{proc_str}]"


# ── Monitor thread ────────────────────────────────────────────────────
def _sync_proc_cache(cache: dict, new_procs: dict, on_evict=None) -> None:
    for key, proc in list(cache.items()):
        if key not in new_procs:
            del cache[key]
            if on_evict:
                on_evict(key, proc)
    for key, proc in new_procs.items():
        cached = cache.get(key)
        # A relaunch reuses the same key (slot prefix) but is a different PID
        # — without this check the cache keeps pointing at the dead process
        # forever (it's still "present" under the same key), every tick raises
        # NoSuchProcess, and the slot silently freezes at state "ERROR" with
        # no further transitions ever logged.
        if cached is None or cached.pid != proc.pid:
            if cached is not None and on_evict:
                on_evict(key, cached)
            try:
                proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            cache[key] = proc


def monitor_loop(stop_event: threading.Event, on_state_change=None,
                 frozen_zone_timeout_s: float = 20.0, excluded_pids: set | None = None):
    global _display_rows

    os.makedirs(LOG_DIR, exist_ok=True)
    server_ips      = resolve_server_ips()
    proxy_cpu_hist  = defaultdict(list)   # net7proxy pid → [samples]
    client_cpu_hist = defaultdict(list)   # ckey → [samples]
    proc_cache      = {}                   # ckey → net7proxy proc
    client_cache    = {}                   # ckey → client.exe proc
    prev_pairs      = {}                   # ckey → last pairs set
    prev_states     = {}
    state_since     = {}
    max_samples     = int(FROZEN_SECS / REFRESH_S) + 5

    # Windows: sticky slot→PID pins for _find_game_procs_win (see its docstring).
    slot_proxy_pid  = {}
    slot_client_pid = {}

    # Zone freeze state — one independent chat.log reader per slot (each
    # prefix now has its own real file; see CHAT_LOG_SUBPATH note above).
    chat_readers = {}
    shared_chat_reader = None
    if sys.platform == "win32":
        shared_chat_reader = _ChatLogReader(CHAT_LOG_PATH_WINDOWS)
    else:
        for sn, prefix in SLOT_PREFIXES.items():
            chat_readers[sn] = _ChatLogReader(os.path.join(prefix, CHAT_LOG_SUBPATH))
    freeze_deadlines = {}    # slot_num → deadline timestamp; armed the moment
                             # that slot starts zoning, cleared by its own
                             # arrival confirmation or by process loss
    freeze_fired     = set() # slot_nums that already logged ZONE FREEZE for
                             # the current watch — prevents re-logging every
                             # tick until the watch is cleared/re-armed

    log(f"START — server IPs: {', '.join(sorted(server_ips))}")

    # Prime CPU counters
    if sys.platform == "win32":
        proxy_procs, client_procs = _find_game_procs_win(slot_proxy_pid, slot_client_pid, excluded_pids)
    else:
        proxy_procs, client_procs = find_game_procs()
    _sync_proc_cache(proc_cache, proxy_procs)
    _sync_proc_cache(client_cache, client_procs)
    time.sleep(REFRESH_S)

    while not stop_event.is_set():
        tick_start = time.time()
        now_ts     = datetime.now().isoformat(timespec='milliseconds')

        if sys.platform == "win32":
            proxy_procs, client_procs = _find_game_procs_win(slot_proxy_pid, slot_client_pid, excluded_pids)
        else:
            proxy_procs, client_procs = find_game_procs()

        _sync_proc_cache(proc_cache, proxy_procs,
                         on_evict=lambda _k, proc: proxy_cpu_hist.pop(proc.pid, None))
        _sync_proc_cache(client_cache, client_procs,
                         on_evict=lambda k, _proc: client_cpu_hist.pop(k, None))

        if sys.platform == "win32":
            all_conns  = _scan_all_conns_win(server_ips, proc_cache, client_cache)
            slot_range = range(1, MAX_SLOTS + 1)
        else:
            all_conns  = scan_all_wine_conns(server_ips)
            slot_range = sorted(SLOT_PREFIXES)

        rows       = []
        state_snap = {}

        # Windows: drain the single shared chat.log once per tick — any new
        # line is an arrival signal for every slot currently being watched.
        shared_arrived = False
        if shared_chat_reader is not None:
            for _line in shared_chat_reader.new_lines():
                shared_arrived = True

        for slot_num in slot_range:
            ckey = slot_num if sys.platform == "win32" else SLOT_PREFIXES[slot_num]
            proc = proc_cache.get(ckey)

            # Drain this slot's own chat.log every tick — keeps the reader's
            # position current even while OFFLINE/crashed. Any new line at all
            # counts as "alive": chat.log only ever receives real game text
            # (no synthetic/keepalive entries), and arrivals can show up as
            # "We have entered…", "DOCKING CONTROL: Landing clearance…" (RTB/
            # docking), or nothing recognizable at all (staying docked while
            # the group zones, being out of formation) — so phrase-matching
            # is structurally incomplete. Activity of any kind is the only
            # signal with zero false-negative risk.
            arrived = shared_arrived
            reader  = chat_readers.get(slot_num)
            if reader is not None:
                for _line in reader.new_lines():
                    arrived = True

            if proc is None:
                state = "OFFLINE"
                freeze_deadlines.pop(slot_num, None)
                freeze_fired.discard(slot_num)
                dur   = fmt_dur(state_since.get(slot_num, now_ts), now_ts)
                rows.append((slot_num, state, dur, "—", "—", "—", "—", "—", "—"))
                state_snap[str(slot_num)] = {
                    "state": state, "pid": None,
                    "cpu_now": None, "cpu_avg": None, "mem_mb": None,
                    "server_ports": [], "localhost_pairs": 0,
                    "uptime_s": None,
                    "state_since": state_since.get(slot_num, now_ts),
                }
            else:
                try:
                    pid     = proc.pid
                    cpu_now = proc.cpu_percent(interval=None)
                    proxy_cpu_hist[pid].append(cpu_now)
                    if len(proxy_cpu_hist[pid]) > max_samples:
                        proxy_cpu_hist[pid].pop(0)

                    client_proc = client_cache.get(ckey)
                    if client_proc:
                        try:
                            cli_cpu = client_proc.cpu_percent(interval=None)
                            client_cpu_hist[ckey].append(cli_cpu)
                            if len(client_cpu_hist[ckey]) > max_samples:
                                client_cpu_hist[ckey].pop(0)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    cdata        = all_conns.get(ckey, {'server': [], 'pairs': set(), 'procs': []})
                    server_conns = cdata['server']
                    pairs        = cdata['pairs']
                    procs_info   = cdata['procs']
                    last_pairs   = prev_pairs.get(ckey)

                    proxy_s  = proxy_cpu_hist[pid]
                    client_s = client_cpu_hist[ckey]

                    state = infer_state(proc, server_conns, pairs, last_pairs, proxy_s, client_s)

                    # Zone freeze: arm the moment this slot starts zoning, clear
                    # on its own arrival confirmation, fire if the timeout passes
                    # with neither — all self-contained, no cross-slot watching.
                    if state == "ZONING":
                        if slot_num not in freeze_deadlines:
                            freeze_deadlines[slot_num] = tick_start + frozen_zone_timeout_s
                            freeze_fired.discard(slot_num)
                            log(f"SLOT {slot_num}  zone start — watching for arrival "
                                f"(timeout {frozen_zone_timeout_s:.0f}s)")

                        if arrived:
                            log(f"SLOT {slot_num}  zoned — freeze watch cleared")
                            del freeze_deadlines[slot_num]
                            freeze_fired.discard(slot_num)
                        elif tick_start > freeze_deadlines[slot_num]:
                            if slot_num not in freeze_fired:
                                log(f"SLOT {slot_num}  ZONE FREEZE — "
                                    f"{frozen_zone_timeout_s:.0f}s without arrival")
                                freeze_fired.add(slot_num)
                            state = "ZONE FREEZE"
                    elif slot_num in freeze_deadlines:
                        # Zone completed (state moved on to IN GAME or
                        # elsewhere) before "arrival" was detected — the
                        # stale watch would otherwise fire ZONE FREEZE on a
                        # perfectly healthy slot later. Clear it.
                        log(f"SLOT {slot_num}  zoned — freeze watch cleared "
                            f"(state={state})")
                        del freeze_deadlines[slot_num]
                        freeze_fired.discard(slot_num)

                    all_s    = proxy_s + client_s
                    cpu_avg  = sum(all_s) / len(all_s) if all_s else 0.0
                    uptime_s = int(time.time() - proc.create_time())
                    dur      = fmt_dur(state_since.get(slot_num, now_ts), now_ts)

                    prev_pairs[ckey] = pairs

                    rows.append((
                        slot_num, state, dur, str(pid),
                        fmt_cpu(proxy_s, client_s),
                        fmt_mem(proc),
                        fmt_conns(server_conns, pairs),
                        fmt_proc_states(procs_info),
                        fmt_uptime(proc),
                    ))
                    state_snap[str(slot_num)] = {
                        "state":           state,
                        "pid":             pid,
                        "cpu_now":         round(cpu_now, 2),
                        "cpu_avg":         round(cpu_avg, 2),
                        "mem_mb":          round(proc.memory_info().rss / 1048576, 1),
                        "server_ports":    sorted({c.raddr.port for c in server_conns if c.raddr}),
                        "localhost_pairs": len(pairs),
                        "proc_states":     [(n, s) for n, p, s in procs_info],
                        "uptime_s":        uptime_s,
                        "state_since":     state_since.get(slot_num, now_ts),
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    state = "ERROR"
                    freeze_deadlines.pop(slot_num, None)
                    dur   = fmt_dur(state_since.get(slot_num, now_ts), now_ts)
                    rows.append((slot_num, state, dur, "—", "—", "—", "—", "—", "—"))
                    state_snap[str(slot_num)] = {
                        "state": state, "pid": None,
                        "cpu_now": None, "cpu_avg": None, "mem_mb": None,
                        "server_ports": [], "localhost_pairs": 0,
                        "uptime_s": None,
                        "state_since": state_since.get(slot_num, now_ts),
                    }

            if state != prev_states.get(slot_num):
                old  = prev_states.get(slot_num, "—")
                cdat = all_conns.get(ckey, {'server': [], 'pairs': set(), 'procs': []})
                log(f"SLOT {slot_num}  {old} → {state}  "
                    f"{detail_str(cdat['server'], cdat['pairs'], cdat['procs'])}")
                if on_state_change:
                    try:
                        on_state_change(slot_num, old, state)
                    except Exception:
                        pass
                prev_states[slot_num] = state
                state_since[slot_num] = now_ts

        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"timestamp": now_ts, "slots": state_snap}, f, indent=2)
        except Exception:
            pass

        with _lock:
            _display_rows = rows

        elapsed = time.time() - tick_start
        time.sleep(max(0.0, REFRESH_S - elapsed))


# ── GUI ───────────────────────────────────────────────────────────────
def build_gui(stop_event: threading.Event):
    root = tk.Tk()
    root.title("EnB State Monitor")
    root.configure(bg=BG_COLOUR)

    mono   = tkfont.Font(family="Monospace", size=10)
    char_w = mono.measure("M")
    line_h = mono.metrics("linespace")
    pad    = 8
    root.geometry(f"{char_w * 120 + pad * 2}x{line_h * 14 + pad * 2}")
    root.resizable(True, True)

    text = tk.Text(
        root,
        font=mono,
        bg=BG_COLOUR,
        fg=FG_COLOUR,
        state="disabled",
        wrap="none",
        bd=0,
        padx=pad,
        pady=pad,
        selectbackground="#333333",
        insertwidth=0,
    )
    text.pack(fill="both", expand=True)

    for state, tag in STATE_TAG.items():
        text.tag_configure(tag, foreground=STATE_COLOUR.get(state, FG_COLOUR))
    text.tag_configure("hdr", foreground="#aaaaaa")
    text.tag_configure("dim", foreground="#555555")

    def refresh():
        with _lock:
            rows = list(_display_rows)

        text.config(state="normal")
        text.delete("1.0", "end")

        ts_str = datetime.now().strftime("%H:%M:%S")
        text.insert("end", f"EnB Client Monitor  {ts_str}  1s refresh  log→ {LOG_FILE}\n\n", "dim")

        hdr = (f"{'SLT':<4} {'STATE':<14} {'DUR':<8} {'PID':<7} "
               f"{'CPU now/avg':<18} {'MEM':<7} {'CONNECTIONS':<20} {'PROCS':<24} UPTIME\n")
        text.insert("end", hdr, "hdr")
        text.insert("end", "─" * 108 + "\n", "dim")

        for row in rows:
            slot_num, state, dur, pid, cpu, mem, conns, procs_s, uptime = row
            text.insert("end", f"{slot_num:<4} ")
            text.insert("end", f"{state:<14}", STATE_TAG.get(state, ""))
            text.insert("end", f" {dur:<8} {pid:<7} {cpu:<18} {mem:<7} {conns:<20} {procs_s:<24} {uptime}\n")

        text.insert("end", "─" * 108 + "\n", "dim")
        text.insert("end",
            "OFFLINE · STARTING · LOGIN SCREEN · CHAR SELECT · "
            "IN GAME · ZONING · FROZEN? · CRASHED?", "dim")

        text.config(state="disabled")

        if not stop_event.is_set():
            root.after(1000, refresh)

    def on_close():
        stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(900, refresh)
    root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────
def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    stop_event = threading.Event()
    t = threading.Thread(target=monitor_loop, args=(stop_event,), daemon=True)
    t.start()
    build_gui(stop_event)
    log("STOP — monitor exited")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("STOP — monitor exited")
        sys.exit(0)
