# ============================================================
#  EnB Multibox Manager — window_manager.py  (Windows native)
#  Window detection, renaming, moving, resizing via pywin32.
#  Replaces the Linux/X11 version (xdotool/wmctrl/Xlib).
#
#  Requires: pip install pywin32 psutil
# ============================================================

import os
import re
import time
import threading
import subprocess

import win32gui
import win32api
import win32con
import win32process

import psutil

from constants import ENB_WINDOW_NAMES

# ── Key timing globals ────────────────────────────────────────
_key_hold_ms: int       = 30
_modifier_delay_ms: int = 50


def configure_key_timing(hold_ms: int = 30, mod_delay_ms: int = 50) -> None:
    global _key_hold_ms, _modifier_delay_ms
    _key_hold_ms       = max(0, hold_ms)
    _modifier_delay_ms = max(0, mod_delay_ms)


# ── Virtual key code map ──────────────────────────────────────

_VK_MAP: dict[str, int] = {
    "escape":    win32con.VK_ESCAPE,
    "esc":       win32con.VK_ESCAPE,
    "return":    win32con.VK_RETURN,
    "enter":     win32con.VK_RETURN,
    "space":     win32con.VK_SPACE,
    "tab":       win32con.VK_TAB,
    "backspace": win32con.VK_BACK,
    "delete":    win32con.VK_DELETE,
    "grave":     0xC0,   # VK_OEM_3  (backtick/tilde key)
    "`":         0xC0,
    "f1":  win32con.VK_F1,  "f2":  win32con.VK_F2,
    "f3":  win32con.VK_F3,  "f4":  win32con.VK_F4,
    "f5":  win32con.VK_F5,  "f6":  win32con.VK_F6,
    "f7":  win32con.VK_F7,  "f8":  win32con.VK_F8,
    "f9":  win32con.VK_F9,  "f10": win32con.VK_F10,
    "f11": win32con.VK_F11, "f12": win32con.VK_F12,
    # Modifier names (used when releasing)
    "alt":   win32con.VK_MENU,
    "ctrl":  win32con.VK_CONTROL,
    "shift": win32con.VK_SHIFT,
    "super": win32con.VK_LWIN,
}

_MOD_VK: dict[str, int] = {
    "alt":   win32con.VK_MENU,
    "ctrl":  win32con.VK_CONTROL,
    "shift": win32con.VK_SHIFT,
    "super": win32con.VK_LWIN,
}


def _vk(key: str) -> int | None:
    """Return the virtual key code for a key name string, or None if unknown."""
    k = key.lower().strip()
    if k in _VK_MAP:
        return _VK_MAP[k]
    if len(k) == 1:
        code = win32api.VkKeyScan(k)
        if code != -1:
            return code & 0xFF
    return None


# ── Dependency check ──────────────────────────────────────────

def check_pywin32() -> bool:
    """Return True if pywin32 is available (should always be True on Windows)."""
    try:
        import win32gui as _
        return True
    except ImportError:
        return False


# ── Modifier handling ─────────────────────────────────────────

def release_modifiers() -> None:
    """Release any stuck modifier keys. Called at the start of every loop thread."""
    for vk in (win32con.VK_MENU, win32con.VK_CONTROL,
                win32con.VK_SHIFT, win32con.VK_LWIN):
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)


def wait_modifiers_released(timeout_s: float = 0.5) -> None:
    """Block until physical modifier keys are no longer held, or timeout expires."""
    mod_vks = (win32con.VK_SHIFT, win32con.VK_CONTROL,
               win32con.VK_MENU, win32con.VK_LWIN)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not any(win32api.GetAsyncKeyState(vk) & 0x8000 for vk in mod_vks):
            break
        time.sleep(0.02)


# ── Window discovery ──────────────────────────────────────────

def slot_wine_prefix(index: int) -> str:
    """
    Linux/Wine concept (per-slot prefix used to disambiguate windows after
    X11 ID reuse) has no Windows equivalent — windows here are never tagged
    with a "wine_prefix" key, so this returns a sentinel that can never match
    `w.get("wine_prefix")` (which is always None on Windows). This makes the
    prefix-match branch in relaunch detection a no-op, falling through to the
    general ID-novelty check, which is sufficient on Windows (no HWND reuse
    issue in practice).
    """
    return f"__no_wine_prefix_slot_{index}__"


