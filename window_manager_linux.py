# ============================================================
#  EnB Multibox Manager — window_manager.py
#  X11 window detection, renaming, moving, resizing
#  All operations via xdotool subprocess calls
# ============================================================

import subprocess
import re
import os
import time
from constants import ENB_WINDOW_NAMES, MAX_SLOTS

# ── Key timing globals ────────────────────────────────────────
# Configurable via configure_key_timing(); applied to every key_to_focused call.
_key_hold_ms: int      = 30   # how long each key is held before release
_modifier_delay_ms: int = 50  # delay between modifier keydown and main key


def configure_key_timing(hold_ms: int = 30, mod_delay_ms: int = 50) -> None:
    global _key_hold_ms, _modifier_delay_ms
    _key_hold_ms       = max(0, hold_ms)
    _modifier_delay_ms = max(0, mod_delay_ms)


def release_modifiers() -> None:
    """Release any stuck modifier keys. Called at the start of every loop thread."""
    for mod in ("alt", "ctrl", "shift", "super"):
        _run(["xdotool", "keyup", mod])


def wait_modifiers_released(timeout_s: float = 1.5) -> None:
    """Block until physical modifier keys are no longer held, or timeout expires.

    Prevents xdotool --clearmodifiers from restoring a held hotkey modifier
    (e.g. the alt from alt+a) onto the target window between keystrokes.
    """
    try:
        from Xlib import display as xdisplay, X
        dpy = xdisplay.Display()
        root = dpy.screen().root
        mod_mask = X.ShiftMask | X.ControlMask | X.Mod1Mask | X.Mod4Mask
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not (root.query_pointer().mask & mod_mask):
                break
            time.sleep(0.02)
        dpy.close()
    except Exception:
        time.sleep(0.15)


def _run(cmd: list) -> tuple[int, str, str]:
    """Run a subprocess, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"
    except Exception as e:
        return -1, "", str(e)


def check_xdotool() -> bool:
    """Return True if xdotool is available."""
    rc, _, _ = _run(["which", "xdotool"])
    return rc == 0

def check_wmctrl() -> bool:
    """Return True if wmctrl is available."""
    rc, _, _ = _run(["which", "wmctrl"])
    return rc == 0


# ── Window discovery ──────────────────────────────────────────

def get_all_windows() -> list[dict]:
    """
    Return list of all visible windows as dicts:
    {id: int, title: str, pid: int, x: int, y: int, w: int, h: int}
    """
    # Try with PID first
    rc, out, err = _run(["wmctrl", "-lGp"])
    use_pid = (rc == 0)
    if not use_pid:
        rc, out, err = _run(["wmctrl", "-lG"])
        if rc != 0:
            return []

    windows = []
    for line in out.splitlines():
        # Don't limit splits — we reassemble the title manually
        parts = line.split()
        try:
            if use_pid:
                # format: id  desktop  pid  x  y  w  h  host  title...
                if len(parts) < 9:
                    continue
                wid   = int(parts[0], 16)
                pid   = int(parts[2])
                x     = int(parts[3])
                y     = int(parts[4])
                w     = int(parts[5])
                h     = int(parts[6])
                # parts[7] = hostname, parts[8:] = title words
                title = " ".join(parts[8:])
            else:
                # format: id  desktop  x  y  w  h  host  title...
                if len(parts) < 8:
                    continue
                wid   = int(parts[0], 16)
                pid   = 0
                x     = int(parts[2])
                y     = int(parts[3])
                w     = int(parts[4])
                h     = int(parts[5])
                title = " ".join(parts[7:])

            if title:
                windows.append({
                    "id":    wid,
                    "title": title.strip(),
                    "pid":   pid,
                    "x": x, "y": y,
                    "w": w, "h": h,
                })
        except (ValueError, IndexError):
            continue
    return windows


def get_toplevel_hwnd(window_id: int) -> int:
    """Linux/X11 parity stub: `winfo_id()` already returns the real top-level
    window id here, so this is a no-op identity function."""
    return window_id


def slot_wine_prefix(slot_index: int) -> str:
    """Return the WINEPREFIX for a given 0-based slot index."""
    base = os.path.expanduser("~/.wine-enb")
    return base if slot_index == 0 else f"{base}-{slot_index + 1}"


def _managed_wine_prefixes() -> set[str]:
    """Return the set of WINEPREFIX paths enbmb manages (slots 0–MAX_SLOTS-1)."""
    return {slot_wine_prefix(i) for i in range(MAX_SLOTS)}


_UNREADABLE = object()  # sentinel: /proc file could not be read

def get_wine_prefix(pid: int):
    """Read WINEPREFIX from /proc/<pid>/environ.
    Returns the prefix string if found, "" if file is readable but WINEPREFIX
    is not set, or _UNREADABLE sentinel if the file could not be read."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            for var in f.read().split(b"\0"):
                if var.startswith(b"WINEPREFIX="):
                    return var[len(b"WINEPREFIX="):].decode(errors="replace")
        return ""  # file readable, WINEPREFIX not present
    except Exception:
        return _UNREADABLE


