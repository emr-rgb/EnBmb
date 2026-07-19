# ============================================================
#  EnB Multibox Manager — gui_settings.py
#  Settings window with click-to-capture hotkey binding,
#  monitor detection, and per-role assist coordinate editor.
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox
from constants import (
    THEME, DEFAULT_HOTKEYS, HOTKEY_DEFS, KEY_DISPLAY_NAMES,
    MAX_SLOTS, ENB_CLASSES, CLASS_ABBREVS
)

def tk_color(key):
    return THEME[key]

def autowrap(label):
    """Make a Label wrap to its own allocated width when the window resizes."""
    label.bind("<Configure>", lambda e: label.config(wraplength=max(e.width - 4, 40)))
    return label

def _center_on_parent(dlg, parent):
    """Centre dlg over parent after geometry is committed."""
    dlg.update_idletasks()
    dw, dh = dlg.winfo_width(), dlg.winfo_height()
    px, py = parent.winfo_rootx(), parent.winfo_rooty()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    x = max(0, px + (pw - dw) // 2)
    y = max(0, py + (ph - dh) // 2)
    dlg.geometry(f"+{x}+{y}")

def _apply_autowrap_all(widget):
    """Recursively bind wraplength-to-width on every Label in the widget tree.
    Safe to call after the full UI is built — adds to existing bindings."""
    if isinstance(widget, tk.Label):
        widget.bind("<Configure>",
                    lambda e, w=widget: w.config(wraplength=max(e.width - 4, 40)),
                    add="+")
    for child in widget.winfo_children():
        _apply_autowrap_all(child)

# ── Hotkey capture widget ─────────────────────────────────────

class HotkeyField(tk.Frame):
    """
    A field that captures a key combination when clicked.
    Click it → turns yellow and shows 'Press a key...'
    Press any key (with optional Ctrl/Alt/Shift) → saves and displays
    a human-friendly name like 'Ctrl + F1' or '` (backtick)'.
    Press Escape while capturing → cancels and restores previous value.
    """

    def __init__(self, parent, initial_value: str = "", **kwargs):
        super().__init__(parent, bg=tk_color("card_bg"),
                         highlightthickness=1,
                         highlightbackground=tk_color("slot_border"),
                         takefocus=1,
                         **kwargs)
        self._value     = initial_value
        self._capturing = False
        self._prev_value = initial_value

        self._label = tk.Label(
            self,
            text=self._format(initial_value),
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_mono"],
            width=22, anchor="w", padx=6, pady=3,
            cursor="hand2",
        )
        self._label.pack(fill="x")

        self._label.bind("<Button-1>", self._start_capture)
        self.bind("<Button-1>",        self._start_capture)

    def _format(self, raw: str) -> str:
        """Convert internal key string to a human-readable display."""
        if not raw:
            return "(not set — click to bind)"
        parts = raw.split("+")
        result = []
        for p in parts:
            pl = p.lower()
            if pl == "ctrl":
                result.append("Ctrl")
            elif pl == "alt":
                result.append("Alt")
            elif pl == "shift":
                result.append("Shift")
            else:
                result.append(KEY_DISPLAY_NAMES.get(p, p))
        return " + ".join(result)

    def _start_capture(self, _=None):
        if self._capturing:
            return
        self._capturing  = True
        self._prev_value = self._value
        self._label.configure(
            text="▶  Press a key...",
            bg=tk_color("accent2"),
            fg=tk_color("text_dark"),
        )
        self.configure(highlightbackground=tk_color("accent2"))
        self.bind("<KeyPress>", self._on_key)
        self.focus_set()

    def _on_key(self, event):
        if not self._capturing:
            return

        mods = []
        state = event.state
        if state & 0x4: mods.append("ctrl")
        if state & 0x8: mods.append("alt")
        if state & 0x1: mods.append("shift")

        keysym = event.keysym

        if keysym == "Escape" and not mods:
            self._cancel_capture()
            return

        # Ignore bare modifier presses
        if keysym in ("Control_L", "Control_R", "Alt_L", "Alt_R",
                      "Shift_L",   "Shift_R",   "Super_L", "Super_R",
                      "Meta_L",    "Meta_R"):
            return

        # Block system shortcuts that must never be overridden
        blocked = {("alt", "Tab"), ("alt", "F4"), ("super", "Tab")}
        key_mods = frozenset(mods)
        for bmod, bkey in blocked:
            if bkey == keysym and bmod in key_mods:
                return

        self._value = "+".join(mods + [keysym])
        self._finish_capture()

    def _finish_capture(self):
        self._capturing = False
        self._label.configure(
            text=self._format(self._value),
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
        )
        self.configure(highlightbackground=tk_color("slot_border"))
        self.unbind("<KeyPress>")

    def _cancel_capture(self):
        self._value     = self._prev_value
        self._capturing = False
        self._label.configure(
            text=self._format(self._value),
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
        )
        self.configure(highlightbackground=tk_color("slot_border"))
        self.unbind("<KeyPress>")

    def get(self) -> str:
        return self._value

    def set(self, value: str):
        self._value = value
        self._label.configure(text=self._format(value))

    def clear(self):
        self._value = ""
        self._label.configure(text="(not set — click to bind)")


# ── Settings Window ───────────────────────────────────────────

class SettingsWindow:

    def __init__(self, parent, settings: dict, on_save, monitors: list = None, initial_tab: str = None, drag_mode_toggle=None, capture_click=None):
        self.settings             = dict(settings)
        self.on_save              = on_save
        self.monitors             = monitors or []
        self._initial_tab         = initial_tab
        self._drag_mode_toggle    = drag_mode_toggle
        self._capture_click_fn    = capture_click

        self.win = tk.Toplevel(parent)
        self.win.title("Settings")
        self.win.configure(bg=tk_color("bg"))
        self.win.grab_set()
        self.win.resizable(True, True)

        self._cycle_x      = tk.StringVar(value="0")
        self._cycle_y      = tk.StringVar(value="0")

        self._build()

    def _calibrate_coord(self, update_fn):
        """Iconify settings window, wait for a click in a game window, call update_fn(x_pct, y_pct)."""
        from tkinter import messagebox as _mb
        if self._capture_click_fn is None:
            _mb.showwarning("Not available", "Click capture requires a running game client.", parent=self.win)
            return
        def on_result(x_pct, y_pct):
            if x_pct is None:
                return
            update_fn(x_pct, y_pct)
        self._capture_click_fn(on_result)

    def _coord_set_row(self, parent, label_text, x_var, y_var):
        """Build [Label] [Set] (X%, Y%) row for a percentage coord. Returns the frame."""
        def _fmt():
            try:
                xp, yp = float(x_var.get()), float(y_var.get())
            except (ValueError, TypeError):
                return "(not set)"
            return "(not set)" if (xp == 0.0 and yp == 0.0) else f"({xp*100:.1f}%, {yp*100:.1f}%)"

        display_var = tk.StringVar(value=_fmt())

        def _do_set():
            def _update(xp, yp):
                x_var.set(str(round(xp, 6)))
                y_var.set(str(round(yp, 6)))
                display_var.set(_fmt())
            self._calibrate_coord(_update)

        row_f = tk.Frame(parent, bg=tk_color("bg"))
        tk.Label(row_f, text=label_text, bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=22, anchor="w").pack(side="left")
        tk.Button(row_f, text="Set", command=_do_set,
                  bg=tk_color("accent"), fg="white",
                  font=THEME["font_small"], relief="flat", padx=8
                  ).pack(side="left", padx=(0, 8))
        tk.Label(row_f, textvariable=display_var,
                 bg=tk_color("bg"), fg=tk_color("accent2"),
                 font=THEME["font_mono"]).pack(side="left")
        return row_f

    def _bind_mousewheel(self, canvas):
        """Bind mousewheel scrolling to a canvas while the cursor is over it.

        Linux/X11 sends Button-4/5; Windows (and macOS) send <MouseWheel> with
        event.delta (multiples of 120 on Windows, positive = scroll up).
        """
        def _scroll(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
        def _scroll_wheel(event):
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        def _on_enter(_):
            self.win.bind("<Button-4>", _scroll)
            self.win.bind("<Button-5>", _scroll)
            self.win.bind("<MouseWheel>", _scroll_wheel)
        def _on_leave(_):
            self.win.unbind("<Button-4>")
            self.win.unbind("<Button-5>")
            self.win.unbind("<MouseWheel>")
        canvas.bind("<Enter>", _on_enter)
        canvas.bind("<Leave>", _on_leave)

    def _build(self):
        tk.Label(self.win, text="SETTINGS",
                 bg=tk_color("bg"), fg=tk_color("accent"),
                 font=THEME["font_title"], pady=8
                 ).pack(fill="x", padx=12)
        tk.Frame(self.win, bg=tk_color("accent"), height=1).pack(fill="x")

        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_hotkeys_tab(nb)
        self._build_general_tab(nb)
        self._build_login_tab(nb)
        self._build_monitors_tab(nb)
        self._build_layout_tab(nb)
        self._build_invite_tab(nb)
        self._build_reform_tab(nb)
        self._build_loops_tab(nb)
        self._build_indicator_tab(nb)
        self._build_roles_tab(nb)
        self._build_characters_tab(nb)

        if self._initial_tab:
            for i in range(nb.index("end")):
                if nb.tab(i, "text") == self._initial_tab:
                    nb.select(i)
                    break

        # Size window so the tab bar fits without wrapping.
        # Measure each tab label's text width and sum — avoids using winfo_reqwidth()
        # which returns the widest tab *content* (far too wide).
        self.win.update_idletasks()
        try:
            import tkinter.font as tkfont
            f = tkfont.nametofont("TkDefaultFont")
            tab_bar_w = sum(
                f.measure(nb.tab(i, "text")) + 36          # 36px padding per tab
                for i in range(nb.index("end"))
            ) + 24                                          # outer margin
        except Exception:
            tab_bar_w = 0
        needed_w = max(tab_bar_w, 620)
        self.win.geometry(f"{needed_w}x680")
        self.win.minsize(needed_w, 520)
        _center_on_parent(self.win, self.win.master)

        btn_row = tk.Frame(self.win, bg=tk_color("bg"))
        btn_row.pack(fill="x", padx=8, pady=(0, 8))

        tk.Button(btn_row, text="Save & Close", command=self._save,
                  bg=tk_color("success"), fg="white",
                  font=THEME["font_main"], relief="flat", padx=16, pady=5
                  ).pack(side="right", padx=4)
        tk.Button(btn_row, text="Cancel", command=self.win.destroy,
                  bg=tk_color("card_bg"), fg=tk_color("text"),
                  font=THEME["font_main"], relief="flat", padx=16, pady=5
                  ).pack(side="right")
        tk.Button(btn_row, text="Reset Hotkeys to Default",
                  command=self._reset_hotkeys,
                  bg=tk_color("warning"), fg="white",
                  font=THEME["font_small"], relief="flat", padx=8, pady=5
                  ).pack(side="left")

        # Apply wraplength-to-width on every Label in the whole window.
        # Done once here so new tabs added in future get it for free.
        self.win.update_idletasks()
        _apply_autowrap_all(self.win)

    # ── Hotkeys tab ───────────────────────────────────────────

    def _build_hotkeys_tab(self, nb):
        outer = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(outer, text="Hotkeys")

        autowrap(tk.Label(outer,
                 text="  Click any field below, then press the key (or key combination) you want.\n"
                      "  Escape cancels. ✕ clears the binding.",
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left",
                 padx=8, pady=6,
                 )).pack(fill="x", padx=10, pady=(8, 4))

        # Scrollable list
        canvas = tk.Canvas(outer, bg=tk_color("bg"), highlightthickness=0)
        scroll = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)

        inner = tk.Frame(canvas, bg=tk_color("bg"))
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Stretch the inner frame to fill the canvas width when the canvas is resized.
        # Must bind to canvas <Configure>, not inner — inner's width isn't known yet
        # when inner fires first, causing itemconfig(cw, width=1) which squashes content.
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        self._bind_mousewheel(canvas)

        hk = self.settings.get("hotkeys", DEFAULT_HOTKEYS.copy())
        self._hk_fields = {}

        for key, (label, description) in HOTKEY_DEFS.items():
            card = tk.Frame(inner, bg=tk_color("panel_bg"),
                            highlightthickness=1,
                            highlightbackground=tk_color("slot_border"))
            card.pack(fill="x", pady=2, padx=2)

            left = tk.Frame(card, bg=tk_color("panel_bg"))
            left.pack(side="left", fill="x", expand=True, padx=8, pady=5)
            tk.Label(left, text=label,
                     bg=tk_color("panel_bg"), fg=tk_color("text"),
                     font=THEME["font_main"], anchor="w"
                     ).pack(anchor="w")
            tk.Label(left, text=description,
                     bg=tk_color("panel_bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"], anchor="w"
                     ).pack(anchor="w")

            field = HotkeyField(
                card,
                initial_value=hk.get(key, DEFAULT_HOTKEYS.get(key, ""))
            )
            field.pack(side="right", padx=(0, 4), pady=5)

            tk.Button(card, text="✕",
                      command=field.clear,
                      bg=tk_color("panel_bg"), fg=tk_color("text_dim"),
                      font=THEME["font_small"], relief="flat", padx=4
                      ).pack(side="right", pady=5)

            self._hk_fields[key] = field

    # ── General tab ───────────────────────────────────────────

    def _build_general_tab(self, nb):
        frame = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(frame, text="General")

        inner = tk.Frame(frame, bg=tk_color("bg"))
        inner.pack(fill="x", padx=16, pady=12)

        def row(r, label, var, tip="", wide=False, is_spin=False, lo=0, hi=9999):
            tk.Label(inner, text=label,
                     bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"], width=28, anchor="w"
                     ).grid(row=r*2, column=0, sticky="w", pady=(6, 0))
            if is_spin:
                w = tk.Spinbox(inner, from_=lo, to=hi, textvariable=var,
                               width=6, bg=tk_color("card_bg"), fg=tk_color("text"),
                               font=THEME["font_mono"], relief="flat")
            else:
                w = tk.Entry(inner, textvariable=var, width=36 if wide else 12,
                             bg=tk_color("card_bg"), fg=tk_color("text"),
                             insertbackground=tk_color("text"),
                             font=THEME["font_mono"], relief="flat")
            w.grid(row=r*2, column=1, sticky="w", padx=8)
            if tip:
                tk.Label(inner, text=tip,
                         bg=tk_color("bg"), fg=tk_color("text_dim"),
                         font=THEME["font_small"]
                         ).grid(row=r*2+1, column=1, sticky="w", padx=8)

        self._delay_var = tk.StringVar(value=str(self.settings.get("action_delay_ms", 50)))
        row(0, "Action delay (ms):", self._delay_var, "Pause between steps in macros/loops")

        self._char_delay_var = tk.StringVar(value=str(self.settings.get("char_type_delay_ms", 10)))
        row(1, "Char type delay (ms):", self._char_delay_var, "Delay between keystrokes when typing names")

        self._launch_delay_var = tk.StringVar(value=str(self.settings.get("launch_delay_ms", 3000)))
        row(2, "Launch delay (ms):", self._launch_delay_var, "Wait after EULA dismiss before launching next slot")

        self._formation_var = tk.StringVar(value=self.settings.get("default_formation_key", "t"))
        row(2, "Default formation key:", self._formation_var, "Key clients press to join formation (default: t)")

        # Per-slot launch commands
        tk.Frame(inner, bg=tk_color("slot_border"), height=1).grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        tk.Label(inner, text="Slot launch commands:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], anchor="w"
                 ).grid(row=11, column=0, columnspan=2, sticky="w")
        tk.Label(inner, text="Command run when launching or relaunching each slot.",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], anchor="w"
                 ).grid(row=12, column=0, columnspan=2, sticky="w", pady=(0, 4))

        from constants import MAX_SLOTS
        defaults = self.settings.get("slot_commands",
                                     [f"bash ~/bin/enb-slot{i+1}" for i in range(MAX_SLOTS)])
        self._slot_cmd_vars = []
        for i in range(MAX_SLOTS):
            cmd = defaults[i] if i < len(defaults) else f"bash ~/bin/enb-slot{i+1}"
            tk.Label(inner, text=f"Slot {i+1}:",
                     bg=tk_color("bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"], anchor="e", width=8
                     ).grid(row=13+i, column=0, sticky="e", pady=1)
            var = tk.StringVar(value=cmd)
            tk.Entry(inner, textvariable=var, width=36,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     insertbackground=tk_color("text"),
                     font=THEME["font_mono"], relief="flat"
                     ).grid(row=13+i, column=1, sticky="w", padx=8, pady=1)
            self._slot_cmd_vars.append(var)

        autowrap(tk.Label(frame,
                 text="  Note: Slot 1 is the driver (party leader) by default.\n"
                      "  Any class can be the driver — there is no class restriction.\n"
                      "  Slot order is determined by which client you assign to which slot.",
                 bg=tk_color("card_bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left",
                 padx=10, pady=6,
                 )).pack(fill="x", padx=16, pady=(16, 0))

    # ── Login tab ─────────────────────────────────────────────

    def _build_login_tab(self, nb):
        frame = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(frame, text="Login")

        autowrap(tk.Label(frame,
                 text="Click coordinates for Auto Login — relative to each window's "
                      "top-left corner. Slot 1 (1920×1080) and slots 2-6 (640×540) "
                      "have different login UI positions so each has its own set.",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left",
                 )).pack(fill="x", padx=16, pady=(12, 4))

        # Scrollable canvas so long coord lists don't overflow the window
        canvas = tk.Canvas(frame, bg=tk_color("bg"), highlightthickness=0)
        scroll = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
        inner = tk.Frame(canvas, bg=tk_color("bg"))
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        self._bind_mousewheel(canvas)

        al  = self.settings.get("autologin", {})
        cs  = self.settings.get("char_select", {})
        qtd = self.settings.get("quit_to_desktop", {})

        def section(text):
            tk.Label(inner, text=text,
                     bg=tk_color("bg"), fg=tk_color("accent"),
                     font=THEME["font_small"], anchor="w",
                     ).pack(fill="x", padx=8, pady=(10, 2))

        def divider():
            tk.Frame(inner, bg=tk_color("slot_border"), height=1
                     ).pack(fill="x", padx=8, pady=(8, 4))

        def ms_row(lbl, var):
            row = tk.Frame(inner, bg=tk_color("bg"))
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=lbl, bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"], anchor="w", width=22).pack(side="left")
            tk.Entry(row, textvariable=var, width=6,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     insertbackground=tk_color("text"),
                     font=THEME["font_mono"], relief="flat").pack(side="left", padx=(6, 0))

        autowrap(tk.Label(inner,
                 text="Click Set, then click the target button in your game window. "
                      "One calibration covers all window sizes.",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left", anchor="w",
                 )).pack(fill="x", padx=8, pady=(4, 2))

        # ── Autologin coords ──────────────────────────────────
        # Username and password fields are filled via Tab navigation (Wine
        # windows don't move keyboard focus on click). Only the login button
        # needs a calibrated click coordinate.
        section("Auto-login")
        self._login_lx = tk.StringVar(value=str(al.get("login_x_pct", 0.0)))
        self._login_ly = tk.StringVar(value=str(al.get("login_y_pct", 0.0)))
        self._coord_set_row(inner, "Accept / Login:", self._login_lx, self._login_ly).pack(fill="x", padx=8, pady=2)

        # ── Char-select positions ─────────────────────────────
        divider()
        section("Char Select — character positions (1–5)")
        autowrap(tk.Label(inner,
                 text="Click the character name button for each slot position. "
                      "Accept button reuses the Accept / Login coord above.",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left", anchor="w",
                 )).pack(fill="x", padx=8, pady=(0, 4))

        positions = cs.get("positions", [[0.0, 0.0]] * 5)
        self._cs_pos_vars = []
        for i in range(5):
            xp, yp = (positions[i] if i < len(positions) else [0.0, 0.0])
            xv = tk.StringVar(value=str(xp))
            yv = tk.StringVar(value=str(yp))
            self._cs_pos_vars.append((xv, yv))
            self._coord_set_row(inner, f"  Char position {i+1}:", xv, yv).pack(fill="x", padx=8, pady=1)

        divider()
        section("Char Select — Timing")
        self._cs_settle_var    = tk.StringVar(value=str(cs.get("settle_ms", 6000)))
        self._cs_btn_ready_var = tk.StringVar(value=str(cs.get("button_ready_ms", 1200)))
        self._cs_accept_d_var  = tk.StringVar(value=str(cs.get("accept_delay_ms", 1200)))
        for lbl, var in [("Settle delay (ms):",      self._cs_settle_var),
                         ("Button ready delay (ms):", self._cs_btn_ready_var),
                         ("Accept delay (ms):",       self._cs_accept_d_var)]:
            ms_row(lbl, var)

        # ── Quit to Desktop ───────────────────────────────────
        divider()
        section("Quit to Desktop")
        autowrap(tk.Label(inner,
                 text="In-game: Escape opens menu, then click Quit to Desktop.\n"
                      "Pre-game (login/char-select): click Exit button directly. "
                      "Leave pre-game at (not set) to fall back to Alt+F4.",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left", anchor="w",
                 )).pack(fill="x", padx=8, pady=(0, 4))

        ig  = qtd.get("in_game",  {"x_pct": 0.0, "y_pct": 0.0})
        pg  = qtd.get("pre_game", {"x_pct": 0.0, "y_pct": 0.0})
        self._qtd_ig_x = tk.StringVar(value=str(ig.get("x_pct", 0.0)))
        self._qtd_ig_y = tk.StringVar(value=str(ig.get("y_pct", 0.0)))
        self._qtd_pg_x = tk.StringVar(value=str(pg.get("x_pct", 0.0)))
        self._qtd_pg_y = tk.StringVar(value=str(pg.get("y_pct", 0.0)))
        self._coord_set_row(inner, "In-game:",  self._qtd_ig_x, self._qtd_ig_y).pack(fill="x", padx=8, pady=2)
        self._coord_set_row(inner, "Pre-game:", self._qtd_pg_x, self._qtd_pg_y).pack(fill="x", padx=8, pady=2)

    # ── Monitors tab ──────────────────────────────────────────

    def _build_monitors_tab(self, nb):
        frame = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(frame, text="Monitors")

        autowrap(tk.Label(frame,
                 text="  Detected monitors. If a monitor is missing, click Refresh.\n"
                      "  Indices here match what you enter in the Layout canvas.",
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left",
                 padx=8, pady=6,
                 )).pack(fill="x", padx=10, pady=(8, 4))

        self._mon_list_frame = tk.Frame(frame, bg=tk_color("bg"))
        self._mon_list_frame.pack(fill="x", padx=10, pady=4)
        self._draw_monitor_list()

        tk.Button(frame, text="⟳  Refresh Monitor Detection",
                  command=self._refresh_monitors,
                  bg=tk_color("card_bg"), fg=tk_color("text"),
                  font=THEME["font_main"], relief="flat", padx=10, pady=4
                  ).pack(padx=10, pady=6, anchor="w")

        assign = tk.Frame(frame, bg=tk_color("bg"))
        assign.pack(fill="x", padx=10, pady=4)

        tk.Label(assign, text="Main window monitor index:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=28, anchor="w"
                 ).grid(row=0, column=0, sticky="w", pady=4)
        self._main_mon_var = tk.IntVar(
            value=self.settings["layout"].get("main_monitor", 0))
        tk.Spinbox(assign, from_=0, to=5, textvariable=self._main_mon_var,
                   width=4, bg=tk_color("card_bg"), fg=tk_color("text"),
                   font=THEME["font_mono"], relief="flat"
                   ).grid(row=0, column=1, sticky="w", padx=8)

        tk.Label(assign, text="Secondary windows monitor index:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=28, anchor="w"
                 ).grid(row=1, column=0, sticky="w", pady=4)
        self._sec_mon_var = tk.IntVar(
            value=self.settings["layout"].get("secondary_monitor", 1))
        tk.Spinbox(assign, from_=0, to=5, textvariable=self._sec_mon_var,
                   width=4, bg=tk_color("card_bg"), fg=tk_color("text"),
                   font=THEME["font_mono"], relief="flat"
                   ).grid(row=1, column=1, sticky="w", padx=8)

    def _draw_monitor_list(self):
        for w in self._mon_list_frame.winfo_children():
            w.destroy()
        if not self.monitors:
            tk.Label(self._mon_list_frame,
                     text="No monitors detected — click Refresh",
                     bg=tk_color("bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"]).pack(anchor="w")
            return

        for col, h in enumerate(["Index", "Name", "Resolution", "Position"]):
            tk.Label(self._mon_list_frame, text=h,
                     bg=tk_color("bg"), fg=tk_color("accent"),
                     font=THEME["font_small"], width=12, anchor="w"
                     ).grid(row=0, column=col, padx=4, pady=2)

        for r, mon in enumerate(self.monitors, 1):
            for col, val in enumerate([
                str(mon.get("index", r-1)),
                mon.get("name", "?"),
                f"{mon['w']}×{mon['h']}",
                f"+{mon['x']},+{mon['y']}",
            ]):
                tk.Label(self._mon_list_frame, text=val,
                         bg=tk_color("panel_bg"), fg=tk_color("text"),
                         font=THEME["font_mono"], width=14, anchor="w",
                         padx=4, pady=2
                         ).grid(row=r, column=col, padx=2, pady=1)

    def _refresh_monitors(self):
        from window_manager import get_monitors
        self.monitors = get_monitors()
        self._draw_monitor_list()

    # ── Layout tab ────────────────────────────────────────────

    def _build_layout_tab(self, nb):
        frame = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(frame, text="Layout")

        inner = tk.Frame(frame, bg=tk_color("bg"))
        inner.pack(fill="x", padx=16, pady=12)

        self._gap_var = tk.StringVar(
            value=str(self.settings["layout"].get("gap_px", 4)))
        self._sec_count_var = tk.IntVar(
            value=self.settings["layout"].get("secondary_count", 5))

        tk.Label(inner, text="Window gap (px):",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=28, anchor="w"
                 ).grid(row=0, column=0, sticky="w", pady=5)
        tk.Entry(inner, textvariable=self._gap_var, width=8,
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_mono"], relief="flat"
                 ).grid(row=0, column=1, sticky="w", padx=8)
        tk.Label(inner, text="px gap between tiled windows",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]
                 ).grid(row=1, column=1, sticky="w", padx=8)

        tk.Label(inner, text="Default secondary slot count:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=28, anchor="w"
                 ).grid(row=2, column=0, sticky="w", pady=5)
        tk.Spinbox(inner, from_=0, to=5, textvariable=self._sec_count_var,
                   width=4, bg=tk_color("card_bg"), fg=tk_color("text"),
                   font=THEME["font_mono"], relief="flat"
                   ).grid(row=2, column=1, sticky="w", padx=8)

        # Taskbar height
        self._taskbar_h_var = tk.StringVar(
            value=str(self.settings["layout"].get("taskbar_height", 0)))
        tk.Label(inner, text="Taskbar height (px):",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=28, anchor="w"
                 ).grid(row=3, column=0, sticky="w", pady=5)
        tk.Entry(inner, textvariable=self._taskbar_h_var, width=8,
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_mono"], relief="flat"
                 ).grid(row=3, column=1, sticky="w", padx=8)
        tk.Label(inner, text="Height of your taskbar/panel (0 if auto-hide or none)",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]
                 ).grid(row=4, column=1, sticky="w", padx=8)

        # AR lock
        self._ar_lock_var = tk.BooleanVar(
            value=self.settings["layout"].get("ar_lock", "none") == "4:3")
        tk.Checkbutton(inner, text="Lock windows to 4:3 aspect ratio",
                       variable=self._ar_lock_var,
                       bg=tk_color("bg"), fg=tk_color("text"),
                       selectcolor=tk_color("card_bg"),
                       activebackground=tk_color("bg"),
                       font=THEME["font_small"]
                       ).grid(row=6, column=0, columnspan=2, sticky="w", pady=5)

        # Taskbar monitor
        self._taskbar_m_var = tk.IntVar(
            value=self.settings["layout"].get("taskbar_monitor", 1))
        tk.Label(inner, text="Taskbar on monitor:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=28, anchor="w"
                 ).grid(row=5, column=0, sticky="w", pady=5)
        tk.Spinbox(inner, from_=0, to=5, textvariable=self._taskbar_m_var,
                   width=4, bg=tk_color("card_bg"), fg=tk_color("text"),
                   font=THEME["font_mono"], relief="flat"
                   ).grid(row=5, column=1, sticky="w", padx=8)

        autowrap(tk.Label(frame,
                 text="  Windows are made borderless (no title bar or frame)\n"
                      "  automatically when assigned to a slot.\n"
                      "  This ensures your X/Y click coordinates remain accurate.",
                 bg=tk_color("card_bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left",
                 padx=10, pady=6,
                 )).pack(fill="x", padx=16, pady=(16, 0))

    # ── Invite accept coords tab ──────────────────────────────

    def _build_invite_tab(self, nb):
        outer = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(outer, text="Invite")

        autowrap(tk.Label(outer,
                 text="  Configure where to click to accept the group invite popup.\n"
                      "  Use Track Mouse (Settings footer) to find coordinates.",
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left",
                 padx=8, pady=6,
                 )).pack(fill="x", padx=10, pady=(8, 4))

        accept = self.settings.get("invite_accept", {})
        self._build_invite_per_window_coords(outer, accept)

    def _flush_invite_coords(self):
        accept = self.settings.get("invite_accept", {})
        try:
            if hasattr(self, "_inv_per_window_vars") and self._inv_per_window_vars:
                per = []
                for x_v, y_v in self._inv_per_window_vars:
                    try:
                        per.append({"x_pct": float(x_v.get()), "y_pct": float(y_v.get())})
                    except ValueError:
                        per.append({"x_pct": 0.0, "y_pct": 0.0})
                accept["per_window"] = per
        except Exception:
            pass
        self.settings["invite_accept"] = accept

    def _build_invite_per_window_coords(self, parent, accept):
        from constants import MAX_SLOTS
        self._inv_per_window_vars = []
        inner = tk.Frame(parent, bg=tk_color("bg"))
        inner.pack(fill="x", pady=4)
        autowrap(tk.Label(inner,
                 text="All slots share the same accept button position. "
                      "Calibrate from any game window — the percentage applies to all.",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left"
                 )).pack(fill="x", pady=(0, 6))

        per = accept.get("per_window", [{"x_pct": 0.0, "y_pct": 0.0}] * (MAX_SLOTS - 1))
        first = per[0] if per else {"x_pct": 0.0, "y_pct": 0.0}
        self._inv_x = tk.StringVar(value=str(first.get("x_pct", 0.0)))
        self._inv_y = tk.StringVar(value=str(first.get("y_pct", 0.0)))
        self._coord_set_row(inner, "Accept button:", self._inv_x, self._inv_y).pack(fill="x", pady=1)

        # Keep _inv_per_window_vars pointing at the same vars for all slots (flush uses it)
        for _ in range(MAX_SLOTS - 1):
            self._inv_per_window_vars.append((self._inv_x, self._inv_y))

    # ── Reform tab ────────────────────────────────────────────

    def _build_reform_tab(self, nb):
        outer = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(outer, text="Reform")

        autowrap(tk.Label(outer,
                 text="  Driver clicks the formation button then the formation type.\n"
                      "  After the settle delay, each secondary slot presses the join key.",
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left",
                 padx=8, pady=6,
                 )).pack(fill="x", padx=10, pady=(8, 4))

        cfg   = self.settings.get("reform", {})

        # ── Driver section ────────────────────────────────────
        tk.Label(outer, text="Driver actions",
                 bg=tk_color("bg"), fg=tk_color("accent"),
                 font=THEME["font_small"]).pack(anchor="w", padx=16, pady=(8, 0))

        inner = tk.Frame(outer, bg=tk_color("bg"))
        inner.pack(fill="x", padx=16, pady=4)

        def coord_row(parent, row, label, xvar, yvar):
            tk.Label(parent, text=label,
                     bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"], width=26, anchor="w"
                     ).grid(row=row, column=0, sticky="w", pady=4)
            coord_f = tk.Frame(parent, bg=tk_color("bg"))
            coord_f.grid(row=row, column=1, sticky="w", padx=8)
            tk.Label(coord_f, text="X:", bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"]).pack(side="left")
            tk.Entry(coord_f, textvariable=xvar, width=7,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     font=THEME["font_mono"], relief="flat"
                     ).pack(side="left", padx=(2, 10))
            tk.Label(coord_f, text="Y:", bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"]).pack(side="left")
            tk.Entry(coord_f, textvariable=yvar, width=7,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     font=THEME["font_mono"], relief="flat"
                     ).pack(side="left", padx=(2, 0))

        def ms_row(parent, row, label, var, tip=""):
            tk.Label(parent, text=label,
                     bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"], width=26, anchor="w"
                     ).grid(row=row, column=0, sticky="w", pady=4)
            f = tk.Frame(parent, bg=tk_color("bg"))
            f.grid(row=row, column=1, sticky="w", padx=8)
            tk.Entry(f, textvariable=var, width=7,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     font=THEME["font_mono"], relief="flat"
                     ).pack(side="left")
            tk.Label(f, text=tip, bg=tk_color("bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"]).pack(side="left", padx=6)

        c1 = cfg.get("click_1", {"x_pct": 0.0, "y_pct": 0.0})
        c2 = cfg.get("click_2", {"x_pct": 0.0, "y_pct": 0.0})
        self._ref_c1x = tk.StringVar(value=str(c1.get("x_pct", 0.0)))
        self._ref_c1y = tk.StringVar(value=str(c1.get("y_pct", 0.0)))
        self._ref_c2x = tk.StringVar(value=str(c2.get("x_pct", 0.0)))
        self._ref_c2y = tk.StringVar(value=str(c2.get("y_pct", 0.0)))
        self._ref_click_delay = tk.StringVar(value=str(cfg.get("click_delay_ms", 200)))
        self._ref_settle      = tk.StringVar(value=str(cfg.get("settle_ms", 1000)))
        self._ref_key         = tk.StringVar(value=cfg.get("key", "t"))

        self._coord_set_row(inner, "Formation button (click 1):", self._ref_c1x, self._ref_c1y).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)
        ms_row   (inner, 1, "Delay between clicks (ms):",  self._ref_click_delay, "ms")
        self._coord_set_row(inner, "Formation type (click 2):", self._ref_c2x, self._ref_c2y).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ms_row   (inner, 3, "Settle delay (ms):",          self._ref_settle,
                  "wait before members press join key")

        tk.Label(inner, text="Formation join key:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=26, anchor="w"
                 ).grid(row=4, column=0, sticky="w", pady=4)
        kf = tk.Frame(inner, bg=tk_color("bg"))
        kf.grid(row=4, column=1, sticky="w", padx=8)
        tk.Entry(kf, textvariable=self._ref_key, width=6,
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_mono"], relief="flat"
                 ).pack(side="left")
        tk.Label(kf, text="key each secondary slot presses to join",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]).pack(side="left", padx=6)

        self._ref_key_delay = tk.StringVar(value=str(cfg.get("key_delay_ms", 300)))
        ms_row(inner, 5, "Key delay (ms):", self._ref_key_delay,
               "wait after focusing slot before pressing join key")

    # ── Loops tab ─────────────────────────────────────────────

    def _build_loops_tab(self, nb):
        outer = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(outer, text="Loops")

        autowrap(tk.Label(outer,
                 text="  Settings for Combat / Debuff / Heal loops.\n"
                      "  Loops focus each secondary slot in-place and send its keys.\n"
                      "  Assist coord: click position of the 'target my target' button\n"
                      "  in each slot's UI — targets whatever the driver is targeting.",
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left",
                 padx=8, pady=6,
                 )).pack(fill="x", padx=10, pady=(8, 4))

        loops = self.settings.get("loops", {})

        # Scalar settings
        inner = tk.Frame(outer, bg=tk_color("bg"))
        inner.pack(fill="x", padx=16, pady=4)

        def ms_row(row, label, var, tip=""):
            tk.Label(inner, text=label,
                     bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"], width=26, anchor="w"
                     ).grid(row=row, column=0, sticky="w", pady=3)
            f = tk.Frame(inner, bg=tk_color("bg"))
            f.grid(row=row, column=1, sticky="w", padx=8)
            tk.Entry(f, textvariable=var, width=7,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     font=THEME["font_mono"], relief="flat"
                     ).pack(side="left")
            if tip:
                tk.Label(f, text=tip, bg=tk_color("bg"), fg=tk_color("text_dim"),
                         font=THEME["font_small"]).pack(side="left", padx=6)

        self._loops_key_delay     = tk.StringVar(value=str(loops.get("key_delay_ms",      40)))
        self._loops_key_hold      = tk.StringVar(value=str(loops.get("key_hold_ms",       30)))
        self._loops_mod_delay     = tk.StringVar(value=str(loops.get("modifier_delay_ms", 50)))
        self._loops_fire_key      = tk.StringVar(value=loops.get("fire_key", "f"))

        ms_row(0, "Key press delay (ms):", self._loops_key_delay,
               "delay between each key press within a slot")
        ms_row(1, "Key hold time (ms):", self._loops_key_hold,
               "how long each key is held down before release")
        ms_row(2, "Modifier delay (ms):", self._loops_mod_delay,
               "delay between Alt/modifier down and the main key (e.g. Alt+6)")

        tk.Label(inner, text="Fire key (combat only):",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=26, anchor="w"
                 ).grid(row=3, column=0, sticky="w", pady=3)
        kf = tk.Frame(inner, bg=tk_color("bg"))
        kf.grid(row=3, column=1, sticky="w", padx=8)
        tk.Entry(kf, textvariable=self._loops_fire_key, width=6,
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_mono"], relief="flat").pack(side="left")
        tk.Label(kf, text="pressed after assist click",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]).pack(side="left", padx=6)

        self._loops_activate_settle    = tk.StringVar(value=str(loops.get("activate_settle_ms",    300)))
        self._loops_activate_settle_2x = tk.StringVar(value=str(loops.get("activate_settle_ms_2x", 400)))
        self._loops_activate_settle_3x = tk.StringVar(value=str(loops.get("activate_settle_ms_3x", 500)))

        ms_row(4, "Activation settle (ms):", self._loops_activate_settle,
               "delay after switching window focus, before sending input")
        ms_row(5, "Activation settle 2x raid (ms):", self._loops_activate_settle_2x,
               "same, used when raid mode is 2x")
        ms_row(6, "Activation settle 3x raid (ms):", self._loops_activate_settle_3x,
               "same, used when raid mode is 3x")

        self._loops_interleave_buffs = tk.BooleanVar(value=loops.get("interleave_buffs", False))
        tk.Checkbutton(inner, text="Interleave buff loops",
                        variable=self._loops_interleave_buffs,
                        bg=tk_color("bg"), fg=tk_color("text"),
                        selectcolor=tk_color("card_bg"),
                        activebackground=tk_color("bg"), activeforeground=tk_color("text"),
                        font=THEME["font_small"]
                        ).grid(row=7, column=0, sticky="w", pady=3)
        tk.Label(inner,
                 text="every buffer hits each target before moving to the next\n"
                      "(faster with multiple buffers; off = each buffer finishes all\n"
                      "its targets before the next buffer starts)",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left", anchor="w"
                 ).grid(row=7, column=1, sticky="w", padx=8, pady=3)

        # Assist coords panel
        self._loops_assist_detail = tk.Frame(outer, bg=tk_color("bg"))
        self._loops_assist_detail.pack(fill="both", expand=True, padx=10, pady=4)
        self._refresh_loops_panel()

    def _flush_loops_coords(self):
        loops = self.settings.get("loops", {})
        try:
            if hasattr(self, "_loops_per_window_vars") and self._loops_per_window_vars:
                per = []
                for x_v, y_v in self._loops_per_window_vars:
                    try:
                        per.append({"x_pct": float(x_v.get()), "y_pct": float(y_v.get())})
                    except ValueError:
                        per.append({"x_pct": 0.0, "y_pct": 0.0})
                loops["assist_per_window"] = per
        except Exception:
            pass
        self.settings["loops"] = loops

    def _refresh_loops_panel(self):
        self._flush_loops_coords()
        for w in self._loops_assist_detail.winfo_children():
            w.destroy()
        loops = self.settings.get("loops", {})
        self._build_loops_per_window_coords(self._loops_assist_detail, loops)

    def _build_loops_per_window_coords(self, parent, loops):
        from constants import MAX_SLOTS
        self._loops_per_window_vars = []
        inner = tk.Frame(parent, bg=tk_color("bg"))
        inner.pack(fill="x", pady=4)
        autowrap(tk.Label(inner,
                 text="The 'target my target' button is in the same position on every slot's screen. "
                      "Calibrate from any game window — the percentage applies to all slots.",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left"
                 )).pack(fill="x", pady=(0, 4))

        per = loops.get("assist_per_window", [{"x_pct": 0.0, "y_pct": 0.0}] * MAX_SLOTS)
        first = per[0] if per else {"x_pct": 0.0, "y_pct": 0.0}
        self._assist_x = tk.StringVar(value=str(first.get("x_pct", 0.0)))
        self._assist_y = tk.StringVar(value=str(first.get("y_pct", 0.0)))
        self._coord_set_row(inner, "Target button:", self._assist_x, self._assist_y).pack(fill="x", pady=1)

        # All slots share the same coord
        for _ in range(MAX_SLOTS):
            self._loops_per_window_vars.append((self._assist_x, self._assist_y))

    # ── Indicator tab ─────────────────────────────────────────

    def _build_indicator_tab(self, nb):
        from tkinter import colorchooser
        outer = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(outer, text="Indicator")

        autowrap(tk.Label(outer,
            text="  On-Main Indicator — a small overlay on the main monitor showing which slot is active.",
            bg=tk_color("card_bg"), fg=tk_color("text"),
            font=THEME["font_small"], justify="left", padx=8, pady=6,
        )).pack(fill="x", padx=10, pady=(8, 4))

        cfg = self.settings.get("omit_indicator", {})
        inner = tk.Frame(outer, bg=tk_color("bg"))
        inner.pack(fill="x", padx=16, pady=8)

        def row(r, label_text, widget_factory):
            tk.Label(inner, text=label_text,
                     bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"], width=20, anchor="w",
                     ).grid(row=r, column=0, sticky="w", pady=4)
            w = widget_factory(inner)
            w.grid(row=r, column=1, sticky="w", padx=10)
            return w

        # Enabled
        self._ind_enabled_var = tk.BooleanVar(value=cfg.get("enabled", False))
        row(0, "Show indicator:",
            lambda p: tk.Checkbutton(p, variable=self._ind_enabled_var,
                                     bg=tk_color("bg"), fg=tk_color("text"),
                                     selectcolor=tk_color("card_bg"),
                                     activebackground=tk_color("bg"),
                                     text="Enabled"))

        # Content
        self._ind_content_var = tk.StringVar(value=cfg.get("content", "slot"))
        content_frame = tk.Frame(inner, bg=tk_color("bg"))
        content_frame.grid(row=1, column=1, sticky="w", padx=10)
        tk.Label(inner, text="Content:", bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=20, anchor="w",
                 ).grid(row=1, column=0, sticky="w", pady=4)
        for val, lbl in [("slot", "Slot number"), ("role", "Role (JD)"), ("char_name", "Character name")]:
            tk.Radiobutton(content_frame, text=lbl, variable=self._ind_content_var,
                           value=val, bg=tk_color("bg"), fg=tk_color("text"),
                           selectcolor=tk_color("card_bg"),
                           activebackground=tk_color("bg"),
                           font=THEME["font_small"],
                           ).pack(side="left", padx=(0, 12))

        # Position — freeform x/y with drag-to-place button
        self._ind_x_var = tk.StringVar(value=str(cfg.get("x", 20)))
        self._ind_y_var = tk.StringVar(value=str(cfg.get("y", 280)))

        def _pos_row(parent):
            f = tk.Frame(parent, bg=tk_color("bg"))
            tk.Label(f, text="x:", bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"]).pack(side="left")
            tk.Entry(f, textvariable=self._ind_x_var, width=6,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     font=THEME["font_mono"], relief="flat").pack(side="left", padx=(2, 0))
            tk.Label(f, text="y:", bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"]).pack(side="left", padx=(10, 0))
            tk.Entry(f, textvariable=self._ind_y_var, width=6,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     font=THEME["font_mono"], relief="flat").pack(side="left", padx=(2, 0))
            if self._drag_mode_toggle:
                self._ind_drag_btn = tk.Button(
                    f, text="Move indicator",
                    command=self._toggle_indicator_drag,
                    bg=tk_color("card_bg"), fg=tk_color("text"),
                    font=THEME["font_small"], relief="flat", padx=8,
                )
                self._ind_drag_btn.pack(side="left", padx=(16, 0))
            return f
        row(2, "Position (x / y):", _pos_row)

        # Opacity
        self._ind_opacity_var = tk.IntVar(value=int(cfg.get("opacity", 0.85) * 100))
        def _opacity_row(parent):
            f = tk.Frame(parent, bg=tk_color("bg"))
            s = tk.Scale(f, from_=10, to=100, orient="horizontal",
                         variable=self._ind_opacity_var, length=160,
                         bg=tk_color("bg"), fg=tk_color("text"),
                         troughcolor=tk_color("card_bg"), highlightthickness=0,
                         font=THEME["font_small"])
            s.pack(side="left")
            tk.Label(f, text="%", bg=tk_color("bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"]).pack(side="left", padx=2)
            return f
        row(3, "Opacity:", _opacity_row)

        # Text color
        self._ind_text_color_var = tk.StringVar(value=cfg.get("text_color", "#ffffff"))
        def _color_row(var, r, label):
            tk.Label(inner, text=label, bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"], width=20, anchor="w",
                     ).grid(row=r, column=0, sticky="w", pady=4)
            f = tk.Frame(inner, bg=tk_color("bg"))
            f.grid(row=r, column=1, sticky="w", padx=10)
            entry = tk.Entry(f, textvariable=var, width=10,
                             bg=tk_color("card_bg"), fg=tk_color("text"),
                             font=THEME["font_mono"], relief="flat")
            entry.pack(side="left")
            swatch = tk.Label(f, text="  ", bg=var.get(), relief="solid", bd=1)
            swatch.pack(side="left", padx=4)
            def _pick(v=var, sw=swatch):
                result = colorchooser.askcolor(color=v.get(), parent=self.win)
                if result and result[1]:
                    v.set(result[1])
                    sw.config(bg=result[1])
            entry.bind("<FocusOut>", lambda e, v=var, sw=swatch: sw.config(bg=v.get()))
            tk.Button(f, text="Pick", command=_pick,
                      bg=tk_color("card_bg"), fg=tk_color("text"),
                      font=THEME["font_small"], relief="flat", padx=6,
                      ).pack(side="left")

        _color_row(self._ind_text_color_var, 4, "Text color:")

        # Font size
        self._ind_font_size_var = tk.StringVar(value=str(cfg.get("font_size", 48)))
        def _font_row(parent):
            f = tk.Frame(parent, bg=tk_color("bg"))
            tk.Entry(f, textvariable=self._ind_font_size_var, width=6,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     font=THEME["font_mono"], relief="flat").pack(side="left")
            tk.Label(f, text="pt", bg=tk_color("bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"]).pack(side="left", padx=4)
            return f
        row(5, "Font size:", _font_row)

    def _toggle_indicator_drag(self):
        if not self._drag_mode_toggle:
            return
        active = self._drag_mode_toggle()
        btn = getattr(self, '_ind_drag_btn', None)
        if btn:
            btn.config(text="Stop moving" if active else "Move indicator")

    # ── Roles tab ─────────────────────────────────────────────

    def _build_roles_tab(self, nb):
        outer = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(outer, text="Roles")

        autowrap(tk.Label(outer,
                 text="  Role profiles define which keys each slot presses per loop type.\n"
                      "  Assign a profile to each slot via right-click → Role Profile.",
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left",
                 padx=8, pady=6,
                 )).pack(fill="x", padx=10, pady=(8, 4))

        ctrl = tk.Frame(outer, bg=tk_color("bg"))
        ctrl.pack(fill="x", padx=10, pady=4)

        from config_manager import list_role_profiles
        self._role_profiles_list = list_role_profiles()

        self._roles_listbox = tk.Listbox(
            outer, bg=tk_color("card_bg"), fg=tk_color("text"),
            font=THEME["font_main"], selectbackground=tk_color("accent"),
            activestyle="none", height=6,
        )
        self._roles_listbox.pack(fill="x", padx=10, pady=4)
        for p in self._role_profiles_list:
            self._roles_listbox.insert("end", p)

        btn_row = tk.Frame(outer, bg=tk_color("bg"))
        btn_row.pack(fill="x", padx=10, pady=2)
        for text, cmd in [("New",    self._new_role_profile),
                           ("Edit",   self._edit_role_profile),
                           ("Delete", self._delete_role_profile)]:
            tk.Button(btn_row, text=text, command=cmd,
                      bg=tk_color("card_bg"), fg=tk_color("text"),
                      font=THEME["font_small"], relief="flat", padx=10, pady=3
                      ).pack(side="left", padx=4)

    def _refresh_roles_list(self):
        from config_manager import list_role_profiles
        self._role_profiles_list = list_role_profiles()
        self._roles_listbox.delete(0, "end")
        for p in self._role_profiles_list:
            self._roles_listbox.insert("end", p)

    def _new_role_profile(self):
        from tkinter import simpledialog
        from config_manager import default_role_profile, save_role_profile
        name = simpledialog.askstring("New Role Profile", "Profile name:",
                                      parent=self.win)
        if not name:
            return
        save_role_profile(default_role_profile(name))
        self._refresh_roles_list()
        self._open_role_profile_editor(name)

    def _edit_role_profile(self):
        sel = self._roles_listbox.curselection()
        if not sel:
            return
        name = self._role_profiles_list[sel[0]]
        self._open_role_profile_editor(name)

    def _delete_role_profile(self):
        from tkinter import messagebox
        from config_manager import delete_role_profile
        sel = self._roles_listbox.curselection()
        if not sel:
            return
        name = self._role_profiles_list[sel[0]]
        if messagebox.askyesno("Delete Profile",
                               f"Delete role profile '{name}'?", parent=self.win):
            delete_role_profile(name)
            self._refresh_roles_list()

    def _open_role_profile_editor(self, name: str):
        from config_manager import load_role_profile, save_role_profile
        from constants import LOOP_KEY_OPTIONS, LOOP_TYPES, CLASS_ABBREVS

        profile = load_role_profile(name)

        dlg = tk.Toplevel(self.win)
        dlg.title(f"Role Profile: {name}")
        dlg.configure(bg=tk_color("bg"))
        dlg.geometry("720x580")
        dlg.grab_set()
        dlg.resizable(True, True)
        _center_on_parent(dlg, self.win)

        # Header fields
        hdr = tk.Frame(dlg, bg=tk_color("bg"))
        hdr.pack(fill="x", padx=12, pady=(10, 4))

        for col, (lbl, key, w) in enumerate([
            ("Name:",        "name",        14),
            ("Description:", "description", 24),
        ]):
            tk.Label(hdr, text=lbl, bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"]).grid(row=0, column=col*2, padx=(8,2))
            var = tk.StringVar(value=profile.get(key, ""))
            tk.Entry(hdr, textvariable=var, width=w,
                     bg=tk_color("card_bg"), fg=tk_color("text"),
                     insertbackground=tk_color("text"),
                     font=THEME["font_mono"], relief="flat"
                     ).grid(row=0, column=col*2+1, padx=(0, 8))
            if key == "name":
                name_var = var
            else:
                desc_var = var

        tk.Label(hdr, text="Class:", bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"]).grid(row=0, column=4, padx=(8,2))
        class_var = tk.StringVar(value=profile.get("class", ""))
        ttk.Combobox(hdr, textvariable=class_var,
                     values=[""] + CLASS_ABBREVS,
                     width=5, state="readonly", font=THEME["font_small"]
                     ).grid(row=0, column=5, padx=(0, 8))

        tk.Frame(dlg, bg=tk_color("slot_border"), height=1).pack(fill="x", padx=12)

        # Loop type tabs
        nb = ttk.Notebook(dlg)
        nb.pack(fill="both", expand=True, padx=12, pady=8)

        key_vars = {}  # loop_type -> list of StringVar
        heal_target_var  = tk.StringVar(value=profile.get("heal_target_key", ""))
        buff_device_vars = []  # filled when buff tab is built

        FKEY_OPTIONS = ["", "f1", "f2", "f3", "f4", "f5", "f6"]

        for loop_type, loop_label in LOOP_TYPES:
            tab = tk.Frame(nb, bg=tk_color("bg"))
            nb.add(tab, text=loop_label)

            if loop_type == "buff":
                # Buff tab can grow arbitrarily with "+ Add Device" — make it scrollable.
                buff_canvas = tk.Canvas(tab, bg=tk_color("bg"), highlightthickness=0)
                buff_scroll = tk.Scrollbar(tab, orient="vertical", command=buff_canvas.yview)
                buff_canvas.configure(yscrollcommand=buff_scroll.set)
                buff_scroll.pack(side="right", fill="y")
                buff_canvas.pack(side="left", fill="both", expand=True)
                content = tk.Frame(buff_canvas, bg=tk_color("bg"))
                buff_cw = buff_canvas.create_window((0, 0), window=content, anchor="nw")
                buff_canvas.bind("<Configure>",
                    lambda e, c=buff_canvas, w=buff_cw: c.itemconfig(w, width=e.width))
                content.bind("<Configure>",
                    lambda e, c=buff_canvas: c.configure(scrollregion=c.bbox("all")))

                def _buff_wheel(event, c=buff_canvas):
                    if event.num == 4:
                        c.yview_scroll(-1, "units")
                    elif event.num == 5:
                        c.yview_scroll(1, "units")
                def _buff_wheel_mw(event, c=buff_canvas):
                    c.yview_scroll(-1 if event.delta > 0 else 1, "units")
                def _buff_wheel_enter(_, c=buff_canvas):
                    dlg.bind("<Button-4>", _buff_wheel)
                    dlg.bind("<Button-5>", _buff_wheel)
                    dlg.bind("<MouseWheel>", _buff_wheel_mw)
                def _buff_wheel_leave(_):
                    dlg.unbind("<Button-4>")
                    dlg.unbind("<Button-5>")
                    dlg.unbind("<MouseWheel>")
                buff_canvas.bind("<Enter>", _buff_wheel_enter)
                buff_canvas.bind("<Leave>", _buff_wheel_leave)
            else:
                content = tab

            # Heal tab gets an extra "target driver" field
            if loop_type == "heal":
                hrow = tk.Frame(content, bg=tk_color("bg"))
                hrow.pack(anchor="w", padx=8, pady=(8, 0))
                tk.Label(hrow, text="Target driver key (TT only):",
                         bg=tk_color("bg"), fg=tk_color("text"),
                         font=THEME["font_small"]
                         ).pack(side="left")
                ttk.Combobox(hrow, textvariable=heal_target_var,
                             values=FKEY_OPTIONS, width=5,
                             state="readonly", font=THEME["font_small"]
                             ).pack(side="left", padx=6)
                autowrap(tk.Label(hrow,
                         text="F-key to select driver before hull patch. Leave blank for TE (repair needs no target).",
                         bg=tk_color("bg"), fg=tk_color("text_dim"),
                         font=THEME["font_small"], justify="left"
                         )).pack(side="left", padx=4, fill="x", expand=True)

            autowrap(tk.Label(content,
                     text=f"Select which key to press at each step of the {loop_label} loop.\n"
                          "The number above each dropdown is the press order (1 = first, 2 = second…).\n"
                          "Leave a step blank to skip it.",
                     bg=tk_color("bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"], justify="left"
                     )).pack(fill="x", padx=8, pady=(6, 2))

            existing = profile.get(f"{loop_type}_keys", [])
            padded = (existing + [""] * 12)[:12]

            vars_for_type = []
            grid_f = tk.Frame(content, bg=tk_color("bg"))
            grid_f.pack(padx=8, pady=4, anchor="w")

            for row, (row_labels, offset) in enumerate([
                (["Step 1","Step 2","Step 3","Step 4","Step 5","Step 6"], 0),
                (["Step 7","Step 8","Step 9","Step 10","Step 11","Step 12"], 6),
            ]):
                for col, lbl in enumerate(row_labels):
                    idx = offset + col
                    tk.Label(grid_f, text=lbl,
                             bg=tk_color("bg"), fg=tk_color("text_dim"),
                             font=THEME["font_small"], anchor="center"
                             ).grid(row=row*2, column=col, padx=2, sticky="ew")
                    v = tk.StringVar(value=padded[idx])
                    ttk.Combobox(grid_f, textvariable=v,
                                 values=LOOP_KEY_OPTIONS,
                                 width=5, font=THEME["font_small"]
                                 ).grid(row=row*2+1, column=col, padx=2, pady=2)
                    vars_for_type.append(v)

            key_vars[loop_type] = vars_for_type

            # Energy tab — Power Vortex EM9 section below the key grid
            if loop_type == "energy":
                tk.Frame(content, bg=tk_color("slot_border"), height=1
                         ).pack(fill="x", padx=8, pady=(10, 0))

                pv9_enabled_var = tk.BooleanVar(value=profile.get("pv9_enabled", False))
                pv9_key_var     = tk.StringVar(value=profile.get("pv9_key", ""))
                existing_pv9    = profile.get("pv9_targets", [])
                existing_pv9    = (existing_pv9 + [""] * 6)[:6]
                pv9_target_vars = [tk.StringVar(value=v) for v in existing_pv9]

                pv9_hdr = tk.Frame(content, bg=tk_color("bg"))
                pv9_hdr.pack(fill="x", padx=8, pady=(6, 0))
                tk.Checkbutton(pv9_hdr, text="Uses Power Vortex EM9",
                               variable=pv9_enabled_var,
                               bg=tk_color("bg"), fg=tk_color("text"),
                               selectcolor=tk_color("card_bg"),
                               activebackground=tk_color("bg"),
                               font=THEME["font_small"]
                               ).pack(side="left")
                autowrap(tk.Label(pv9_hdr,
                         text="one pass: target F-key → activate → re-assist → fire",
                         bg=tk_color("bg"), fg=tk_color("text_dim"),
                         font=THEME["font_small"], justify="left"
                         )).pack(side="left", padx=8, fill="x", expand=True)

                pv9_body = tk.Frame(content, bg=tk_color("bg"))
                pv9_body.pack(anchor="w", padx=8, pady=4)

                tk.Label(pv9_body, text="Reactor key:",
                         bg=tk_color("bg"), fg=tk_color("text"),
                         font=THEME["font_small"], width=18, anchor="w"
                         ).grid(row=0, column=0, sticky="w", pady=3)
                ttk.Combobox(pv9_body, textvariable=pv9_key_var,
                             values=LOOP_KEY_OPTIONS, width=6,
                             font=THEME["font_small"]
                             ).grid(row=0, column=1, sticky="w", padx=4)

                tk.Label(pv9_body, text="Buff order (F-keys):",
                         bg=tk_color("bg"), fg=tk_color("text"),
                         font=THEME["font_small"], width=18, anchor="w"
                         ).grid(row=1, column=0, sticky="nw", pady=(6, 2))
                pv9_targets_frame = tk.Frame(pv9_body, bg=tk_color("bg"))
                pv9_targets_frame.grid(row=1, column=1, columnspan=2,
                                       sticky="w", pady=(6, 2))
                for i, v in enumerate(pv9_target_vars):
                    lf = tk.Frame(pv9_targets_frame, bg=tk_color("bg"))
                    lf.pack(side="left", padx=(0, 6))
                    tk.Label(lf, text=f"{i+1}:",
                             bg=tk_color("bg"), fg=tk_color("text_dim"),
                             font=THEME["font_small"]).pack()
                    ttk.Combobox(lf, textvariable=v, values=FKEY_OPTIONS,
                                 width=4, state="readonly",
                                 font=THEME["font_small"]).pack()

                tk.Label(pv9_body,
                         text="F1=self  F2=driver  F3-F6=other party members",
                         bg=tk_color("bg"), fg=tk_color("text_dim"),
                         font=THEME["font_small"]
                         ).grid(row=2, column=1, columnspan=2, sticky="w", pady=(2, 0))

            # Buff tab — targeted devices section below the simple key grid
            if loop_type == "buff":
                tk.Frame(content, bg=tk_color("slot_border"), height=1
                         ).pack(fill="x", padx=8, pady=(10, 0))

                autowrap(tk.Label(content,
                         text="Targeted Devices — for each device: target F-key → press device key → re-assist → fire.\n"
                              "Leave targets blank to cast without targeting.",
                         bg=tk_color("bg"), fg=tk_color("text_dim"),
                         font=THEME["font_small"], justify="left"
                         )).pack(fill="x", padx=8, pady=(6, 2))

                devices_container = tk.Frame(content, bg=tk_color("bg"))
                devices_container.pack(fill="x")

                def _renumber_devices():
                    for i, entry in enumerate(buff_device_vars):
                        entry["label_widget"].config(text=f"Device {i+1}:")

                def _add_device_row(dev=None):
                    dev = dev or {}
                    dev_key_var       = tk.StringVar(value=dev.get("key", ""))
                    dev_reassist_var  = tk.BooleanVar(value=dev.get("reassist", True))
                    dev_casttime_var  = tk.StringVar(value=str(dev.get("cast_time_s", 0.0)))
                    raw_targets       = dev.get("targets", [])
                    raw_targets       = (raw_targets + [""] * 6)[:6]
                    dev_target_vars   = [tk.StringVar(value=t) for t in raw_targets]

                    dev_frame = tk.Frame(devices_container, bg=tk_color("card_bg"),
                                        relief="flat", bd=0,
                                        highlightthickness=1,
                                        highlightbackground=tk_color("slot_border"))
                    dev_frame.pack(fill="x", padx=8, pady=(4, 0))

                    hdr_row = tk.Frame(dev_frame, bg=tk_color("card_bg"))
                    hdr_row.pack(fill="x", padx=6, pady=(4, 2))
                    label_widget = tk.Label(hdr_row, text="Device:",
                             bg=tk_color("card_bg"), fg=tk_color("text"),
                             font=THEME["font_small"], width=9, anchor="w")
                    label_widget.pack(side="left")
                    ttk.Combobox(hdr_row, textvariable=dev_key_var,
                                 values=LOOP_KEY_OPTIONS, width=7,
                                 font=THEME["font_small"]
                                 ).pack(side="left", padx=(0, 8))
                    tk.Label(hdr_row, text="Cast time (s):",
                             bg=tk_color("card_bg"), fg=tk_color("text"),
                             font=THEME["font_small"]
                             ).pack(side="left")
                    tk.Entry(hdr_row, textvariable=dev_casttime_var, width=5,
                             bg=tk_color("bg"), fg=tk_color("text"),
                             insertbackground=tk_color("text"),
                             font=THEME["font_mono"], relief="flat"
                             ).pack(side="left", padx=(2, 8))
                    tk.Label(hdr_row, text="(0=instant)",
                             bg=tk_color("card_bg"), fg=tk_color("text_dim"),
                             font=THEME["font_small"]
                             ).pack(side="left", padx=(0, 4))

                    def _remove_this():
                        dev_frame.destroy()
                        buff_device_vars.remove(entry)
                        _renumber_devices()

                    tk.Button(hdr_row, text="✕ Remove", command=_remove_this,
                              bg=tk_color("card_bg"), fg=tk_color("text_dim"),
                              font=THEME["font_small"], relief="flat",
                              activebackground=tk_color("slot_border")
                              ).pack(side="right", padx=(0, 4))

                    tgt_row = tk.Frame(dev_frame, bg=tk_color("card_bg"))
                    tgt_row.pack(anchor="w", padx=6, pady=(0, 2))
                    tk.Label(tgt_row, text="Targets:",
                             bg=tk_color("card_bg"), fg=tk_color("text_dim"),
                             font=THEME["font_small"]
                             ).pack(side="left", padx=(0, 6))
                    for ti, tv in enumerate(dev_target_vars):
                        lf = tk.Frame(tgt_row, bg=tk_color("card_bg"))
                        lf.pack(side="left", padx=(0, 4))
                        tk.Label(lf, text=f"{ti+1}:",
                                 bg=tk_color("card_bg"), fg=tk_color("text_dim"),
                                 font=THEME["font_small"]).pack()
                        ttk.Combobox(lf, textvariable=tv, values=FKEY_OPTIONS,
                                     width=4, state="readonly",
                                     font=THEME["font_small"]).pack()

                    reassist_row = tk.Frame(dev_frame, bg=tk_color("card_bg"))
                    reassist_row.pack(anchor="w", padx=6, pady=(0, 6))
                    tk.Checkbutton(reassist_row,
                                   text="Re-assist + fire after each target",
                                   variable=dev_reassist_var,
                                   bg=tk_color("card_bg"), fg=tk_color("text"),
                                   selectcolor=tk_color("bg"),
                                   activebackground=tk_color("card_bg"),
                                   font=THEME["font_small"]
                                   ).pack(side="left")

                    entry = {
                        "key_var":       dev_key_var,
                        "target_vars":   dev_target_vars,
                        "reassist_var":  dev_reassist_var,
                        "casttime_var":  dev_casttime_var,
                        "label_widget":  label_widget,
                    }
                    buff_device_vars.append(entry)
                    _renumber_devices()

                existing_devs = profile.get("buff_devices", []) or [{}]
                for dev in existing_devs:
                    _add_device_row(dev)

                add_row = tk.Frame(content, bg=tk_color("bg"))
                add_row.pack(fill="x", padx=8, pady=(4, 10))
                tk.Button(add_row, text="+ Add Device", command=_add_device_row,
                          bg=tk_color("card_bg"), fg=tk_color("text"),
                          font=THEME["font_small"], relief="flat",
                          activebackground=tk_color("slot_border")
                          ).pack(side="left")

        # ── Daimyo tab (PS only) ──────────────────────────────
        daimyo_tab = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(daimyo_tab, text="Daimyo")

        autowrap(tk.Label(daimyo_tab,
                 text="PS Daimyo buff loop. Cycles through targets in order,\n"
                      "activates the device, then re-assists and fires.\n"
                      "F1 = self (no target key sent). Leave targets blank to self-buff only.",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left"
                 )).pack(fill="x", padx=8, pady=(8, 4))

        daimyo_inner = tk.Frame(daimyo_tab, bg=tk_color("bg"))
        daimyo_inner.pack(anchor="w", padx=8, pady=4)

        daimyo_key_var      = tk.StringVar(value=profile.get("daimyo_key", ""))
        daimyo_interval_var = tk.StringVar(value=str(profile.get("daimyo_interval_s", 30.0)))

        tk.Label(daimyo_inner, text="Device key:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(daimyo_inner, textvariable=daimyo_key_var,
                     values=LOOP_KEY_OPTIONS, width=6,
                     font=THEME["font_small"]
                     ).grid(row=0, column=1, sticky="w", padx=4)

        tk.Label(daimyo_inner, text="Interval (seconds):",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=1, column=0, sticky="w", pady=3)
        tk.Entry(daimyo_inner, textvariable=daimyo_interval_var, width=7,
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_mono"], relief="flat"
                 ).grid(row=1, column=1, sticky="w", padx=4)
        tk.Label(daimyo_inner,
                 text="wait after each target before moving to next",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]
                 ).grid(row=1, column=2, sticky="w", padx=6)

        tk.Label(daimyo_inner, text="Buff order (F-keys):",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=2, column=0, sticky="nw", pady=(6, 2))

        targets_frame = tk.Frame(daimyo_inner, bg=tk_color("bg"))
        targets_frame.grid(row=2, column=1, columnspan=2, sticky="w", pady=(6, 2))

        existing_targets = profile.get("daimyo_targets", [])
        existing_targets = (existing_targets + [""] * 6)[:6]
        daimyo_target_vars = []
        for i, val in enumerate(existing_targets):
            lf = tk.Frame(targets_frame, bg=tk_color("bg"))
            lf.pack(side="left", padx=(0, 6))
            tk.Label(lf, text=f"{i+1}:", bg=tk_color("bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"]).pack()
            v = tk.StringVar(value=val)
            ttk.Combobox(lf, textvariable=v, values=FKEY_OPTIONS,
                         width=4, state="readonly", font=THEME["font_small"]
                         ).pack()
            daimyo_target_vars.append(v)

        tk.Label(daimyo_inner,
                 text="F1=self  F2=driver  F3-F6=other party members",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]
                 ).grid(row=3, column=1, columnspan=2, sticky="w", pady=(2, 0))

        # ── Focus of the Warder ───────────────────────────────
        tk.Frame(daimyo_tab, bg=tk_color("slot_border"), height=1
                 ).pack(fill="x", padx=8, pady=(10, 0))

        fotw_enabled_var  = tk.BooleanVar(value=profile.get("fotw_enabled", False))
        fotw_key_var      = tk.StringVar(value=profile.get("fotw_key", ""))
        fotw_interval_var = tk.StringVar(value=str(profile.get("fotw_interval_s", 6.0)))
        existing_fotw     = profile.get("fotw_targets", [])
        existing_fotw     = (existing_fotw + [""] * 6)[:6]
        fotw_target_vars  = [tk.StringVar(value=v) for v in existing_fotw]

        fotw_hdr = tk.Frame(daimyo_tab, bg=tk_color("bg"))
        fotw_hdr.pack(fill="x", padx=8, pady=(6, 0))
        tk.Checkbutton(fotw_hdr, text="Use Focus of the Warder instead of Daimyo",
                       variable=fotw_enabled_var,
                       bg=tk_color("bg"), fg=tk_color("text"),
                       selectcolor=tk_color("card_bg"),
                       activebackground=tk_color("bg"),
                       font=THEME["font_small"]
                       ).pack(side="left")
        autowrap(tk.Label(fotw_hdr,
                 text="6s cooldown, 210s buff — overrides Daimyo key/targets when checked",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left"
                 )).pack(side="left", padx=8, fill="x", expand=True)

        fotw_body = tk.Frame(daimyo_tab, bg=tk_color("bg"))
        fotw_body.pack(anchor="w", padx=8, pady=4)

        tk.Label(fotw_body, text="Device key:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(fotw_body, textvariable=fotw_key_var,
                     values=LOOP_KEY_OPTIONS, width=6,
                     font=THEME["font_small"]
                     ).grid(row=0, column=1, sticky="w", padx=4)

        tk.Label(fotw_body, text="Cooldown (seconds):",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=1, column=0, sticky="w", pady=3)
        tk.Entry(fotw_body, textvariable=fotw_interval_var, width=7,
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_mono"], relief="flat"
                 ).grid(row=1, column=1, sticky="w", padx=4)
        tk.Label(fotw_body, text="default 6s",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]
                 ).grid(row=1, column=2, sticky="w", padx=6)

        tk.Label(fotw_body, text="Buff order (F-keys):",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=2, column=0, sticky="nw", pady=(6, 2))
        fotw_targets_frame = tk.Frame(fotw_body, bg=tk_color("bg"))
        fotw_targets_frame.grid(row=2, column=1, columnspan=2, sticky="w", pady=(6, 2))
        for i, v in enumerate(fotw_target_vars):
            lf = tk.Frame(fotw_targets_frame, bg=tk_color("bg"))
            lf.pack(side="left", padx=(0, 6))
            tk.Label(lf, text=f"{i+1}:", bg=tk_color("bg"), fg=tk_color("text_dim"),
                     font=THEME["font_small"]).pack()
            ttk.Combobox(lf, textvariable=v, values=FKEY_OPTIONS,
                         width=4, state="readonly",
                         font=THEME["font_small"]).pack()
        tk.Label(fotw_body,
                 text="F1=self  F2=driver  F3-F6=other party members",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]
                 ).grid(row=3, column=1, columnspan=2, sticky="w", pady=(2, 0))

        # Save button
        def _safe_float(val, default):
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        def save_profile():
            new_name = name_var.get().strip() or name
            profile["name"]        = new_name
            profile["description"] = desc_var.get().strip()
            profile["class"]       = class_var.get()
            for loop_type, _ in LOOP_TYPES:
                profile[f"{loop_type}_keys"] = [
                    v.get() for v in key_vars[loop_type] if v.get()
                ]
            profile["heal_target_key"] = heal_target_var.get()
            profile["buff_devices"] = [
                {
                    "key":          d["key_var"].get(),
                    "targets":      [v.get() for v in d["target_vars"] if v.get()],
                    "reassist":     d["reassist_var"].get(),
                    "cast_time_s":  _safe_float(d["casttime_var"].get(), 0.0),
                }
                for d in buff_device_vars
                if d["key_var"].get()
            ]
            profile["pv9_enabled"]  = pv9_enabled_var.get()
            profile["pv9_key"]      = pv9_key_var.get()
            profile["pv9_targets"]  = [v.get() for v in pv9_target_vars if v.get()]
            profile["daimyo_key"]        = daimyo_key_var.get()
            try:
                profile["daimyo_interval_s"] = float(daimyo_interval_var.get())
            except ValueError:
                profile["daimyo_interval_s"] = 30.0
            profile["daimyo_targets"] = [v.get() for v in daimyo_target_vars if v.get()]
            profile["fotw_enabled"] = fotw_enabled_var.get()
            profile["fotw_key"]     = fotw_key_var.get()
            try:
                profile["fotw_interval_s"] = float(fotw_interval_var.get())
            except ValueError:
                profile["fotw_interval_s"] = 6.0
            profile["fotw_targets"] = [v.get() for v in fotw_target_vars if v.get()]
            if new_name != name:
                from config_manager import delete_role_profile
                delete_role_profile(name)
            save_role_profile(profile)
            self._refresh_roles_list()
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", save_profile)
        tk.Button(dlg, text="Save Profile", command=save_profile,
                  bg=tk_color("success"), fg="white",
                  font=THEME["font_main"], relief="flat", padx=14, pady=5
                  ).pack(pady=(0, 10))

    # ── Characters tab ────────────────────────────────────────

    def _build_characters_tab(self, nb):
        outer = tk.Frame(nb, bg=tk_color("bg"))
        nb.add(outer, text="Characters")

        autowrap(tk.Label(outer,
                 text="  One profile per in-game character. Each holds the account, "
                      "password, class, role profile (loops/keys), and the click "
                      "coordinate of the character's button on the character "
                      "select screen. Slots reference characters by name.",
                 bg=tk_color("card_bg"), fg=tk_color("text"),
                 font=THEME["font_small"], justify="left",
                 padx=8, pady=6,
                 )).pack(fill="x", padx=10, pady=(8, 4))

        from config_manager import list_characters
        self._characters_list = list_characters()

        self._characters_listbox = tk.Listbox(
            outer, bg=tk_color("card_bg"), fg=tk_color("text"),
            font=THEME["font_main"], selectbackground=tk_color("accent"),
            activestyle="none", height=10,
        )
        self._characters_listbox.pack(fill="both", expand=True, padx=10, pady=4)
        self._refresh_characters_list()
        self._characters_listbox.bind(
            "<Double-Button-1>", lambda _: self._edit_character())

        btn_row = tk.Frame(outer, bg=tk_color("bg"))
        btn_row.pack(fill="x", padx=10, pady=(2, 8))
        for text, cmd in [("New",    self._new_character),
                          ("Edit",   self._edit_character),
                          ("Delete", self._delete_character)]:
            tk.Button(btn_row, text=text, command=cmd,
                      bg=tk_color("card_bg"), fg=tk_color("text"),
                      font=THEME["font_small"], relief="flat", padx=10, pady=3
                      ).pack(side="left", padx=4)

    def _refresh_characters_list(self):
        from config_manager import list_characters, load_character
        self._characters_list = list_characters()
        self._characters_listbox.delete(0, "end")
        for name in self._characters_list:
            c   = load_character(name)
            acc = c.get("account", "")
            cls = c.get("char_class", "")
            tag = f"  [{cls}]" if cls else ""
            sub = f"   ({acc})" if acc else ""
            self._characters_listbox.insert("end", f"{name}{tag}{sub}")

    def _new_character(self):
        from tkinter import simpledialog
        from config_manager import default_character, save_character
        name = simpledialog.askstring("New Character",
                                      "In-game character name:",
                                      parent=self.win)
        if not name:
            return
        save_character(default_character(name))
        self._refresh_characters_list()
        self._open_character_editor(name)

    def _edit_character(self):
        sel = self._characters_listbox.curselection()
        if not sel:
            return
        name = self._characters_list[sel[0]]
        self._open_character_editor(name)

    def _delete_character(self):
        from config_manager import delete_character
        sel = self._characters_listbox.curselection()
        if not sel:
            return
        name = self._characters_list[sel[0]]
        if messagebox.askyesno("Delete Character",
                               f"Delete character '{name}'?", parent=self.win):
            delete_character(name)
            self._refresh_characters_list()

    def _open_character_editor(self, name: str):
        from config_manager import (
            load_character, save_character, delete_character,
            list_role_profiles,
        )

        profile = load_character(name)
        dlg = tk.Toplevel(self.win)
        dlg.title(f"Character: {name}")
        dlg.configure(bg=tk_color("bg"))
        dlg.geometry("480x460")
        dlg.grab_set()
        _center_on_parent(dlg, self.win)

        frm = tk.Frame(dlg, bg=tk_color("bg"))
        frm.pack(fill="both", expand=True, padx=14, pady=10)
        frm.columnconfigure(0, weight=0)
        frm.columnconfigure(1, weight=1)

        def labeled(row, label, w=24, show=None):
            tk.Label(frm, text=label,
                     bg=tk_color("bg"), fg=tk_color("text"),
                     font=THEME["font_small"], width=18, anchor="w"
                     ).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            kwargs = {"show": show} if show else {}
            ent = tk.Entry(frm, textvariable=var, width=w,
                           bg=tk_color("card_bg"), fg=tk_color("text"),
                           insertbackground=tk_color("text"),
                           font=THEME["font_mono"], relief="flat", **kwargs)
            ent.grid(row=row, column=1, sticky="ew", padx=6)
            return var

        name_var     = labeled(0, "Character name:")
        acct_var     = labeled(1, "Account (username):")
        pass_var     = labeled(2, "Password:", show="*")
        notes_var    = labeled(6, "Notes:")
        name_var.set(profile.get("name", name))
        acct_var.set(profile.get("account", ""))
        pass_var.set(profile.get("password", ""))
        notes_var.set(profile.get("notes", ""))

        # Class
        tk.Label(frm, text="Class:", bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=3, column=0, sticky="w", pady=4)
        class_var = tk.StringVar(value=profile.get("char_class", ""))
        ttk.Combobox(frm, textvariable=class_var,
                     values=[""] + CLASS_ABBREVS,
                     width=6, state="readonly", font=THEME["font_small"]
                     ).grid(row=3, column=1, sticky="w", padx=6)

        # Role profile
        tk.Label(frm, text="Role profile:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=4, column=0, sticky="w", pady=4)
        rp_var = tk.StringVar(value=profile.get("role_profile", ""))
        rp_values = [""] + list_role_profiles()
        ttk.Combobox(frm, textvariable=rp_var,
                     values=rp_values, width=22,
                     state="readonly", font=THEME["font_small"]
                     ).grid(row=4, column=1, sticky="w", padx=6)

        # Char-select position (1-5) — which slot in the game's character list
        tk.Label(frm, text="Char-select position:",
                 bg=tk_color("bg"), fg=tk_color("text"),
                 font=THEME["font_small"], width=18, anchor="w"
                 ).grid(row=5, column=0, sticky="w", pady=4)
        cs_pos_var = tk.StringVar(value=str(profile.get("char_select_pos", "")))
        ttk.Combobox(frm, textvariable=cs_pos_var,
                     values=["", "1", "2", "3", "4", "5"],
                     width=4, state="readonly", font=THEME["font_small"]
                     ).grid(row=5, column=1, sticky="w", padx=6)
        autowrap(tk.Label(frm,
                 text="Position of this character in the game's character-select list "
                      "(1 = top). X/Y coords are configured per monitor size in "
                      "Settings → Login.",
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], justify="left"
                 )).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 4))


        def save_and_close():
            new_name = name_var.get().strip() or name
            try:
                cs_pos = int(cs_pos_var.get())
            except ValueError:
                cs_pos = 0
            updated = {
                "name":            new_name,
                "account":         acct_var.get().strip(),
                "password":        pass_var.get(),
                "char_class":      class_var.get().strip(),
                "role_profile":    rp_var.get().strip(),
                "char_select_pos": cs_pos,
                "notes":           notes_var.get(),
            }
            if new_name != name:
                delete_character(name)
            save_character(updated)
            self._refresh_characters_list()
            dlg.destroy()

        tk.Button(dlg, text="Save", command=save_and_close,
                  bg=tk_color("success"), fg="white",
                  font=THEME["font_main"], relief="flat", padx=14, pady=5
                  ).pack(pady=(0, 10))

    # ── Save ─────────────────────────────────────────────────

    def _reset_hotkeys(self):
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Reset Hotkeys",
            "Reset all hotkeys to defaults?\nThis cannot be undone.",
            parent=self.win,
        ):
            return
        for key, field in self._hk_fields.items():
            field.set(DEFAULT_HOTKEYS.get(key, ""))

    def _save(self):
        try:
            delay = int(self._delay_var.get())
        except ValueError:
            messagebox.showerror("Invalid value",
                                 "Action delay must be a whole number (milliseconds).",
                                 parent=self.win)
            return
        try:
            char_delay = int(self._char_delay_var.get())
        except ValueError:
            char_delay = 10
        try:
            gap = int(self._gap_var.get())
        except ValueError:
            gap = 4

        self.settings["hotkeys"] = {
            **self.settings.get("hotkeys", {}),
            **{k: f.get() for k, f in self._hk_fields.items()},
        }
        try:
            launch_delay = int(self._launch_delay_var.get())
        except ValueError:
            launch_delay = 3000
        self.settings["action_delay_ms"]       = delay
        self.settings["char_type_delay_ms"]    = char_delay
        self.settings["launch_delay_ms"]       = launch_delay
        self.settings["default_formation_key"] = self._formation_var.get().strip() or "t"
        self.settings["slot_commands"]         = [v.get().strip() for v in self._slot_cmd_vars]

        self.settings["layout"]["gap_px"]            = gap
        self.settings["layout"]["main_monitor"]      = self._main_mon_var.get()
        self.settings["layout"]["secondary_monitor"] = self._sec_mon_var.get()
        self.settings["layout"]["secondary_count"]   = self._sec_count_var.get()
        try:
            self.settings["layout"]["taskbar_height"]  = int(self._taskbar_h_var.get())
        except ValueError:
            self.settings["layout"]["taskbar_height"]  = 0
        self.settings["layout"]["taskbar_monitor"]     = self._taskbar_m_var.get()
        self.settings["layout"]["ar_lock"]             = "4:3" if self._ar_lock_var.get() else "none"

        # Flush all coord panels so both modes' values are in self.settings
        self._flush_invite_coords()
        self._flush_loops_coords()

        # Reform settings
        def _int(var, default):
            try:    return int(var.get())
            except: return default
        def _coord(xv, yv):
            return {"x": _int(xv, 0), "y": _int(yv, 0)}

        def _pct(xv, yv):
            try:    return {"x_pct": float(xv.get()), "y_pct": float(yv.get())}
            except: return {"x_pct": 0.0, "y_pct": 0.0}

        self.settings.setdefault("reform", {}).update({
            "click_1":        _pct(self._ref_c1x, self._ref_c1y),
            "click_delay_ms": _int(self._ref_click_delay, 200),
            "click_2":        _pct(self._ref_c2x, self._ref_c2y),
            "settle_ms":      _int(self._ref_settle, 1000),
            "key":            self._ref_key.get().strip() or "t",
            "key_delay_ms":   _int(self._ref_key_delay, 300),
        })

        # Loops scalars — coords already flushed above
        loops = self.settings.setdefault("loops", {})
        loops["key_delay_ms"]      = _int(self._loops_key_delay,    40)
        loops["key_hold_ms"]       = _int(self._loops_key_hold,     30)
        loops["modifier_delay_ms"] = _int(self._loops_mod_delay,    50)
        loops["fire_key"]          = self._loops_fire_key.get().strip() or "f"
        loops["interleave_buffs"]  = self._loops_interleave_buffs.get()
        loops["activate_settle_ms"]    = _int(self._loops_activate_settle,    300)
        loops["activate_settle_ms_2x"] = _int(self._loops_activate_settle_2x, 400)
        loops["activate_settle_ms_3x"] = _int(self._loops_activate_settle_3x, 500)

        def _f(var, default=0.0):
            try:    return float(var.get())
            except: return default

        self.settings["autologin"] = {
            "login_x_pct": _f(self._login_lx),
            "login_y_pct": _f(self._login_ly),
        }
        self.settings["char_select"] = {
            "positions":       [[_f(xv), _f(yv)] for xv, yv in self._cs_pos_vars],
            "settle_ms":       _int(self._cs_settle_var, 6000),
            "button_ready_ms": _int(self._cs_btn_ready_var, 1200),
            "accept_delay_ms": _int(self._cs_accept_d_var, 1200),
        }
        self.settings["quit_to_desktop"] = {
            "in_game":  {"x_pct": _f(self._qtd_ig_x), "y_pct": _f(self._qtd_ig_y)},
            "pre_game": {"x_pct": _f(self._qtd_pg_x), "y_pct": _f(self._qtd_pg_y)},
        }

        # Indicator settings
        if hasattr(self, "_ind_enabled_var"):
            try:
                font_size = max(8, int(self._ind_font_size_var.get()))
            except ValueError:
                font_size = 48
            try:
                ind_x = int(self._ind_x_var.get())
            except ValueError:
                ind_x = 20
            try:
                ind_y = int(self._ind_y_var.get())
            except ValueError:
                ind_y = 280
            self.settings["omit_indicator"] = {
                "enabled":    self._ind_enabled_var.get(),
                "content":    self._ind_content_var.get(),
                "x":          ind_x,
                "y":          ind_y,
                "opacity":    round(self._ind_opacity_var.get() / 100.0, 2),
                "text_color": self._ind_text_color_var.get(),
                "font_size":  font_size,
            }

        self.on_save(self.settings)
        self.win.destroy()