def get_all_windows() -> list[dict]:
    """
    Return list of all visible top-level windows as dicts:
    {id: int (HWND), title: str, pid: int, x: int, y: int, w: int, h: int}
    """
    windows = []

    def _callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            rect = win32gui.GetWindowRect(hwnd)
            x, y, x2, y2 = rect
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            windows.append({
                "id":    hwnd,
                "title": title.strip(),
                "pid":   pid,
                "x": x, "y": y,
                "w": x2 - x, "h": y2 - y,
            })
        except Exception:
            pass

    win32gui.EnumWindows(_callback, None)
    return windows


def find_enb_windows(extra_names: list[str] = None) -> list[dict]:
    """
    Return windows that look like EnB clients.
    Matches on known window title substrings, role abbreviations,
    and any extra_names provided (e.g. character names from slots).
    """
    from constants import CLASS_ABBREVS
    all_wins    = get_all_windows()
    enb         = []
    known_titles = set(CLASS_ABBREVS)
    if extra_names:
        known_titles.update(n.strip() for n in extra_names if n.strip())

    for win in all_wins:
        title   = win["title"].strip()
        matched = False

        for name in ENB_WINDOW_NAMES:
            if name.lower() in title.lower():
                matched = True
                break

        if not matched and title in known_titles:
            matched = True

        if matched and win not in enb:
            enb.append(win)

    return enb


def get_window_by_id(hwnd: int) -> dict | None:
    """Fetch current geometry/title for a specific window handle."""
    all_wins = get_all_windows()
    for w in all_wins:
        if w["id"] == hwnd:
            return w
    return None


def get_active_window_id() -> int:
    """Return the HWND of the currently active (foreground) window."""
    try:
        return win32gui.GetForegroundWindow()
    except Exception:
        return 0


def get_mouse_position() -> tuple[int, int]:
    """Return the current (x, y) screen position of the mouse cursor."""
    try:
        return win32api.GetCursorPos()
    except Exception:
        return (0, 0)


def window_exists(hwnd: int) -> bool:
    return win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd)


# ── Process management ────────────────────────────────────────