def find_enb_windows_any(extra_names: list[str] = None) -> list[dict]:
    """Like find_enb_windows but returns ALL EnB-looking windows regardless of prefix.
    Use only for tracking windows that may be on unmanaged prefixes (e.g. independent client)."""
    from constants import CLASS_ABBREVS
    all_wins = get_all_windows()
    enb = []
    known_titles = set(CLASS_ABBREVS)
    if extra_names:
        known_titles.update(n.strip() for n in extra_names if n.strip())
    for win in all_wins:
        title = win["title"].strip()
        matched = any(name.lower() in title.lower() for name in ENB_WINDOW_NAMES)
        if not matched and title in known_titles:
            matched = True
        if matched and win not in enb:
            enb.append(win)
    return enb


def find_enb_windows(extra_names: list[str] = None) -> list[dict]:
    """
    Return windows that look like EnB clients.
    Matches on known window title substrings, role abbreviations,
    and any extra_names provided (e.g. character names from slots).
    """
    from constants import CLASS_ABBREVS
    all_wins = get_all_windows()
    enb      = []
    known_titles = set(CLASS_ABBREVS)
    if extra_names:
        known_titles.update(n.strip() for n in extra_names if n.strip())

    for win in all_wins:
        title = win["title"].strip()
        matched = False

        # Match on known EnB window name substrings
        for name in ENB_WINDOW_NAMES:
            if name.lower() in title.lower():
                matched = True
                break

        # Match on exact role abbreviation or character name
        if not matched and title in known_titles:
            matched = True

        if matched and win not in enb:
            enb.append(win)

    # Filter to managed Wine prefixes only. Windows whose prefix is readable
    # but not in the managed set are independent clients — skip them silently.
    # Only fail-open when /proc is genuinely unreadable (process race, permissions).
    # A readable environ with no WINEPREFIX set is also not a managed client.
    managed = _managed_wine_prefixes()
    filtered = []
    for win in enb:
        pid = win.get("pid")
        if pid:
            prefix = get_wine_prefix(pid)
            if prefix is _UNREADABLE:
                win["wine_prefix"] = None  # unknown — fail-open
            elif prefix not in managed:
                continue  # readable but not managed (includes "" = no prefix set)
            else:
                win["wine_prefix"] = prefix
        else:
            win["wine_prefix"] = None
        filtered.append(win)
    return filtered


def get_window_by_id(wid: int) -> dict | None:
    """Fetch current geometry/title for a specific window ID."""
    all_wins = get_all_windows()
    for w in all_wins:
        if w["id"] == wid:
            return w
    return None

def window_exists(wid: int) -> bool:
    return get_window_by_id(wid) is not None


def get_active_window_id() -> int:
    """Return the window ID of the currently active window."""
    rc, out, _ = _run(["xdotool", "getactivewindow"])
    if rc == 0:
        try:
            return int(out.strip())
        except ValueError:
            pass
    return 0


