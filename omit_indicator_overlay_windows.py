#!/usr/bin/env python3
"""Transparent text overlay for enbmb slot indicator — Windows version.

Runs as a subprocess of gui_main.py.  State is communicated via two temp
JSON files (paths passed as argv[1]/argv[2]).

Technique:
  - tkinter Tk with overrideredirect + -topmost
  - -transparentcolor chroma-keys the background colour so it becomes
    fully transparent, leaving only the drawn text visible
  - WS_EX_LAYERED | WS_EX_TRANSPARENT makes the window click-through
    (mouse events fall through to whatever is beneath)
  - When drag-mode is active, WS_EX_TRANSPARENT is removed so the
    window can receive mouse events
"""
import sys
import os
import json
import signal
import tempfile
import ctypes
import tkinter as tk
import win32gui
import win32con

_tmp = tempfile.gettempdir()
STATE_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_tmp, "enbmb-indicator-state.json")
DRAG_FILE  = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_tmp, "enbmb-indicator-drag.json")

# Near-black used as the transparency chroma key.
# Must not appear in any text colour.  #000001 = rgb(0,0,1).
_CHROMA = "#000001"

# Win32 virtual-screen metrics constants
_SM_XVIRTUALSCREEN  = 76
_SM_YVIRTUALSCREEN  = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79


def _virtual_screen():
    u32 = ctypes.windll.user32
    x = u32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
    y = u32.GetSystemMetrics(_SM_YVIRTUALSCREEN)
    w = u32.GetSystemMetrics(_SM_CXVIRTUALSCREEN) or 1920
    h = u32.GetSystemMetrics(_SM_CYVIRTUALSCREEN) or 1080
    return x, y, w, h


class IndicatorOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("enbmb-indicator-overlay")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-transparentcolor", _CHROMA)
        self.root.configure(bg=_CHROMA)

        vx, vy, vw, vh = _virtual_screen()
        self.root.geometry(f"{vw}x{vh}+{vx}+{vy}")

        self.canvas = tk.Canvas(
            self.root, bg=_CHROMA, highlightthickness=0, width=vw, height=vh
        )
        self.canvas.pack()

        # Apply WS_EX_LAYERED | WS_EX_TRANSPARENT so the overlay is click-through.
        # winfo_id() returns a child widget HWND on Windows, not the top-level window.
        # GetAncestor(GA_ROOT=2) walks up to the actual window handle.
        self.root.update_idletasks()
        _child_hwnd = self.root.winfo_id()
        self._hwnd = ctypes.windll.user32.GetAncestor(_child_hwnd, 2)
        if not self._hwnd:
            self._hwnd = _child_hwnd
        self._set_click_through(True)

        self._state       = {}
        self._last_mtime  = 0
        self._draw_x      = 20
        self._draw_y      = 280
        self._drag_mode   = False
        self._drag_active = False
        self._drag_ox     = 0
        self._drag_oy     = 0

        self.canvas.bind("<ButtonPress-1>",  self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.root.after(150, self._poll)

    # ── Win32 click-through ───────────────────────────────────

    def _set_click_through(self, passthrough: bool):
        ex = win32gui.GetWindowLong(self._hwnd, win32con.GWL_EXSTYLE)
        ex |= win32con.WS_EX_LAYERED
        if passthrough:
            ex |= win32con.WS_EX_TRANSPARENT
        else:
            ex &= ~win32con.WS_EX_TRANSPARENT
        win32gui.SetWindowLong(self._hwnd, win32con.GWL_EXSTYLE, ex)

    # ── Drag mode ─────────────────────────────────────────────

    def _set_drag_mode(self, enabled: bool):
        if enabled == self._drag_mode:
            return
        self._drag_mode = enabled
        if not enabled:
            self._drag_active = False
        self._set_click_through(not enabled)
        self.canvas.config(cursor="fleur" if enabled else "")

    def _on_press(self, event):
        if self._drag_mode:
            self._drag_active = True
            self._drag_ox = event.x_root - self._draw_x
            self._drag_oy = event.y_root - self._draw_y

    def _on_motion(self, event):
        if self._drag_active:
            self._draw_x = event.x_root - self._drag_ox
            self._draw_y = event.y_root - self._drag_oy
            self._redraw()

    def _on_release(self, event):
        if self._drag_active:
            self._drag_active = False
            try:
                with open(DRAG_FILE, "w", encoding="utf-8") as f:
                    json.dump({"x": self._draw_x, "y": self._draw_y}, f)
            except Exception:
                pass

    # ── Drawing ───────────────────────────────────────────────

    def _redraw(self):
        self.canvas.delete("all")
        state = self._state
        text = state.get("text", "")
        if not text or not state.get("enabled", False):
            return

        font_size  = max(8, int(state.get("font_size", 48)))
        text_color = state.get("text_color", "#ffffff")
        font = ("Courier New", font_size, "bold")
        x, y = self._draw_x, self._draw_y

        # 8-directional shadow in near-black (not chroma-keyed)
        for ox, oy in [(-1, -1), (1, -1), (-1, 1), (1, 1),
                       (0, -1),  (0, 1),  (-1, 0), (1, 0)]:
            self.canvas.create_text(
                x + ox, y + oy, text=text, font=font,
                fill="#000000", anchor="nw"
            )

        self.canvas.create_text(x, y, text=text, font=font,
                                fill=text_color, anchor="nw")

    # ── State polling ─────────────────────────────────────────

    def _poll(self):
        if not os.path.exists(STATE_FILE):
            self.root.quit()
            return
        try:
            mtime = os.path.getmtime(STATE_FILE)
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                with open(STATE_FILE, encoding="utf-8") as f:
                    self._state = json.load(f)
                self._set_drag_mode(self._state.get("drag_mode", False))
                self._refresh()
        except Exception:
            pass
        self.root.after(150, self._poll)

    def _refresh(self):
        state = self._state
        opacity = float(state.get("opacity", 1.0))
        self.root.wm_attributes("-alpha", max(0.01, min(1.0, opacity)))

        if not state.get("enabled", False):
            self.root.withdraw()
            return

        if not self._drag_mode:
            self._draw_x = int(state.get("x", 20))
            self._draw_y = int(state.get("y", 280))

        if not self.root.winfo_viewable():
            self.root.deiconify()

        self._redraw()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    _app = None

    def _on_sigterm(*_):
        if _app is not None:
            _app.root.quit()

    signal.signal(signal.SIGTERM, _on_sigterm)
    _app = IndicatorOverlay()
    _app.run()