def find_enb_windows_by_process() -> list[dict]:
    """
    Return all visible top-level windows owned by EnB-related processes,
    regardless of window title.  Used as a fallback when title-matching
    misses windows (e.g. EULA dialogs with non-standard titles).
    """
    from constants import ENB_PROCESS_NAMES
    target_names = {n.lower() for n in ENB_PROCESS_NAMES}
    enb_pids: set[int] = set()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if (proc.info['name'] or '').lower() in target_names:
                enb_pids.add(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    results = []
    def _cb(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in enb_pids:
                    rect = win32gui.GetWindowRect(hwnd)
                    x, y, x2, y2 = rect
                    results.append({
                        "id":    hwnd,
                        "title": win32gui.GetWindowText(hwnd).strip(),
                        "pid":   pid,
                        "x": x, "y": y,
                        "w": x2 - x, "h": y2 - y,
                    })
        except Exception:
            pass
        return True

    win32gui.EnumWindows(_cb, None)
    return results


def find_enb_processes() -> dict[str, list[int]]:
    """
    Return {process_name: [pid, ...]} for all running EnB-related processes.
    """
    from constants import ENB_PROCESS_NAMES
    result = {}
    target_names = {n.lower() for n in ENB_PROCESS_NAMES}
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = (proc.info['name'] or '').lower()
            if name in target_names:
                canonical = proc.info['name']
                result.setdefault(canonical, []).append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return result


def kill_all_enb_processes() -> list[str]:
    """
    Terminate all running EnB-related processes.
    Returns list of process names that had running instances.
    """
    from constants import ENB_PROCESS_NAMES
    target_names = {n.lower() for n in ENB_PROCESS_NAMES}

    target_pids: set[int] = set()
    target_procs = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = (proc.info['name'] or '').lower()
            if name in target_names:
                target_pids.add(proc.info['pid'])
                target_procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if target_pids:
        def _hide(hwnd: int, _) -> bool:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid in target_pids:
                        _remove_from_taskbar(hwnd)
            except Exception:
                pass
            return True
        win32gui.EnumWindows(_hide, None)

    killed = []
    for proc in target_procs:
        try:
            proc.kill()
            killed.append(proc.info['name'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        _nudge_taskbar()
    return killed


def _remove_from_taskbar(hwnd: int) -> None:
    """Forcibly drop a window's taskbar button, independent of process state.

    Plain ShowWindow(SW_HIDE) often leaves a ghost button until something else
    (e.g. the user hovering over it) makes the shell re-check whether the
    window is still there — especially when the owning process is about to be
    killed rather than exiting normally. Toggling WS_EX_TOOLWINDOW in and
    WS_EX_APPWINDOW out, with a hide/show/hide cycle, is the standard trick for
    making the shell immediately re-evaluate and drop the taskbar association.
    Works cross-process since window styles aren't thread-bound the way
    DestroyWindow is.
    """
    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        style = (style | win32con.WS_EX_TOOLWINDOW) & ~win32con.WS_EX_APPWINDOW
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNA)
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
    except Exception:
        pass


def _nudge_taskbar() -> None:
    """Force Explorer's taskbar to repaint immediately.

    SW_HIDE on a window removes its taskbar button eventually, but the
    taskbar's own redraw is lazy — it often doesn't notice until some other
    event (e.g. the user hovering over the stale button) triggers a repaint.
    Forcing a RedrawWindow on Shell_TrayWnd (and its children) makes it
    notice right away instead of leaving a ghost button hanging around.
    """
    try:
        hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
        if hwnd:
            win32gui.RedrawWindow(
                hwnd, None, None,
                win32con.RDW_INVALIDATE | win32con.RDW_UPDATENOW | win32con.RDW_ALLCHILDREN,
            )
    except Exception:
        pass


def refresh_taskbar(enb_pids: set[int] = None) -> None:
    """Hide orphaned EnB windows so the shell removes their ghost taskbar buttons.

    If enb_pids is provided, only windows owned by those specific PIDs are
    hidden (safe even when all EnB processes are already dead).  Without it,
    falls back to title-matching so we don't accidentally hide unrelated windows.
    """
    from constants import ENB_PROCESS_NAMES, ENB_WINDOW_NAMES

    if enb_pids is not None:
        # Fast path: hide only windows whose PID we know was an EnB process.
        def _hide_orphan(hwnd: int, _) -> bool:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid in enb_pids:
                        _remove_from_taskbar(hwnd)
            except Exception:
                pass
            return True
    else:
        # Fallback: hide visible windows whose process is dead AND whose title
        # matches a known EnB window name (avoids touching unrelated windows).
        enb_titles = [n.lower() for n in ENB_WINDOW_NAMES]

        def _hide_orphan(hwnd: int, _) -> bool:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    try:
                        psutil.Process(pid)  # alive — leave it alone
                    except psutil.NoSuchProcess:
                        title = win32gui.GetWindowText(hwnd).lower()
                        if any(n in title for n in enb_titles):
                            _remove_from_taskbar(hwnd)
            except Exception:
                pass
            return True

    try:
        win32gui.EnumWindows(_hide_orphan, None)
    except Exception:
        pass
    _nudge_taskbar()


def sweep_and_clear_enb(pre_wait_ms: int = 500) -> int:
    """
    Full ENB process teardown + taskbar cleanup.

    1. Collect PIDs of all live ENB processes.
    2. Send WM_CLOSE to every visible top-level window owned by those PIDs
       so Windows can follow the normal destroy path (removes taskbar button).
    3. Wait briefly for graceful exit.
    4. Force-kill any survivors with SIGKILL.
    5. Nudge Shell_TrayWnd so ghost buttons disappear immediately.

    Returns the count of windows that received WM_CLOSE.
    """
    from constants import ENB_PROCESS_NAMES
    target_names = {n.lower() for n in ENB_PROCESS_NAMES}

    # Step 1 — collect live ENB PIDs
    enb_pids: set[int] = set()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if (proc.info['name'] or '').lower() in target_names:
                enb_pids.add(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    closed_hwnds: list[int] = []

    if enb_pids:
        # Step 2 — hide then WM_CLOSE every visible top-level window owned by those PIDs.
        # SW_HIDE removes the taskbar button immediately (before the process dies),
        # so the shell never shows a ghost entry regardless of how the process exits.
        def _enum_cb(hwnd: int, _) -> bool:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid in enb_pids:
                        _remove_from_taskbar(hwnd)
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        closed_hwnds.append(hwnd)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_enum_cb, None)

        # Step 3 — brief grace period
        time.sleep(pre_wait_ms / 1000.0)

        # Step 4 — hard-kill survivors
        kill_all_enb_processes()

    # Step 5 — wait briefly for the OS to finalize kills, then hide orphaned windows
    time.sleep(0.3)
    refresh_taskbar(enb_pids)
    return len(closed_hwnds)


def is_enb_client_pid(pid: int) -> bool:
    """
    Return True if pid belongs to a process we should treat as an EnB client.
    On Windows, find_enb_windows() already title-matches, so every result is
    relevant — unlike Linux there's no "is this actually Wine" ambiguity.
    """
    return True


def pid_exists(pid: int) -> bool:
    """Return True if a process with this PID is currently running."""
    return psutil.pid_exists(pid)


def kill_window_process(pid: int) -> bool:
    """Kill a process by PID, hiding its windows first to clear the taskbar button."""
    try:
        proc = psutil.Process(pid)
        def _hide(hwnd: int, _) -> bool:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                    if wpid == pid:
                        _remove_from_taskbar(hwnd)
            except Exception:
                pass
            return True
        win32gui.EnumWindows(_hide, None)
        proc.kill()
        _nudge_taskbar()
        return True
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        print(f"[wm] Permission denied killing PID {pid}")
        return False


# ── Window manipulation ───────────────────────────────────────

def rename_window(hwnd: int, name: str) -> bool:
    """Rename a window's title bar text."""
    try:
        win32gui.SetWindowText(hwnd, name)
        return True
    except Exception as e:
        print(f"[wm] rename_window({hwnd}, {name!r}) failed: {e}")
        return False


def minimize_window(hwnd: int) -> None:
    """Iconify (minimize) a window without killing it."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception:
        pass


def move_resize_window(hwnd: int, x: int, y: int, w: int, h: int) -> bool:
    """Move and resize a window. Restores it first if maximized."""
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        # placement[1] is showCmd; SW_MAXIMIZE=3
        if placement[1] == win32con.SW_MAXIMIZE:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.05)

        win32gui.SetWindowPos(
            hwnd, None, x, y, w, h,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        )
        return True
    except Exception as e:
        print(f"[wm] move_resize_window({hwnd}) failed: {e}")
        return False


def restore_window(hwnd: int) -> None:
    """Un-minimize/un-maximize a window without moving or resizing it."""
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] in (win32con.SW_MAXIMIZE, win32con.SW_MINIMIZE):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass


def raise_window(hwnd: int) -> None:
    """Raise a window to the top of the z-order without stealing focus."""
    try:
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        was_topmost = bool(ex & win32con.WS_EX_TOPMOST)
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
        )
        if not was_topmost:
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
            )
    except Exception:
        pass


def reposition_window(hwnd: int, x: int, y: int) -> None:
    """Move a window without resizing it."""
    try:
        win32gui.SetWindowPos(
            hwnd, None, x, y, 0, 0,
            win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        )
    except Exception:
        pass


def focus_window(hwnd: int) -> bool:
    """Bring a window to focus and raise it."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        win32gui.BringWindowToTop(hwnd)
        return True
    except Exception as e:
        print(f"[wm] focus_window({hwnd}) failed: {e}")
        return False


def activate_window(hwnd: int) -> bool:
    """Activate window (focus + raise)."""
    return focus_window(hwnd)


def return_to_driver(hwnd: int, cx: int, cy: int) -> None:
    """End-of-loop cleanup: activate driver window and move mouse into it."""
    try:
        win32gui.SetForegroundWindow(hwnd)
        win32gui.BringWindowToTop(hwnd)
        win32api.SetCursorPos((cx, cy))
        time.sleep(0.05)
    except Exception:
        pass


def set_stay_on_top(hwnd: int, enable: bool) -> bool:
    """Toggle always-on-top for a window."""
    z_order = win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST
    try:
        win32gui.SetWindowPos(
            hwnd, z_order, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
        )
        return True
    except Exception as e:
        print(f"[wm] set_stay_on_top({hwnd}, {enable}) failed: {e}")
        return False


def get_frame_extents(hwnd: int) -> tuple[int, int, int, int]:
    """
    Return the non-client frame size as (left, right, top, bottom).
    Returns (0, 0, 0, 0) for borderless windows.
    """
    try:
        wx1, wy1, wx2, wy2 = win32gui.GetWindowRect(hwnd)
        cx1, cy1, cx2, cy2 = win32gui.GetClientRect(hwnd)
        # GetClientRect is relative to client origin (0,0); convert to screen
        client_screen = win32gui.ClientToScreen(hwnd, (0, 0))
        left   = client_screen[0] - wx1
        top    = client_screen[1] - wy1
        right  = (wx2 - wx1) - cx2 - left
        bottom = (wy2 - wy1) - cy2 - top
        return (max(0, left), max(0, right), max(0, top), max(0, bottom))
    except Exception:
        return (0, 0, 0, 0)


def get_toplevel_hwnd(hwnd: int) -> int:
    """
    Return the real top-level frame HWND for a window handle.

    Tkinter's `winfo_id()` on Windows returns the HWND of the toplevel's
    drawable child window, not the decorated frame window itself — calling
    `SetWindowLong(GWL_STYLE, ...)` on that child has no visible effect.
    `GetAncestor(hwnd, GA_ROOT)` walks up to the actual frame HWND that owns
    the title bar/menu, which is what `set_window_borderless` needs to act on.
    """
    try:
        return win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
    except Exception:
        return hwnd


def set_window_borderless(hwnd: int, enable: bool) -> bool:
    """Add or remove window decorations (title bar + resize border)."""
    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if enable:
            style &= ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME)
        else:
            style |= win32con.WS_CAPTION | win32con.WS_THICKFRAME
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        # Force Windows to apply the style change visually
        win32gui.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
            win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
        )
        return True
    except Exception as e:
        print(f"[wm] set_window_borderless({hwnd}, {enable}) failed: {e}")
        return False


def set_bypass_compositor(hwnd: int) -> bool:
    """No-op on Windows (compositor bypass is an X11/Openbox concept)."""
    return True


# ── Focused-window input ──────────────────────────────────────

def type_to_focused(text: str, delay_ms: int = 10) -> bool:
    """
    Type a string into whichever window currently has focus.
    Uses VkKeyScan to handle shifted characters (e.g. uppercase, symbols).
    """
    try:
        for char in text:
            vk_full = win32api.VkKeyScan(char)
            if vk_full == -1:
                continue
            vk_code   = vk_full & 0xFF
            need_shift = bool((vk_full >> 8) & 1)

            if need_shift:
                win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)

            win32api.keybd_event(vk_code, 0, 0, 0)
            time.sleep(delay_ms / 1000.0)
            win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)

            if need_shift:
                win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)

            time.sleep(delay_ms / 1000.0)
        return True
    except Exception as e:
        print(f"[wm] type_to_focused failed: {e}")
        return False