def get_mouse_position() -> tuple[int, int]:
    """Return the current (x, y) screen position of the mouse cursor."""
    rc, out, _ = _run(["xdotool", "getmouselocation", "--shell"])
    if rc == 0:
        x = y = 0
        for line in out.splitlines():
            if line.startswith("X="):
                x = int(line[2:])
            elif line.startswith("Y="):
                y = int(line[2:])
        return (x, y)
    return (0, 0)


def find_enb_processes() -> dict[str, list[int]]:
    """
    Return {process_name: [pid, ...]} for all running EnB-related processes.
    Useful for diagnostics and confirming everything is dead after Kill All.
    """
    from constants import ENB_PROCESS_NAMES
    result = {}
    for name in ENB_PROCESS_NAMES:
        rc, out, _ = _run(["pgrep", "--full", name])
        if rc == 0 and out.strip():
            pids = [int(p) for p in out.strip().splitlines() if p.strip().isdigit()]
            if pids:
                result[name] = pids
    return result


def kill_all_enb_processes() -> list[str]:
    """
    SIGKILL all running EnB-related processes by name.
    Returns list of process names that had running instances.
    Supplements kill-by-PID so stray processes without assigned slots are caught.
    """
    from constants import ENB_PROCESS_NAMES
    killed = []
    for name in ENB_PROCESS_NAMES:
        rc, _, _ = _run(["pkill", "--signal", "9", "--full", name])
        if rc == 0:
            killed.append(name)
    return killed


# ── Window manipulation ───────────────────────────────────────

def rename_window(wid: int, name: str) -> bool:
    """Rename a window's title via xdotool."""
    rc, _, err = _run(["xdotool", "set_window", "--name", name, str(wid)])
    if rc != 0:
        print(f"[wm] rename_window({wid}, {name!r}) failed: {err}")
    return rc == 0


def minimize_window(wid: int) -> None:
    """Iconify (minimize) a window without killing it."""
    _run(["xdotool", "windowminimize", str(wid)])


def move_resize_window(wid: int, x: int, y: int, w: int, h: int) -> bool:
    """Move and resize a window via xdotool/wmctrl."""
    wid_hex = hex(wid)

    # Remove maximized state first — maximized windows ignore resize commands
    _run(["wmctrl", "-ir", wid_hex, "-b", "remove,maximized_vert,maximized_horz"])
    _run(["wmctrl", "-ir", wid_hex, "-b", "remove,fullscreen"])
    time.sleep(0.05)

    # Move then resize
    r1 = _run(["xdotool", "windowmove", str(wid), str(x), str(y)])
    time.sleep(0.05)
    r2 = _run(["xdotool", "windowsize", str(wid), str(w), str(h)])

    if r1[0] != 0:
        print(f"[wm] windowmove({wid}) failed: {r1[2]}")
    if r2[0] != 0:
        print(f"[wm] windowsize({wid}) failed: {r2[2]}")
    return r1[0] == 0 and r2[0] == 0


def restore_window(wid: int) -> None:
    """Un-minimize and clear maximized/fullscreen state without moving/resizing."""
    wid_hex = hex(wid)
    _run(["wmctrl", "-ir", wid_hex, "-b", "remove,hidden"])
    _run(["wmctrl", "-ir", wid_hex, "-b", "remove,maximized_vert,maximized_horz"])
    _run(["wmctrl", "-ir", wid_hex, "-b", "remove,fullscreen"])


def raise_window(wid: int) -> None:
    """Raise window to top of stacking order without stealing focus."""
    _run(["xdotool", "windowraise", str(wid)])


def reposition_window(wid: int, x: int, y: int) -> None:
    """Move window without resizing."""
    _run(["xdotool", "windowmove", str(wid), str(x), str(y)])


def focus_window(wid: int) -> bool:
    """Bring a window to focus and raise it."""
    rc, _, err = _run(["xdotool", "windowfocus", "--sync", str(wid)])
    if rc != 0:
        print(f"[wm] focus_window({wid}) failed: {err}")
        return False
    _run(["xdotool", "windowraise", str(wid)])
    return True


def activate_window(wid: int) -> bool:
    """Activate window (focus + raise + bring to current desktop)."""
    rc, _, err = _run(["wmctrl", "-ia", hex(wid)])
    if rc != 0:
        # fallback to xdotool
        return focus_window(wid)
    return True


