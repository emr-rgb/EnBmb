#!/usr/bin/env python3
# ============================================================
#  EnB Multibox Manager — main.py
#  Entry point — run this to start the application
#
#  Requirements (install via pacman on CachyOS):
#    sudo pacman -S python python-tk xdotool wmctrl xorg-xrandr
#
#  Run on X11 session only (not Wayland):
#    python3 main.py
# ============================================================

import sys
import os
import signal
import subprocess
import threading

# Ensure we can import from our own directory
sys.path.insert(0, os.path.dirname(__file__))

import tkinter as tk
from tkinter import ttk, messagebox

# Prevent Ctrl+Z from suspending the process — a suspended Tkinter app leaves
# a broken empty window on screen that can only be killed with kill -9.
if hasattr(signal, 'SIGTSTP'):
    signal.signal(signal.SIGTSTP, signal.SIG_IGN)


def ensure_admin_windows():
    """
    On Windows, relaunch elevated if not already running as admin, so child
    processes (LaunchNet7.exe, which requires admin) inherit the token instead
    of each one popping its own UAC prompt.
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = True  # if we can't tell, don't loop trying to elevate
    if is_admin:
        return
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, os.path.dirname(os.path.abspath(__file__)), 1
    )
    sys.exit(0)


def ensure_shortcuts_windows():
    """
    Create a Desktop and Start Menu shortcut on first launch (Windows only).
    There's no installer on Windows, so this is the only point where a
    "setup" step happens. Idempotent — skipped once both already exist.
    Delete either shortcut anytime; this won't recreate ones you removed.
    """
    if sys.platform != "win32":
        return
    try:
        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop", "EnB Multibox Manager.lnk")
        start_menu_dir = os.path.join(
            os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs"
        )
        start_menu = os.path.join(start_menu_dir, "EnB Multibox Manager.lnk")
        if os.path.exists(desktop) and os.path.exists(start_menu):
            return

        import win32com.client

        app_dir = os.path.dirname(os.path.abspath(__file__))
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        target = pythonw if os.path.exists(pythonw) else sys.executable
        icon = os.path.join(app_dir, "enbmb.ico")

        os.makedirs(start_menu_dir, exist_ok=True)
        shell = win32com.client.Dispatch("WScript.Shell")
        for path in (desktop, start_menu):
            if os.path.exists(path):
                continue
            shortcut = shell.CreateShortCut(path)
            shortcut.TargetPath = target
            shortcut.Arguments = f'"{os.path.join(app_dir, "main.py")}"'
            shortcut.WorkingDirectory = app_dir
            if os.path.exists(icon):
                shortcut.IconLocation = icon
            shortcut.Save()
    except Exception:
        pass  # shortcuts are a convenience, never block launch over this


def _first_run_setup_windows(root, app):
    """Prompt for LaunchNet7.exe on first launch if slot commands are unconfigured (Windows only)."""
    if sys.platform != "win32":
        return
    cmds = app.settings.get("slot_commands") or []
    if any(c.strip() for c in cmds):
        return

    candidates = [
        r"C:\Program Files (x86)\Net-7\bin\LaunchNet7.exe",
        r"C:\Program Files\Net-7\bin\LaunchNet7.exe",
    ]
    found = next((p for p in candidates if os.path.exists(p)), None)

    from tkinter import filedialog

    win = tk.Toplevel(root)
    win.title("First-time setup")
    win.resizable(False, False)
    win.grab_set()
    win.focus_force()

    bg   = "#1a1a2e"
    card = "#0f3460"
    fg   = "#eaeaea"
    acc  = "#e94560"
    win.configure(bg=bg)

    tk.Label(win, text="EnB Launch Command", font=("Courier New", 11, "bold"),
             bg=bg, fg=acc).pack(pady=(16, 2), padx=24)

    if found:
        msg = f"Found LaunchNet7.exe at:\n{found}\n\nConfirm to use this for all 6 slots."
    else:
        msg = ("LaunchNet7.exe not found at default locations.\n"
               "Locate it manually to continue.")
    tk.Label(win, text=msg, font=("Courier New", 9), bg=bg, fg=fg,
             justify="left", wraplength=400).pack(pady=(6, 4), padx=24)

    path_var = tk.StringVar(value=found or "")
    entry = tk.Entry(win, textvariable=path_var, width=54,
                     bg=card, fg=fg, insertbackground=fg, relief="flat")
    entry.pack(pady=4, padx=24, ipady=4)

    def browse():
        p = filedialog.askopenfilename(
            title="Locate LaunchNet7.exe",
            filetypes=[("LaunchNet7", "LaunchNet7.exe"), ("All files", "*.*")],
            initialdir=r"C:\Program Files (x86)\Net-7\bin",
        )
        if p:
            path_var.set(p.replace("/", "\\"))

    def confirm():
        p = path_var.get().strip()
        if not p:
            return
        n = len(app.settings.get("slot_commands") or [""] * 6)
        app.settings["slot_commands"] = [p] * n
        from config_manager import save_settings
        save_settings(app.settings)
        win.destroy()

    btn_row = tk.Frame(win, bg=bg)
    btn_row.pack(pady=(8, 20), padx=24)
    tk.Button(btn_row, text="Browse…", command=browse,
              bg=card, fg=fg, activebackground=card, activeforeground=fg,
              relief="flat", padx=14, pady=4).pack(side="left", padx=(0, 8))
    tk.Button(btn_row, text="Confirm", command=confirm,
              bg=acc, fg="white", activebackground=acc, activeforeground="white",
              relief="flat", padx=14, pady=4).pack(side="left")

    win.wait_window()


def check_display():
    """Make sure we're running under X11, not Wayland (Linux only)."""
    if sys.platform == "win32":
        return
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    display = os.environ.get("DISPLAY", "")

    if session == "wayland":
        print("ERROR: Wayland detected. Please log into an X11 session to use this tool.")
        print("At your login screen, select 'Plasma (X11)' instead of 'Plasma (Wayland)'.")
        sys.exit(1)

    if not display:
        print("ERROR: No DISPLAY variable found. Are you running in a graphical session?")
        sys.exit(1)