def key_to_focused(key: str) -> bool:
    """
    Send a key to whichever window currently has focus.
    Supports modifier combos like 'alt+f', 'shift+F1', 'ctrl+d'.
    Uses explicit keydown → hold → keyup for reliable game registration.
    """
    hold = _key_hold_ms      / 1000.0
    mdly = _modifier_delay_ms / 1000.0

    if '+' in key:
        parts    = key.split('+', 1)
        mod_name = parts[0].strip().lower()
        key_name = parts[1].strip()

        mod_vk  = _MOD_VK.get(mod_name)
        main_vk = _vk(key_name)

        if mod_vk is None or main_vk is None:
            print(f"[wm] key_to_focused: unknown key combo '{key}'")
            return False

        win32api.keybd_event(mod_vk, 0, 0, 0)
        try:
            time.sleep(mdly)
            win32api.keybd_event(main_vk, 0, 0, 0)
            time.sleep(hold)
            win32api.keybd_event(main_vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.01)
        finally:
            win32api.keybd_event(mod_vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    else:
        vk_code = _vk(key)
        if vk_code is None:
            print(f"[wm] key_to_focused: unknown key '{key}'")
            return False
        win32api.keybd_event(vk_code, 0, 0, 0)
        time.sleep(hold)
        win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True


# ── Input broadcasting ────────────────────────────────────────

def send_key_to_window(hwnd: int, key: str) -> bool:
    """
    Send a keystroke to a window WITHOUT focusing it via PostMessage.
    Uses WM_KEYDOWN / WM_KEYUP. May not work with DirectInput games,
    but EnB uses standard Win32 messages so this should be fine.
    Returns True if PostMessage accepted the command.
    """
    vk_code = _vk(key)
    if vk_code is None:
        print(f"[wm] send_key_to_window: unknown key '{key}'")
        return False
    try:
        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
        time.sleep(_key_hold_ms / 1000.0)
        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0)
        return True
    except Exception as e:
        print(f"[wm] send_key_to_window({hwnd}, {key!r}) failed: {e}")
        return False