def return_to_driver(wid: int, cx: int, cy: int) -> None:
    """End-of-loop cleanup: activate driver window and warp mouse into it.

    Uses xdotool windowactivate + windowfocus (more reliable for Wine than
    wmctrl alone) then moves the mouse to (cx, cy) so it is no longer hovering
    over the last secondary window.  Short settle sleep included.
    """
    _run(["xdotool", "windowactivate", "--sync", str(wid)])
    _run(["xdotool", "windowfocus",    "--sync", str(wid)])
    _run(["xdotool", "mousemove", str(cx), str(cy)])
    time.sleep(0.05)


def set_stay_on_top(wid: int, enable: bool) -> bool:
    """Toggle always-on-top for a window via wmctrl."""
    action = "add" if enable else "remove"
    rc, _, err = _run([
        "wmctrl", "-ir", hex(wid),
        "-b", f"{action},above"
    ])
    return rc == 0


def get_frame_extents(wid: int) -> tuple[int, int, int, int]:
    """
    Return the Openbox frame extents (left, right, top, bottom) for a window.
    Returns (0, 0, 0, 0) if the property is absent (borderless or unmanaged).
    """
    rc, out, _ = _run(["xprop", "-id", str(wid), "_NET_FRAME_EXTENTS"])
    if rc != 0 or "=" not in out:
        return (0, 0, 0, 0)
    try:
        vals = [int(v.strip()) for v in out.split("=")[1].split(",")]
        if len(vals) == 4:
            return (vals[0], vals[1], vals[2], vals[3])
    except Exception:
        pass
    return (0, 0, 0, 0)


def set_window_borderless(wid: int, enable: bool) -> bool:
    """
    Add or remove window decorations (borderless) via Openbox's
    _OB_WM_STATE_UNDECORATED atom using a proper _NET_WM_STATE ClientMessage.
    wmctrl -b doesn't work here because wmctrl prepends _NET_WM_STATE_ to the
    atom name, creating a non-existent atom.
    """
    try:
        from Xlib import display as xdisplay, X
        from Xlib.protocol import event

        dpy    = xdisplay.Display()
        root   = dpy.screen().root
        window = dpy.create_resource_object('window', wid)

        NET_WM_STATE   = dpy.intern_atom('_NET_WM_STATE')
        OB_UNDECORATED = dpy.intern_atom('_OB_WM_STATE_UNDECORATED')

        action = 1 if enable else 0  # 1=add, 0=remove
        ev = event.ClientMessage(
            window=window,
            client_type=NET_WM_STATE,
            # data[3]=1 → source indication = normal application (Openbox requires this)
            data=(32, [action, OB_UNDECORATED, 0, 1, 0]),
        )
        root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        dpy.sync()  # flush + wait for X server to process before returning
        dpy.close()
        return True
    except Exception as e:
        print(f"[wm] set_window_borderless({wid}, {enable}) failed: {e}")
        return False


def set_bypass_compositor(wid: int) -> bool:
    """
    Set _NET_WM_BYPASS_COMPOSITOR=1 on a window so the compositor skips it.
    Eliminates the ghost-copy artifact when dragging windows across Wine surfaces.
    """
    try:
        from Xlib import display as xdisplay
        from Xlib import Xatom

        dpy    = xdisplay.Display()
        window = dpy.create_resource_object('window', wid)
        atom   = dpy.intern_atom('_NET_WM_BYPASS_COMPOSITOR')
        window.change_property(atom, Xatom.CARDINAL, 32, [1])
        dpy.sync()
        dpy.close()
        return True
    except Exception as e:
        print(f"[wm] set_bypass_compositor({wid}) failed: {e}")
        return False


# ── Focused-window input ──────────────────────────────────────

def type_to_focused(text: str, delay_ms: int = 10) -> bool:
    """Type a string into whichever window currently has focus."""
    rc, _, err = _run([
        "xdotool", "type",
        "--delay", str(delay_ms),
        "--clearmodifiers",
        text,
    ])
    return rc == 0