def main():
    check_display()

    root = tk.Tk()

    # Apply ttk theme to match our dark style
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Style ttk widgets to match our theme
    bg    = "#1a1a2e"
    card  = "#0f3460"
    text  = "#eaeaea"
    dim   = "#888888"
    acc   = "#e94560"

    style.configure("TCombobox",
                    fieldbackground=card,
                    background=card,
                    foreground=text,
                    arrowcolor=acc,
                    selectbackground=card,
                    selectforeground=text)
    style.map("TCombobox",
              fieldbackground=[("readonly", card)],
              selectbackground=[("readonly", card)],
              selectforeground=[("readonly", text)])
    style.configure("TNotebook",
                    background=bg,
                    borderwidth=0)
    style.configure("TNotebook.Tab",
                    background=card,
                    foreground=text,
                    padding=[10, 4],
                    font=("Courier New", 9))
    style.map("TNotebook.Tab",
              background=[("selected", acc)],
              foreground=[("selected", "white")])
    style.configure("TPanedwindow", background=bg)

    # Apply saved theme before building UI
    try:
        from config_manager import load_settings
        from constants import get_theme
        import constants
        saved = load_settings()
        constants.THEME = get_theme(saved.get("theme", "Dark Navy"))
    except Exception:
        pass

    # Import here so any import errors show clearly
    try:
        from gui_main import EnBMultiboxApp
    except ImportError as e:
        messagebox.showerror("Import Error",
                             f"Failed to load application modules:\n\n{e}\n\n"
                             f"Make sure all .py files are in the same directory.")
        sys.exit(1)

    app = EnBMultiboxApp(root)
    root.after(300, lambda: _first_run_setup_windows(root, app))

    # Start the state monitor silently in the background — logs to logs/monitor.log,
    # writes current state to logs/monitor_state.json. Daemon thread so it dies with
    # the process. Failure to import (e.g. missing psutil) is non-fatal.
    try:
        from enb_monitor import monitor_loop
        _monitor_stop  = threading.Event()
        _zone_timeout  = float(app.settings.get("frozen_zone_timeout_s", 20))
        def _monitor_crash_cb(slot_num, prev_state, new_state):
            root.after(0, lambda: app._on_monitor_crash(slot_num, prev_state, new_state))
        threading.Thread(
            target=monitor_loop, args=(_monitor_stop,),
            kwargs={
                "on_state_change":       _monitor_crash_cb,
                "frozen_zone_timeout_s": _zone_timeout,
                "excluded_pids":         app._independent_pids,
            },
            daemon=True, name="enb-monitor"
        ).start()
    except Exception as e:
        print(f"[monitor] Could not start: {e}")

    root.protocol("WM_DELETE_WINDOW", app._quit)
    signal.signal(signal.SIGINT, lambda *_: app._quit())
    root.mainloop()


if __name__ == "__main__":
    ensure_shortcuts_windows()
    ensure_admin_windows()
    main()