def send_keys_to_window(hwnd: int, keys: list[str], delay_ms: int = 50) -> bool:
    """Send multiple keys to a window sequentially."""
    for key in keys:
        ok = send_key_to_window(hwnd, key)
        if not ok:
            return False
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
    return True


def click_at(x: int, y: int, button: int = 1) -> bool:
    """Move mouse to screen coordinates and click."""
    try:
        win32api.SetCursorPos((x, y))
        time.sleep(0.02)
        if button == 1:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,  x, y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,    x, y, 0, 0)
        elif button == 3:
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, x, y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP,   x, y, 0, 0)
        return True
    except Exception as e:
        print(f"[wm] click_at({x}, {y}) failed: {e}")
        return False


def mouse_slide_relative(dx: int = 0, dy: int = 400, duration_ms: int = 200,
                          hold_shift: bool = True) -> None:
    """Smoothly move mouse by (dx, dy) relative to current position."""
    try:
        cur = win32api.GetCursorPos()
        start_x, start_y = cur

        steps      = max(1, duration_ms // 10)
        step_sleep = duration_ms / 1000.0 / steps

        if hold_shift:
            win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
            time.sleep(0.02)

        for i in range(1, steps + 1):
            nx = start_x + round(dx * i / steps)
            ny = start_y + round(dy * i / steps)
            win32api.SetCursorPos((nx, ny))
            time.sleep(step_sleep)

        if hold_shift:
            time.sleep(0.02)
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception as e:
        print(f"[wm] mouse_slide_relative failed: {e}")


def mouse_drag(x1: int, y1: int, x2: int, y2: int,
               steps: int = 12, hold_shift: bool = False) -> bool:
    """Drag mouse from (x1,y1) to (x2,y2) with optional Shift held."""
    try:
        win32api.SetCursorPos((x1, y1))
        time.sleep(0.02)
        if hold_shift:
            win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
            time.sleep(0.02)

        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x1, y1, 0, 0)
        step_x = (x2 - x1) / steps
        step_y = (y2 - y1) / steps
        for i in range(1, steps + 1):
            nx = int(x1 + step_x * i)
            ny = int(y1 + step_y * i)
            win32api.SetCursorPos((nx, ny))
            time.sleep(0.015)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x2, y2, 0, 0)

        if hold_shift:
            time.sleep(0.02)
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"[wm] mouse_drag failed: {e}")
        return False