def key_to_focused(key: str) -> bool:
    """Send a key to whichever window currently has focus.

    All keys use explicit keydown → hold → keyup so the game registers them
    reliably even under lag.  Modifier combos (e.g. 'alt+6') hold the modifier
    first, delay, then press the main key.
    """
    def _norm(k: str) -> str:
        return re.sub(r'(?i)^f(\d+)$', lambda m: f'F{m.group(1)}', k)

    hold  = _key_hold_ms      / 1000.0
    mdly  = _modifier_delay_ms / 1000.0

    if '+' in key:
        parts    = key.split('+', 1)
        modifier = parts[0].strip()
        main     = _norm(parts[1].strip())
        _run(["xdotool", "keydown", modifier])
        try:
            time.sleep(mdly)
            _run(["xdotool", "keydown", main])
            time.sleep(hold)
            _run(["xdotool", "keyup", main])
            time.sleep(0.01)
        finally:
            _run(["xdotool", "keyup", modifier])
        return True
    else:
        key = _norm(key)
        _run(["xdotool", "keydown", "--clearmodifiers", key])
        time.sleep(hold)
        rc, _, _ = _run(["xdotool", "keyup", "--clearmodifiers", key])
        return rc == 0


# ── Input broadcasting ────────────────────────────────────────

def send_key_to_window(wid: int, key: str) -> bool:
    """
    Send a keystroke to a window WITHOUT focusing it.
    This is the broadcast-to-inactive-window attempt.
    Returns True if xdotool accepted the command (not a guarantee EnB received it).
    """
    rc, _, err = _run(["xdotool", "key", "--window", str(wid), key])
    return rc == 0


def send_keys_to_window(wid: int, keys: list[str], delay_ms: int = 50) -> bool:
    """Send multiple keys to a window sequentially."""
    for key in keys:
        ok = send_key_to_window(wid, key)
        if not ok:
            return False
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
    return True


def click_at(x: int, y: int, button: int = 1) -> bool:
    """Move mouse to screen coordinates and click (active window mode)."""
    _run(["xdotool", "mousemove", "--sync", str(x), str(y)])
    rc, _, _ = _run(["xdotool", "click", "--clearmodifiers", str(button)])
    return rc == 0


def mouse_slide_relative(dx: int = 0, dy: int = 400, duration_ms: int = 200,
                          hold_shift: bool = True) -> None:
    """Smoothly move mouse by (dx, dy) relative to current position.
    Shift is held throughout if hold_shift is True. No mouse button is pressed.

    Some games clamp the per-event relative-mouse delta (to avoid huge jumps from
    lag), so a single large mousemove_relative can be silently truncated. Cap each
    step to MAX_STEP_PX and add steps as needed -- step_sleep shrinks to match, so
    total duration stays duration_ms regardless of how many steps that becomes."""
    MAX_STEP_PX = 20
    largest     = max(abs(dx), abs(dy))
    min_steps   = (largest // MAX_STEP_PX) + 1 if largest else 1
    steps       = max(1, duration_ms // 10, min_steps)
    step_sleep  = duration_ms / 1000.0 / steps
    acc_x = acc_y = 0.0

    if hold_shift:
        _run(["xdotool", "keydown", "shift"])
        time.sleep(0.02)
    for i in range(1, steps + 1):
        move_x = round(dx * i / steps - acc_x)
        move_y = round(dy * i / steps - acc_y)
        acc_x += move_x
        acc_y += move_y
        _run(["xdotool", "mousemove_relative", "--", str(move_x), str(move_y)])
        time.sleep(step_sleep)
    if hold_shift:
        time.sleep(0.02)
        _run(["xdotool", "keyup", "shift"])


def mouse_drag(x1: int, y1: int, x2: int, y2: int,
               steps: int = 12, hold_shift: bool = False) -> bool:
    """Drag mouse from (x1,y1) to (x2,y2) with optional Shift held."""
    _run(["xdotool", "mousemove", str(x1), str(y1)])
    time.sleep(0.02)
    if hold_shift:
        _run(["xdotool", "keydown", "shift"])
        time.sleep(0.02)
    _run(["xdotool", "mousedown", "1"])
    step_x = (x2 - x1) / steps
    step_y = (y2 - y1) / steps
    for i in range(1, steps + 1):
        nx = int(x1 + step_x * i)
        ny = int(y1 + step_y * i)
        _run(["xdotool", "mousemove", str(nx), str(ny)])
        time.sleep(0.015)
    _run(["xdotool", "mouseup", "1"])
    if hold_shift:
        time.sleep(0.02)
        _run(["xdotool", "keyup", "shift"])
    return True


# ── Process control ───────────────────────────────────────────

def _is_wine_pid(pid: int) -> bool:
    """Return True if the process is a Wine executable (not a native Linux process)."""
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
        return "wine" in exe.lower()
    except OSError:
        return False


def is_enb_client_pid(pid: int) -> bool:
    """
    Return True if pid belongs to a process we should treat as an EnB client.
    On Linux, find_enb_windows() may title-match unrelated native windows
    (e.g. this app's own UI), so we additionally require the process be Wine.
    """
    return _is_wine_pid(pid)


def pid_exists(pid: int) -> bool:
    """Return True if a process with this PID is currently running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def kill_window_process(pid: int) -> bool:
    """Kill a process by PID."""
    try:
        os.kill(pid, 15)  # SIGTERM first
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        print(f"[wm] Permission denied killing PID {pid}")
        return False


def winresize_wine_window(slot_index: int, title: str,
                          x: int, y: int, w: int, h: int) -> bool:
    """
    Resize a Wine window via winresize.exe (SetWindowPos).
    xdotool windowsize has no effect on Wine windows; this is the only working path.
    Must run under the same Wine prefix as the target window.
    slot_index is 0-based: slot 0 → ~/.wine-enb, slot N → ~/.wine-enb-{N+1}
    """
    winres = os.path.join(os.path.dirname(os.path.abspath(__file__)), "winresize.exe")
    if not os.path.exists(winres):
        return False
    prefix = slot_wine_prefix(slot_index)
    cmd    = f'WINEPREFIX="{prefix}" wine "{winres}" "{title}" {x} {y} {w} {h}'
    try:
        result = subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=8)
        return result.returncode == 0
    except Exception as e:
        print(f"[wm] winresize failed for slot {slot_index + 1}: {e}")
        return False


def launch_enb_client(command: str) -> int | None:
    """
    Launch an EnB client with the given shell command.
    Returns the PID of the launched process, or None on failure.
    """
    if not command:
        print("[wm] No launch command configured")
        return None
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.pid
    except Exception as e:
        print(f"[wm] Failed to launch client: {e}")
        return None


# ── Monitor info ──────────────────────────────────────────────

def get_monitors() -> list[dict]:
    """
    Return list of monitors as dicts: {index, x, y, w, h, name, is_primary}
    Uses xrandr to parse connected monitors.
    Monitors are sorted so the primary monitor is always index 0.
    """
    rc, out, err = _run(["xrandr", "--query"])
    if rc != 0:
        return [{"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080,
                 "name": "default", "is_primary": True}]

    monitors = []
    # Match lines like: HDMI-0 connected primary 1920x1080+1920+0
    # or:               DP-1 connected 1920x1080+0+0
    pattern = re.compile(r"(\S+) connected( primary)? (\d+)x(\d+)\+(\d+)\+(\d+)")
    for line in out.splitlines():
        m = pattern.search(line)
        if m:
            monitors.append({
                "name":       m.group(1),
                "is_primary": m.group(2) is not None,
                "w":          int(m.group(3)),
                "h":          int(m.group(4)),
                "x":          int(m.group(5)),
                "y":          int(m.group(6)),
            })

    if not monitors:
        return [{"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080,
                 "name": "default", "is_primary": True}]

    # Sort: primary first, then by x position
    monitors.sort(key=lambda m: (0 if m["is_primary"] else 1, m["x"]))

    # Assign indices after sorting
    for i, mon in enumerate(monitors):
        mon["index"] = i

    return monitors