# ── Process launching ─────────────────────────────────────────

def _dismiss_launcher_window(delay_s: float = 1.0) -> None:
    time.sleep(delay_s)
    try:
        hwnds = []
        def _cb(hwnd, _):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if win32gui.IsWindowVisible(hwnd) and "LaunchNet7" in psutil.Process(pid).name():
                    hwnds.append(hwnd)
            except Exception:
                pass
            return True
        win32gui.EnumWindows(_cb, None)
        for hwnd in hwnds:
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.1)
            win32api.keybd_event(win32con.VK_SPACE, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(win32con.VK_SPACE, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception as e:
        print(f"[wm] _dismiss_launcher_window: {e}")


def launch_enb_client(command: str) -> int | None:
    """
    Launch an EnB client with the given command.
    Returns the PID of the launched process, or None on failure.
    Window dismissal (launcher Enter, EULA Enter) is handled by the caller.
    """
    if not command:
        print("[wm] No launch command configured")
        return None
    try:
        cwd = os.path.dirname(command.strip('"')) if "LaunchNet7" in command else None
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
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
    Uses win32api.EnumDisplayMonitors.
    Primary monitor is always index 0.
    """
    monitors = []
    try:
        for hmon, _hdc, rect in win32api.EnumDisplayMonitors():
            info = win32api.GetMonitorInfo(hmon)
            mx1, my1, mx2, my2 = info['Monitor']
            is_primary = bool(info.get('Flags', 0) & 1)
            monitors.append({
                "name":       str(int(hmon)),
                "is_primary": is_primary,
                "x":  mx1, "y":  my1,
                "w":  mx2 - mx1,
                "h":  my2 - my1,
            })
    except Exception as e:
        print(f"[wm] get_monitors failed: {e}")

    if not monitors:
        return [{"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080,
                 "name": "default", "is_primary": True}]

    monitors.sort(key=lambda m: (0 if m["is_primary"] else 1, m["x"]))
    for i, mon in enumerate(monitors):
        mon["index"] = i

    return monitors
