# ============================================================
#  EnB Multibox Manager — gui_main.py
#  Main application window: left control panel + layout canvas
# ============================================================

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from config_manager import (
    characters_for_account,
    default_group_profile,
    default_role_profile,
    delete_profile,
    delete_role_profile,
    list_accounts,
    list_characters,
    list_invite_profiles,
    list_profiles,
    list_role_profiles,
    load_character,
    load_invite_profile,
    load_profile,
    load_role_profile,
    load_settings,
    save_character,
    save_invite_profile,
    save_profile,
    save_role_profile,
    save_settings,
)
from constants import (
    APP_NAME,
    APP_VERSION,
    CLASS_ABBREVS,
    CLASS_FULLNAMES,
    DEFAULT_HOTKEYS,
    ENB_CLASSES,
    ENB_WINDOW_TITLE,
    LOOP_KEY_OPTIONS,
    LOOP_TYPES,
    MAX_SLOTS,
    THEME,
    WIN32_NC_H,
    WIN32_NC_W,
    slot_color,
)
from layout_engine import (
    _get_monitor,
    _monitor_bounds,
    apply_layout_to_slots,
    calculate_grid,
    calculate_layout,
    canvas_to_screen,
    mgr_cell,
    monitor_to_canvas_rect,
    single_monitor_layout,
    single_monitor_layout_large,
    slot_to_canvas_rect,
)
from slot_manager import SlotManager
from window_manager import (
    activate_window,
    click_at,
    configure_key_timing,
    find_enb_windows,
    get_active_window_id,
    get_frame_extents,
    get_monitors,
    get_mouse_position,
    get_window_by_id,
    is_enb_client_pid,
    key_to_focused,
    kill_all_enb_processes,
    kill_window_process,
    launch_enb_client,
    slot_wine_prefix,
    minimize_window,
    mouse_slide_relative,
    move_resize_window,
    pid_exists,
    raise_window,
    release_modifiers,
    rename_window,
    get_toplevel_hwnd,
    reposition_window,
    restore_window,
    return_to_driver,
    set_bypass_compositor,
    set_stay_on_top,
    set_window_borderless,
    type_to_focused,
    wait_modifiers_released,
)
if sys.platform == "win32":
    from window_manager import check_pywin32, find_enb_windows_by_process
else:
    from window_manager import (
        _run, check_wmctrl, check_xdotool,
        find_enb_windows_any, winresize_wine_window,
    )

# ── Helpers ───────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR    = os.path.join(SCRIPT_DIR, "logs")

# Pseudo invite-list name: when picked, the invite list is auto-built from
# slots 2–6 (non-driver) in slot order.
# always excluded — it is never invited. Named profiles remain available.
INVITE_FROM_SLOTS = "(Slots — auto)"

# Empirically tuned launch/relaunch timing constants
_GAME_SETTLE_S      = 4.0  # wait after login window detected for game to finish loading
_AUTOLOGIN_DELAY_S  = 2.0  # wait after game loads before starting autologin sequence
_RELAUNCH_KILL_WAIT_S = 1.5  # wait for killed slot process to clean up before relaunching


def tk_color(key):
    return THEME[key]


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
    """Recursively bind wraplength-to-width on every Label in the widget tree."""
    if isinstance(widget, tk.Label):
        widget.bind(
            "<Configure>",
            lambda e, w=widget: w.config(wraplength=max(e.width - 4, 40)),
            add="+",
        )
    for child in widget.winfo_children():
        _apply_autowrap_all(child)


def autowrap(label):
    """Make a Label wrap to its own allocated width when the window resizes."""
    label.bind("<Configure>", lambda e: label.config(wraplength=max(e.width - 4, 40)))
    return label


class ToolTip:
    """Simple tooltip for tkinter widgets."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        self._after = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self.hide)
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._after = self.widget.after(400, self._show)

    def _cancel(self):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self):
        self._after = None
        # Position below and to the right of the cursor, not the widget origin,
        # so the tooltip window can never land under the cursor and cause flicker.
        x = self.widget.winfo_pointerx() + 16
        y = self.widget.winfo_pointery() + 20
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self.tip,
            text=self.text,
            bg="#2a2a2a",
            fg="#eaeaea",
            font=THEME["font_small"],
            relief="solid",
            borderwidth=1,
            padx=4,
            pady=2,
            wraplength=400,
            justify="left",
        )
        lbl.pack()

    def hide(self, _=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ── Main Application ──────────────────────────────────────────


class EnBMultiboxApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = load_settings()
        raid_setting = self.settings.get("raid_mode", "off")
        self._raid_mode = raid_setting != "off"
        self._raid_factor = {"off": 1, "2x": 2, "3x": 3}.get(raid_setting, 1)
        self._apply_key_timing()
        self.slots = SlotManager()
        self.monitors = get_monitors()
        # Reserve space for a visible (non-auto-hide) taskbar so window
        # layouts don't get placed underneath it (e.g. covering the
        # bottom-row Accept buttons on a single-monitor layout).
        _taskbar_h = self.settings["layout"].get("taskbar_height", 0)
        _taskbar_m = self.settings["layout"].get("taskbar_monitor", 1)
        if _taskbar_h:
            for m in self.monitors:
                if m["index"] == _taskbar_m:
                    m["h"] = max(0, m["h"] - _taskbar_h)
        self._abort_flag = threading.Event()
        self._loop_running = False
        self._energy_running = False
        self._daimyo_running = False
        self._invite_running = False
        self._reform_running = False
        self._daimyo_step_indices    = {}  # slot.index → position in that slot's target list
        self._daimyo_step_last_times = {}  # slot.index → timestamp of last successful step
        self._omit_proc = None
        self._omit_state_file = None
        self._omit_drag_file = None
        self._compact_mode = False
        self._mon_labels = []
        self._active_settings_win = None
        self._indicator_drag_mode = False
        self._layout_mode = self.settings["layout"].get("layout_mode", "auto")
        self._mgr_custom_pos = self.settings["layout"].get("mgr_custom_pos", None)
        self._preview_geo = None  # preset preview geometry — canvas uses this when set
        self._mgr_dragging = False
        self._indicator_cycling = False
        self._relaunching = set()  # slot indices currently being relaunched
        self._relaunch_lock = threading.Semaphore(1)  # one relaunch at a time — sequential
        self._autologin_lock = threading.Lock()  # only one autologin sequence at a time
        self._pending_crashes: set[int] = set()  # crash events waiting for debounce window
        self._crashes_assigned: set[int] = set()  # assigned slots at first-crash moment
        self._crash_debounce_timer: threading.Timer | None = None  # fires _process_crashes
        self._independent_wids: set[int] = set()  # untracked "Launch Independent Client" windows
        self._independent_pids: set[int] = set()  # their net7proxy.exe/client.exe PIDs (Windows monitor exclusion)
        self.status_var = tk.StringVar(value="Ready")
        self._first_open = not bool(list_profiles())
        self._cycle_mgr = None
        self._hk_mgr = None
        self._action_btn_ordered = []  # (key, btn) list for visibility management

        # Auto-set main/secondary monitor from xrandr primary flag
        self._auto_set_monitors()

        self._setup_window()
        self._check_deps()
        self._build_ui()
        self._load_profile(self.settings.get("active_profile", "default"))

        # Auto-tile on startup only in auto mode. Custom mode preserves saved slot geometry.
        self.root.after(200, lambda: self._auto_tile(apply=False) if self._layout_mode == "auto" else self._redraw_canvas())

        self._start_liveness_monitor()
        self._bind_hotkeys()
        self.slots.register_callback(self._on_slots_changed)
        self._build_omit_indicator()

    def _auto_set_monitors(self):
        """Set main/secondary monitor indices from xrandr primary flag on every startup."""
        if not self.monitors:
            return
        # monitors are already sorted: primary first (index 0)
        layout = self.settings.get("layout", {})
        layout["main_monitor"] = 0
        layout["secondary_monitor"] = 1 if len(self.monitors) > 1 else 0
        self.settings["layout"] = layout

    # ── Window setup ─────────────────────────────────────────

    def _setup_window(self):
        self.root.title(f"{APP_NAME}  v{APP_VERSION}")
        self.root.configure(bg=tk_color("bg"))
        self.root.minsize(1100, 660)
        self.root.resizable(True, True)
        # Center on screen
        self.root.update_idletasks()
        sh = self.root.winfo_screenheight()
        # Place on primary monitor (first 1920px), not centered across all monitors
        self.root.geometry(f"1440x800+{(1920 - 1440) // 2}+{(sh - 800) // 2}")

        # Block Tkinter menu traversal on Alt, but pass Alt+Tab to the WM.
        def _alt_guard(e):
            if e.keysym == "Tab":
                return None
            return "break"

        self.root.bind("<Alt-Key>", _alt_guard)

    def _check_deps(self):
        if sys.platform == "win32":
            if not check_pywin32():
                messagebox.showwarning(
                    "Missing Dependencies",
                    "pywin32 is required but not found.\n\n"
                    "Install with:\n  pip install pywin32\n"
                    "Then run:\n  python pywin32_postinstall.py -install",
                )
        else:
            missing = []
            if not check_xdotool():
                missing.append("xdotool")
            if not check_wmctrl():
                missing.append("wmctrl")
            if missing:
                messagebox.showwarning(
                    "Missing Dependencies",
                    f"The following tools are required but not found:\n\n"
                    f"  {', '.join(missing)}\n\n"
                    f"Install them with:\n"
                    f"  sudo pacman -S {' '.join(missing)}",
                )

    # ── UI construction ──────────────────────────────────────

    def _build_ui(self):
        self._build_menu()

        # Main paned layout: left panel | right canvas
        self.pane = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            bg=tk_color("bg"),
            sashwidth=6,
            sashrelief="raised",
        )
        self.pane.pack(fill="both", expand=True, padx=4, pady=4)

        # Left control panel
        self.left_frame = tk.Frame(self.pane, bg=tk_color("panel_bg"), width=420)
        self.pane.add(self.left_frame, minsize=380)

        # Right canvas panel
        self.right_frame = tk.Frame(self.pane, bg=tk_color("bg"))
        self.pane.add(self.right_frame, minsize=400)

        self._build_left_panel()
        self._build_right_panel()
        self._build_compact_view()
        self.root.update_idletasks()
        _apply_autowrap_all(self.root)

    def _build_menu(self):
        menubar = tk.Menu(
            self.root,
            bg=tk_color("panel_bg"),
            fg=tk_color("text"),
            activebackground=tk_color("card_bg"),
            activeforeground=tk_color("accent"),
        )
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(
            menubar, tearoff=0, bg=tk_color("panel_bg"), fg=tk_color("text")
        )
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Profile", command=self._new_profile)
        file_menu.add_command(label="Save Profile", command=self._save_current_profile)
        file_menu.add_command(label="Open Settings", command=self._open_settings_window)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._quit)

        # View menu
        view_menu = tk.Menu(
            menubar, tearoff=0, bg=tk_color("panel_bg"), fg=tk_color("text")
        )
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Compact", command=self._toggle_compact)
        view_menu.add_separator()

        # Raid Mode submenu
        self._raid_var = tk.StringVar(value=self.settings.get("raid_mode", "off"))
        raid_menu = tk.Menu(
            view_menu, tearoff=0, bg=tk_color("panel_bg"), fg=tk_color("text"),
            activebackground=tk_color("card_bg"), activeforeground=tk_color("accent"),
        )
        view_menu.add_cascade(label="Raid Mode", menu=raid_menu)
        for _label, _val in [("Off", "off"), ("2× timing", "2x"), ("3× timing", "3x")]:
            raid_menu.add_radiobutton(
                label=_label,
                variable=self._raid_var,
                value=_val,
                command=self._on_raid_mode_change,
            )
        view_menu.add_separator()

        theme_menu = tk.Menu(
            view_menu, tearoff=0, bg=tk_color("panel_bg"), fg=tk_color("text")
        )
        view_menu.add_cascade(label="Theme", menu=theme_menu)
        from constants import THEMES
        for theme_name in THEMES:
            theme_menu.add_command(
                label=theme_name,
                command=lambda n=theme_name: self._set_theme(n),
            )

        # Links
        import webbrowser
        links_menu = tk.Menu(
            menubar, tearoff=0, bg=tk_color("panel_bg"), fg=tk_color("text"),
            activebackground=tk_color("card_bg"), activeforeground=tk_color("accent"),
        )
        menubar.add_cascade(label="Links", menu=links_menu)
        for _label, _url in [
            ("EnB Maps",  "http://enbmaps.de/"),
            ("Net-7",     "https://www.net-7.org"),
            ("EnB Wiki",  "https://net7wiki.bmsite.net"),
            ("EnB Forum", "https://forum.enb-emulator.com/"),
        ]:
            links_menu.add_command(
                label=_label,
                command=lambda u=_url: webbrowser.open(u),
            )

        # Help
        help_menu = tk.Menu(
            menubar, tearoff=0, bg=tk_color("panel_bg"), fg=tk_color("text")
        )
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Read Me", command=self._show_readme)
        help_menu.add_command(
            label="User Guide",
            command=lambda: self._show_doc("User Guide", os.path.join("docs", "USER_GUIDE.md")),
        )
        help_menu.add_command(
            label="Hotkeys & Macros",
            command=lambda: self._show_doc("Hotkeys & Macros", os.path.join("docs", "HOTKEYS_MACROS.md")),
        )
        help_menu.add_command(
            label="Installation Guide (Linux)",
            command=lambda: self._show_doc("Installation Guide — Linux", os.path.join("docs", "INSTALL.md")),
        )
        help_menu.add_command(
            label="Installation Guide (Windows)",
            command=lambda: self._show_doc("Installation Guide — Windows", os.path.join("docs", "INSTALL_WINDOWS.md")),
        )
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)

    # ────────────────────────────────────────────────────────
    # LEFT PANEL
    # ────────────────────────────────────────────────────────

    def _build_left_panel(self):
        lf = self.left_frame

        # Status bar stays at the bottom, outside the scroll area
        status = tk.Label(
            lf,
            textvariable=self.status_var,
            bg=tk_color("bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
            anchor="w",
            padx=6,
            justify="left",
        )
        status.pack(fill="x", side="bottom")
        status.bind("<Configure>", lambda e: status.config(wraplength=max(e.width - 12, 40)))

        # Scrollable container
        scrollbar = ttk.Scrollbar(lf, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        scroll_canvas = tk.Canvas(
            lf,
            bg=tk_color("panel_bg"),
            highlightthickness=0,
            borderwidth=0,
            yscrollcommand=scrollbar.set,
        )
        scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=scroll_canvas.yview)

        # Inner frame — all content packs here
        inner = tk.Frame(scroll_canvas, bg=tk_color("panel_bg"))
        cw_id = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(event):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        inner.bind("<Configure>", _on_inner_configure)

        def _on_scroll_canvas_configure(event):
            scroll_canvas.itemconfig(cw_id, width=event.width)

        scroll_canvas.bind("<Configure>", _on_scroll_canvas_configure)

        # Mousewheel scroll — platform-specific event names
        if sys.platform == "win32":
            def _scroll(event):
                scroll_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            def _bind_wheel(event):
                self.root.bind("<MouseWheel>", _scroll)
            def _unbind_wheel(event):
                self.root.unbind("<MouseWheel>")
        else:
            def _scroll(event):
                if event.num == 4:
                    scroll_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    scroll_canvas.yview_scroll(1, "units")
            def _bind_wheel(event):
                self.root.bind("<Button-4>", _scroll)
                self.root.bind("<Button-5>", _scroll)
            def _unbind_wheel(event):
                self.root.unbind("<Button-4>")
                self.root.unbind("<Button-5>")

        scroll_canvas.bind("<Enter>", _bind_wheel)
        scroll_canvas.bind("<Leave>", _unbind_wheel)

        # Build content into inner frame.
        # _compact_header_frame and _compact_body_frame are hidden in compact mode;
        # profile bar and action buttons remain visible.

        # Header: app title — hidden in compact
        self._compact_header_frame = tk.Frame(inner, bg=tk_color("panel_bg"))
        self._compact_header_frame.pack(fill="x")
        tk.Label(
            self._compact_header_frame,
            text=APP_NAME.upper(),
            bg=tk_color("panel_bg"),
            fg=tk_color("accent"),
            font=THEME["font_title"],
            pady=8,
        ).pack(fill="x")
        tk.Frame(self._compact_header_frame, bg=tk_color("accent"), height=1).pack(
            fill="x"
        )

        # Profile bar — always visible
        self._build_profile_bar(inner)

        # Separator between profile and body — hidden in compact
        self._compact_sep = tk.Frame(inner, bg=tk_color("slot_border"), height=1)
        self._compact_sep.pack(fill="x", pady=2)

        # Body: slot cards + combat + invite — hidden in compact
        self._compact_body_frame = tk.Frame(inner, bg=tk_color("panel_bg"))
        self._compact_body_frame.pack(fill="x")
        self._build_slot_panel(self._compact_body_frame)
        tk.Frame(self._compact_body_frame, bg=tk_color("slot_border"), height=1).pack(
            fill="x", pady=2
        )
        self._build_invite_bar(self._compact_body_frame)
        tk.Frame(self._compact_body_frame, bg=tk_color("slot_border"), height=1).pack(
            fill="x", pady=2
        )

        # Action buttons — always visible
        self._build_action_buttons(inner)

        # Compact-only extras — hidden in normal mode, shown in compact mode
        self._compact_extra_frame = tk.Frame(inner, bg=tk_color("panel_bg"))
        compact_top = tk.Frame(self._compact_extra_frame, bg=tk_color("panel_bg"))
        compact_top.pack(fill="x")
        tk.Button(
            self._compact_extra_frame,
            text="⌨  Auto Login",
            command=self._auto_login,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_main"],
            relief="flat",
            pady=4,
            anchor="w",
            padx=8,
        ).pack(fill="x", pady=2)

    def _build_profile_bar(self, parent):
        frame = tk.Frame(parent, bg=tk_color("panel_bg"), padx=6, pady=4)
        frame.pack(fill="x")
        self._profile_bar_frame = frame

        tk.Label(
            frame,
            text="Group Profile:",
            bg=tk_color("panel_bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).grid(row=0, column=0, sticky="w")

        self.profile_var = tk.StringVar()
        profiles = list_profiles() or ["default"]
        self.profile_combo = ttk.Combobox(
            frame,
            textvariable=self.profile_var,
            values=profiles,
            width=18,
            state="readonly",
            font=THEME["font_main"],
        )
        self.profile_combo.grid(row=0, column=1, padx=4)
        self.profile_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._load_profile(self.profile_var.get())
        )

        tk.Button(
            frame,
            text="＋",
            command=self._new_profile,
            bg=tk_color("card_bg"),
            fg=tk_color("accent"),
            font=THEME["font_main"],
            relief="flat",
            padx=4,
        ).grid(row=0, column=2)

        tk.Button(
            frame,
            text="✕",
            command=self._delete_profile,
            bg=tk_color("card_bg"),
            fg=tk_color("danger"),
            font=THEME["font_main"],
            relief="flat",
            padx=4,
        ).grid(row=0, column=3)

        # Detect + Apply Layout — own sub-frame spanning all 4 columns so each
        # button gets equal half-width regardless of + / ✕ column sizes.
        btn_row = tk.Frame(frame, bg=tk_color("panel_bg"))
        btn_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        detect_btn = tk.Button(
            btn_row,
            text="⟳ Detect",
            command=self._auto_detect,
            bg=tk_color("success"),
            fg="white",
            font=THEME["font_main"],
            relief="flat",
            padx=6,
            pady=2,
        )
        detect_btn.grid(row=0, column=0, sticky="ew")
        ToolTip(detect_btn, "Scan for running EnB clients and assign to empty slots")

        apply_btn = tk.Button(
            btn_row,
            text="⊞ Apply Layout",
            command=self._on_apply_layout_click,
            bg=tk_color("card_bg"),
            fg=tk_color("accent2"),
            font=THEME["font_main"],
            relief="flat",
            padx=6,
            pady=2,
        )
        apply_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ToolTip(apply_btn, "Move and resize all client windows to their grid positions")

    def _build_slot_panel(self, parent):
        container = tk.Frame(parent, bg=tk_color("panel_bg"), padx=6)
        container.pack(fill="x")

        tk.Label(
            container,
            text="SLOTS",
            bg=tk_color("panel_bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).pack(anchor="w", pady=(4, 2))

        self.slot_frames = []
        self.slot_role_vars = []

        for i in range(MAX_SLOTS):
            card = self._build_slot_card(container, i)
            card.pack(fill="x", pady=2)

    def _build_slot_card(self, parent, index: int) -> tk.Frame:
        """Build one slot card row.
        Top row: slot # | account dropdown | character dropdown | status | ⋮
        Picking a character auto-fills role / role_profile / credentials from
        the character profile."""
        slot = self.slots.slot(index)

        card = tk.Frame(
            parent,
            bg=tk_color("slot_empty"),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=tk_color("slot_border"),
        )
        card.pack_propagate(False)
        card.configure(height=42)
        card.bind("<Button-3>", lambda e, i=index: self._slot_context_menu_at(i, e.x_root, e.y_root))

        # Slot number label
        # Pack ⋮ first so it always claims its space before left items fill the row
        ctx_btn = tk.Button(
            card,
            text="⋮",
            bg=tk_color("slot_empty"),
            fg=tk_color("text_dim"),
            font=THEME["font_main"],
            relief="flat",
            command=lambda i=index, w=card: self._slot_context_menu(i, w),
        )
        ctx_btn.pack(side="right", padx=4)

        num_lbl = tk.Label(
            card,
            text=f"{index + 1}",
            bg=tk_color("slot_empty"),
            fg=tk_color("text_dim"),
            font=THEME["font_mono"],
            width=2,
            anchor="center",
        )
        num_lbl.pack(side="left", padx=(6, 2))

        # Role and status pack right (before char_cb) so char_cb can fill remaining space
        role_var = tk.StringVar(value=slot.role or "—")
        role_lbl = tk.Label(
            card,
            textvariable=role_var,
            bg=tk_color("slot_empty"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
            width=3,
            anchor="center",
        )
        role_lbl.pack(side="right", padx=(0, 4))

        status_var = tk.StringVar(value="○")
        status_lbl = tk.Label(
            card,
            textvariable=status_var,
            bg=tk_color("slot_empty"),
            fg=tk_color("text_dim"),
            font=THEME["font_main"],
        )
        status_lbl.pack(side="right", padx=2)

        # Account dropdown — drives the character list
        account_var = tk.StringVar(value=slot.username)
        account_opts = [""] + list_accounts()
        account_cb = ttk.Combobox(
            card,
            textvariable=account_var,
            values=account_opts,
            width=12,
            font=THEME["font_main"],
        )
        account_cb.pack(side="left", padx=2)
        account_cb.bind(
            "<<ComboboxSelected>>", lambda _, i=index: self._on_slot_account_change(i)
        )

        # Character dropdown — expands to fill remaining space between account and status
        char_var = tk.StringVar(value=slot.character or slot.char_name)
        char_cb = ttk.Combobox(
            card,
            textvariable=char_var,
            values=[""] + list_characters(),
            state="readonly",
            font=THEME["font_main"],
        )
        char_cb.pack(side="left", padx=2, fill="x", expand=True)
        char_cb.bind(
            "<<ComboboxSelected>>", lambda _, i=index: self._on_slot_character_change(i)
        )

        self.slot_frames.append(
            {
                "card": card,
                "role_var": role_var,
                "account_var": account_var,
                "account_cb": account_cb,
                "char_var": char_var,
                "char_cb": char_cb,
                "status_var": status_var,
                "num_lbl": num_lbl,
            }
        )
        self.slot_role_vars.append(role_var)

        return card

    def _build_invite_bar(self, parent):
        frame = tk.Frame(parent, bg=tk_color("panel_bg"), padx=6, pady=4)
        frame.pack(fill="x")

        tk.Label(
            frame,
            text="Invite List:",
            bg=tk_color("panel_bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).grid(row=0, column=0, sticky="w")

        self.invite_var = tk.StringVar()
        # First entry is the dynamic "from slots" list — built at run time
        # from characters currently assigned to slots (in slot order).
        # Named lists (Tours, GoBB, etc.) follow.
        profiles = [INVITE_FROM_SLOTS] + list_invite_profiles()
        self.invite_combo = ttk.Combobox(
            frame,
            textvariable=self.invite_var,
            values=profiles,
            width=18,
            state="readonly",
            font=THEME["font_main"],
        )
        self.invite_combo.grid(row=0, column=1, padx=4)
        if profiles:
            self.invite_combo.current(0)

        tk.Button(
            frame,
            text="＋",
            command=self._new_invite_profile,
            bg=tk_color("card_bg"),
            fg=tk_color("accent"),
            font=THEME["font_main"],
            relief="flat",
            padx=4,
        ).grid(row=0, column=2)

        tk.Button(
            frame,
            text="Edit",
            command=self._edit_invite_list,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_small"],
            relief="flat",
            padx=6,
        ).grid(row=0, column=3, padx=(2, 0))

    def _build_action_buttons(self, parent):
        frame = tk.Frame(parent, bg=tk_color("panel_bg"), padx=6, pady=6)
        frame.pack(fill="x")

        # Header row with gear icon for button visibility editor
        hdr = tk.Frame(frame, bg=tk_color("panel_bg"))
        hdr.pack(fill="x", pady=(0, 2))
        tk.Label(
            hdr, text="ACTIONS",
            bg=tk_color("panel_bg"), fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).pack(side="left")
        gear_btn = tk.Button(
            hdr, text="⚙",
            command=self._open_button_visibility_editor,
            bg=tk_color("panel_bg"), fg=tk_color("text_dim"),
            font=THEME["font_small"], relief="flat", padx=4,
        )
        gear_btn.pack(side="right")
        ToolTip(gear_btn, "Show/hide buttons for this view mode")

        self._action_btn_ordered = []
        self._action_btn_meta = {}  # key → (base_text, hk_key)

        # Maps button key → settings hotkey key for label display
        _hk = {
            "emergency_stop": "abort",
            "stop":           "abort",
            "combat_loop":    "combat_loop",
            "debuff_loop":    "debuff_cycle",
            "buff_loop":      "buff_loop",
            "heal_loop":      "heal_cycle",
            "energy_loop":    "energy_loop",
            "daimyo_loop":    "daimyo_step",
            "invite":         "invite",
            "reform":         "reform",
        }

        btn_specs = [
            (
                "emergency_stop",
                "⛔  Stop All Scripts",
                self._stop_loop,
                tk_color("danger"), "white",
                "Stop all running scripts — loops, autologin sequences (does not kill clients)",
            ),
            (
                "restart_app",
                "↺  Restart Manager",
                self._restart_app,
                tk_color("warning"), "white",
                "Save settings and restart the manager application",
            ),
            (
                "combat_loop",
                "▶  Combat Loop",
                lambda: self._start_loop("combat"),
                tk_color("accent"), "white",
                "Assist → Fire → combat keys for each slot",
            ),
            (
                "debuff_loop",
                "⚡  Debuff Loop",
                lambda: self._start_loop("debuff"),
                tk_color("card_bg"), tk_color("accent2"),
                "Press debuff keys for each slot that has them",
            ),
            (
                "buff_loop",
                "✨  Buff Loop",
                lambda: self._start_loop("buff"),
                tk_color("card_bg"), tk_color("accent"),
                "Press buff keys for each slot (one pass)",
            ),
            (
                "heal_loop",
                "❤  Heal Loop",
                lambda: self._start_loop("heal"),
                tk_color("card_bg"), tk_color("text"),
                "TT: target driver → heal → re-assist → fire. TE: repair only",
            ),
            (
                "energy_loop",
                "⚡  Energy Loop",
                self._start_energy_loop,
                tk_color("card_bg"), tk_color("accent2"),
                "Press energy keys for each slot; PV9 slots run one pass",
            ),
            (
                "daimyo_loop",
                "⚗  Daimyo",
                self._start_daimyo_action,
                tk_color("card_bg"), tk_color("accent"),
                "Mode 1: continuous loop. Mode 2: one step per press. F-key→buff→assist→fire",
            ),
            (
                "daimyo_mode_toggle",
                self._daimyo_mode_text(),
                self._toggle_daimyo_mode,
                tk_color("card_bg"), tk_color("text_dim"),
                "Toggle between Daimyo Mode 1 (continuous loop) and Mode 2 (manual step per press)",
            ),
            (
                "invite",
                "✉  Invite Party",
                self._run_invite,
                tk_color("card_bg"), tk_color("text"),
                "Send /invite to all names in list",
            ),
            (
                "reform",
                "⚑  Reform",
                self._run_reform,
                tk_color("card_bg"), tk_color("text"),
                "Set formation and have party join",
            ),
            (
                "compact",
                "▣  Compact",
                self._toggle_compact,
                tk_color("card_bg"), tk_color("accent2"),
                "Shrink manager to the empty grid slot position (toggle)",
            ),
        ]

        for key, text, cmd, bg, fg, tip in btn_specs:
            hk_key = _hk.get(key, "")
            label = text + self._fmt_hotkey(hk_key)
            btn = tk.Button(
                frame,
                text=label,
                command=cmd,
                bg=bg,
                fg=fg,
                font=THEME["font_main"],
                relief="flat",
                pady=4,
                anchor="w",
                padx=8,
            )
            btn.pack(fill="x", pady=2)
            ToolTip(btn, tip)
            self._action_btn_ordered.append((key, btn))
            self._action_btn_meta[key] = (text, hk_key)

        self._apply_button_visibility()

    # ────────────────────────────────────────────────────────
    # RIGHT PANEL — Layout Canvas
    # ────────────────────────────────────────────────────────

    def _build_right_panel(self):
        rf = self.right_frame

        # Header row
        hdr = tk.Frame(rf, bg=tk_color("bg"))
        hdr.pack(fill="x", padx=6, pady=(6, 2))

        tk.Label(
            hdr,
            text="LAYOUT CANVAS",
            bg=tk_color("bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).pack(side="left")

        # Secondary slots slider + Auto Tile + Apply Layout in header
        self._build_secondary_controls(hdr)

        # Preset bar
        preset_bar = tk.Frame(rf, bg=tk_color("bg"))
        preset_bar.pack(fill="x", padx=6, pady=(0, 2))
        self._build_preset_bar(preset_bar)

        # Controls row: monitor selectors only
        ctrl = tk.Frame(rf, bg=tk_color("bg"))
        ctrl.pack(fill="x", padx=6, pady=2)
        self._build_layout_controls(ctrl)

        # Canvas — don't expand vertically, maintain aspect ratio
        self.canvas_frame = tk.Frame(rf, bg=tk_color("bg"))
        self.canvas_frame.pack(fill="x", expand=False, padx=6, pady=4)
        self._build_canvas(self.canvas_frame)
        # Set initial canvas height based on aspect ratio after layout
        self.root.after(100, self._fix_canvas_aspect)

        # Snap controls below canvas
        snap_row = tk.Frame(rf, bg=tk_color("bg"))
        snap_row.pack(fill="x", padx=6, pady=(0, 2))
        self._build_snap_controls(snap_row)

        # Action buttons below canvas
        self._build_canvas_action_buttons(rf)

    def _build_canvas_action_buttons(self, parent):
        """Buttons that live below the layout canvas in the right panel."""
        frame = tk.Frame(parent, bg=tk_color("bg"), padx=6, pady=4)
        frame.pack(fill="x")
        self._canvas_action_frame = frame

        # Autologin-on-launch checkbox — gates whether Launch All also runs
        # the full login + character-select sequence after windows appear.
        self.autologin_var = tk.BooleanVar(
            value=self.settings.get("autologin_on_launch", False)
        )
        autologin_cb = tk.Checkbutton(
            frame,
            text="Autologin on Launch All",
            variable=self.autologin_var,
            command=self._on_autologin_toggle,
            bg=tk_color("bg"),
            fg=tk_color("text"),
            selectcolor=tk_color("card_bg"),
            activebackground=tk_color("bg"),
            font=THEME["font_small"],
            anchor="w",
        )
        autologin_cb.grid(row=99, column=0, columnspan=2, sticky="w", pady=(2, 2))
        ToolTip(
            autologin_cb,
            "When set, Launch All also clicks login + character select for each slot",
        )

        self.auto_relaunch_var = tk.BooleanVar(
            value=self.settings.get("auto_relaunch", False)
        )
        ar_cb = tk.Checkbutton(
            frame,
            text="Auto-relaunch on crash",
            variable=self.auto_relaunch_var,
            command=self._on_auto_relaunch_toggle,
            bg=tk_color("bg"),
            fg=tk_color("text"),
            selectcolor=tk_color("card_bg"),
            activebackground=tk_color("bg"),
            font=THEME["font_small"],
            anchor="w",
        )
        ar_cb.grid(row=100, column=0, columnspan=2, sticky="w", pady=(0, 2))
        ToolTip(
            ar_cb,
            "Automatically relaunch a slot if its client crashes. "
            "Use right-click → Quit to Desktop to close intentionally.",
        )

        self.zone_freeze_var = tk.BooleanVar(
            value=self.settings.get("zone_freeze_enabled", False)
        )
        zf_cb = tk.Checkbutton(
            frame,
            text="Zone freeze detection",
            variable=self.zone_freeze_var,
            command=self._on_zone_freeze_toggle,
            bg=tk_color("bg"),
            fg=tk_color("text"),
            selectcolor=tk_color("card_bg"),
            activebackground=tk_color("bg"),
            font=THEME["font_small"],
            anchor="w",
        )
        zf_cb.grid(row=101, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ToolTip(
            zf_cb,
            "Relaunch a slot that freezes mid-zone. Each slot watches its own "
            "chat.log: the moment it starts zoning, a timer arms — if its own "
            f"arrival isn't confirmed within {self.settings.get('frozen_zone_timeout_s', 20)}s, "
            "it's treated as frozen and relaunched. Each slot is judged only on "
            "its own progress, so independent zoning (different sectors, "
            "solo play) won't trigger false relaunches.\n\n"
            "Requires Auto-relaunch on crash to also be enabled.",
        )

        # (text, cmd, bg, fg, tip, row, col)
        btn_specs = [
            (
                "⏻  Launch All",
                self._launch_all_clients,
                tk_color("success"),
                "white",
                "Launch all slot clients in sequence then auto-detect",
                0,
                0,
            ),
            (
                "⌨  Auto Login",
                self._auto_login,
                tk_color("card_bg"),
                tk_color("text"),
                "Send Tab Tab username Tab password Enter to each slot",
                1,
                0,
            ),
            (
                "⬆  Top All",
                self._toggle_stay_on_top_all,
                tk_color("card_bg"),
                tk_color("text"),
                "Toggle always-on-top on all assigned slots",
                2,
                0,
            ),
            (
                "⏻  Quit to Desktop",
                self._quit_to_desktop_all,
                tk_color("warning"),
                "white",
                "Send Escape + Quit to Desktop to each client in sequence",
                3,
                0,
            ),
            (
                "☠  Kill All",
                self._kill_all_clients,
                tk_color("danger"),
                "white",
                "Force-kill all client processes immediately (no grace quit)",
                4,
                0,
            ),
            (
                "↑  Updates",
                self._launch_updater,
                tk_color("card_bg"),
                tk_color("text"),
                "Open Net7 launcher to check for game updates",
                0,
                1,
            ),
            (
                "🔇 Mute Sounds",
                self._mute_login_sounds,
                tk_color("card_bg"),
                tk_color("text"),
                "Zero login/voice/footstep SoundVolume entries in sounds.ini",
                1,
                1,
            ),
            (
                "◑  Dark Mode",
                self._apply_dark_mode,
                tk_color("card_bg"),
                tk_color("text"),
                "Removes star brightness",
                2,
                1,
            ),
            (
                "🔒  Privacy",
                self._apply_privacy_settings,
                tk_color("card_bg"),
                tk_color("text"),
                "Hide login, disable broadcast/local/race channels, keep guild/group/private",
                3,
                1,
            ),
            (
                "💾  Save Settings",
                self._save_game_settings,
                tk_color("card_bg"),
                tk_color("text"),
                "Back up shortcut.ini + player options to config/game_settings_backup/",
                4,
                1,
            ),
            (
                "📂  Load Settings",
                self._load_game_settings,
                tk_color("card_bg"),
                tk_color("text"),
                "Restore shortcut.ini + player options from backup",
                5,
                1,
            ),
            (
                "⊞  Launch Independent Client",
                self._launch_independent_slot,
                tk_color("card_bg"),
                tk_color("accent2"),
                "Launch an independent (untracked) client in its own normal window",
                5,
                0,
            ),
        ]

        for text, cmd, bg, fg, tip, row, col in btn_specs:
            btn = tk.Button(
                frame,
                text=text,
                command=cmd,
                bg=bg,
                fg=fg,
                font=THEME["font_main"],
                relief="flat",
                pady=4,
                anchor="w",
                padx=8,
            )
            btn.grid(
                row=row, column=col, sticky="ew", padx=(0, 4 if col == 0 else 0), pady=2
            )
            ToolTip(btn, tip)

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _build_secondary_controls(self, parent):
        """Secondary-slot slider + Auto Tile + Apply Layout — lives in the header row."""
        tk.Label(
            parent,
            text="  Secondary slots:",
            bg=tk_color("bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).pack(side="left")

        self.sec_count_var = tk.IntVar(
            value=self.settings["layout"].get("secondary_count", 5)
        )

        self.sec_slider_label = tk.Label(
            parent,
            textvariable=self.sec_count_var,
            bg=tk_color("bg"),
            fg=tk_color("accent"),
            font=THEME["font_main"],
            width=2,
        )
        self.sec_slider_label.pack(side="left", padx=(2, 0))

        slider = tk.Scale(
            parent,
            from_=0,
            to=MAX_SLOTS - 1,
            orient=tk.HORIZONTAL,
            variable=self.sec_count_var,
            bg=tk_color("bg"),
            fg=tk_color("text"),
            troughcolor=tk_color("card_bg"),
            highlightthickness=0,
            showvalue=False,
            length=100,
            sliderlength=16,
            command=lambda _: self._on_layout_change(),
        )
        slider.pack(side="left", padx=(0, 6))
        ToolTip(slider, "Number of windows to tile on secondary monitor")

        self._reset_auto_btn = tk.Button(
            parent,
            text="Reset to Auto",
            command=self._reset_to_auto,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_small"],
            relief="flat",
            padx=6,
            state="disabled" if self._layout_mode == "auto" else "normal",
        )
        self._reset_auto_btn.pack(side="left", padx=(0, 4))
        ToolTip(self._reset_auto_btn, "Exit custom mode and recalculate layout from slider/monitor settings")
        tk.Button(
            parent,
            text="⟳ Apply Layout",
            command=self._on_apply_layout_click,
            bg=tk_color("success"),
            fg="white",
            font=THEME["font_small"],
            relief="flat",
            padx=6,
        ).pack(side="left", padx=(0, 8))

        mode_color = tk_color("success") if self._layout_mode == "auto" else tk_color("accent2")
        mode_text = "AUTO" if self._layout_mode == "auto" else "CUSTOM"
        self._mode_label = tk.Label(
            parent,
            text=mode_text,
            bg=tk_color("bg"),
            fg=mode_color,
            font=THEME["font_small"],
        )
        self._mode_label.pack(side="left", padx=(4, 0))
        ToolTip(self._mode_label, "AUTO: slider/monitor controls drive geometry\nCUSTOM: drag/preset geometry is locked")

    def _build_preset_bar(self, parent):
        tk.Label(parent, text="Preset:", bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]).pack(side="left")

        self._preset_var = tk.StringVar()
        self._preset_combo = ttk.Combobox(parent, textvariable=self._preset_var,
                                          width=22, state="readonly", font=THEME["font_small"])
        self._preset_combo.pack(side="left", padx=(2, 4))
        self._preset_combo.bind("<<ComboboxSelected>>", lambda _: self._on_preset_selected())

        apply_btn = tk.Button(parent, text="Apply", command=self._apply_selected_preset,
                              bg=tk_color("card_bg"), fg=tk_color("text"), font=THEME["font_small"],
                              relief="flat", padx=6)
        apply_btn.pack(side="left", padx=(0, 4))
        ToolTip(apply_btn, "Apply this preset: updates canvas and moves windows to the new positions")

        save_btn = tk.Button(parent, text="Save As...", command=self._save_preset_dialog,
                             bg=tk_color("card_bg"), fg=tk_color("text"), font=THEME["font_small"],
                             relief="flat", padx=6)
        save_btn.pack(side="left", padx=(0, 4))
        ToolTip(save_btn, "Save the current canvas layout as a named preset")

        self._delete_preset_btn = tk.Button(parent, text="Delete", command=self._delete_selected_preset,
                                            bg=tk_color("card_bg"), fg=tk_color("text"),
                                            font=THEME["font_small"], relief="flat", padx=6,
                                            state="disabled")
        self._delete_preset_btn.pack(side="left")
        ToolTip(self._delete_preset_btn, "Delete the selected user preset (built-in presets cannot be deleted)")
        # Populate after building — methods need _preset_combo to exist
        self.root.after(50, self._restore_last_preset)

    def _build_snap_controls(self, parent):
        self._snap_var = tk.BooleanVar(value=self.settings["layout"].get("snap_enabled", True))
        snap_cb = tk.Checkbutton(parent, text="Snap", variable=self._snap_var,
                                 command=self._on_snap_toggle,
                                 bg=tk_color("bg"), fg=tk_color("text"),
                                 selectcolor=tk_color("card_bg"),
                                 activebackground=tk_color("bg"),
                                 font=THEME["font_small"])
        snap_cb.pack(side="left")
        ToolTip(snap_cb, "Snap slots to monitor edges and other slot edges while dragging")

        tk.Label(parent, text="Threshold:", bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]).pack(side="left", padx=(8, 2))
        self._snap_threshold_var = tk.IntVar(value=self.settings["layout"].get("snap_threshold_px", 20))
        snap_spin = tk.Spinbox(parent, from_=4, to=100, increment=4,
                               textvariable=self._snap_threshold_var, width=4,
                               command=self._on_snap_threshold_change,
                               bg=tk_color("card_bg"), fg=tk_color("text"),
                               buttonbackground=tk_color("card_bg"),
                               font=THEME["font_small"], relief="flat")
        snap_spin.pack(side="left", padx=(0, 2))
        snap_spin.bind("<FocusOut>", lambda _: self._on_snap_threshold_change())
        snap_spin.bind("<Return>", lambda _: self._on_snap_threshold_change())
        tk.Label(parent, text="px", bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]).pack(side="left")

    def _on_snap_toggle(self):
        self.settings["layout"]["snap_enabled"] = self._snap_var.get()
        save_settings(self.settings)

    def _on_snap_threshold_change(self):
        try:
            self.settings["layout"]["snap_threshold_px"] = self._snap_threshold_var.get()
            save_settings(self.settings)
        except Exception:
            pass

    def _build_layout_controls(self, parent):
        def _mon_label(m):
            tag = " PRIMARY" if m.get("is_primary") else ""
            return f"{m['index']}  {m['name']} {m['w']}×{m['h']}{tag}"

        mon_labels = [_mon_label(m) for m in self.monitors] or ["0  default 1920×1080"]
        mon_indices = list(range(len(self.monitors))) or [0]

        # Main monitor selector
        tk.Label(
            parent,
            text="Main:",
            bg=tk_color("bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).pack(side="left")
        self.main_mon_var = tk.IntVar(
            value=self.settings["layout"].get("main_monitor", 0)
        )
        main_combo = ttk.Combobox(
            parent,
            textvariable=self.main_mon_var,
            values=mon_indices,
            width=3,
            state="readonly",
            font=THEME["font_small"],
        )
        main_combo.pack(side="left", padx=(2, 4))
        main_combo.bind("<<ComboboxSelected>>", lambda _: self._on_layout_change())

        # Monitor name label (shows detected info next to index)
        self._main_mon_info = tk.Label(
            parent,
            text=mon_labels[self.main_mon_var.get()] if mon_labels else "",
            bg=tk_color("bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        )
        self._main_mon_info.pack(side="left", padx=(0, 8))

        # Secondary monitor selector
        tk.Label(
            parent,
            text="Secondary:",
            bg=tk_color("bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).pack(side="left")
        self.sec_mon_var = tk.IntVar(
            value=self.settings["layout"].get("secondary_monitor", 1)
        )
        sec_combo = ttk.Combobox(
            parent,
            textvariable=self.sec_mon_var,
            values=mon_indices,
            width=3,
            state="readonly",
            font=THEME["font_small"],
        )
        sec_combo.pack(side="left", padx=(2, 4))
        sec_combo.bind("<<ComboboxSelected>>", lambda _: self._on_layout_change())

        sec_idx = self.sec_mon_var.get()
        self._sec_mon_info = tk.Label(
            parent,
            text=mon_labels[sec_idx] if sec_idx < len(mon_labels) else "",
            bg=tk_color("bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        )
        self._sec_mon_info.pack(side="left", padx=(0, 8))

        # Store labels for updating on change
        self._mon_labels = mon_labels

    def _build_canvas(self, parent):
        """Build the layout canvas widget — delegates to _rebuild_canvas_only."""
        self._rebuild_canvas_only(parent)

    def _fix_canvas_aspect(self):
        """Set canvas height to correct aspect ratio based on current width."""


        self.root.update_idletasks()
        monitors = self.monitors or [{"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080}]
        total_w, total_h, _, _ = _monitor_bounds(monitors)
        cw = self.canvas.winfo_width()
        if cw > 10 and total_w > 0:
            correct_h = max(100, int(cw * total_h / total_w))
            self._aspect_updating = True
            self.canvas.configure(height=correct_h)
            self._aspect_updating = False
        self._redraw_canvas()

    def _on_canvas_configure(self, event):
        """Redraw canvas on resize, maintain aspect ratio."""
        if self._aspect_updating:
            return


        monitors = self.monitors or [
            {"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080, "name": "?"}
        ]
        total_w, total_h, _, _ = _monitor_bounds(monitors)
        if total_w > 0 and event.width > 10:
            correct_h = max(100, int(event.width * total_h / total_w))
            if abs(self.canvas.winfo_height() - correct_h) > 4:
                self._aspect_updating = True
                self.canvas.configure(height=correct_h)
                self._aspect_updating = False
        self._redraw_canvas()

    # ── Canvas drawing ────────────────────────────────────────

    def _redraw_canvas(self):
        """Redraw all visible canvases."""
        self._draw_on_canvas(self.canvas)
        if self._compact_mode and hasattr(self, "_compact_canvas"):
            self._draw_on_canvas(self._compact_canvas)

    def _draw_on_canvas(self, c):
        """Draw the layout onto canvas widget c."""
        c.delete("all")
        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 10 or ch < 10:
            return

        monitors = self.monitors or [
            {"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080, "name": "?"}
        ]

        for mon in monitors:
            cx, cy, mw, mh = monitor_to_canvas_rect(mon, monitors, cw, ch)
            c.create_rectangle(cx, cy, cx + mw, cy + mh,
                               fill="#111122", outline=tk_color("slot_border"), width=1)
            c.create_text(cx + 4, cy + 4, anchor="nw",
                          text=f"Monitor {mon['index']}  {mon['w']}×{mon['h']}",
                          fill=tk_color("text_dim"), font=THEME["font_small"])

        if self._preview_geo:
            sec_count = sum(1 for i, g in enumerate(self._preview_geo) if i > 0 and g is not None)
        else:
            sec_count = self.sec_count_var.get()
        any_drawn = False
        for i, slot in enumerate(self.slots.slots):
            if i > 0 and i > sec_count:
                continue
            has_preview = self._preview_geo and i < len(self._preview_geo) and self._preview_geo[i]
            if not slot.is_assigned and i > 0 and slot.x == 0 and slot.y == 0 and not has_preview:
                continue

            pgeo = self._preview_geo[i] if (self._preview_geo and i < len(self._preview_geo) and self._preview_geo[i]) else None
            geo = pgeo if pgeo else {"x": slot.x, "y": slot.y, "w": slot.w, "h": slot.h}
            sx, sy, sw, sh = slot_to_canvas_rect(geo, monitors, cw, ch)

            assigned = slot.is_assigned
            active = i == self.slots.active_index
            color = slot_color(slot.role) if slot.role else tk_color("slot_empty")
            border = tk_color("accent") if active else tk_color("slot_border")
            alpha = color if assigned else tk_color("slot_empty")
            any_drawn = True

            c.create_rectangle(sx, sy, sx + sw, sy + sh,
                                fill=alpha, outline=border,
                                width=2 if active else 1,
                                tags=(f"slot_{i}", "slot"))

            if assigned:
                primary = slot.character or slot.char_name or slot.label
                bits = []
                if slot.role:
                    bits.append(slot.role)
                if slot.username:
                    bits.append(slot.username)
                label = primary + ("\n" + " · ".join(bits) if bits else "")
            else:
                label = f"[{i + 1}]"
            c.create_text(sx + sw // 2, sy + sh // 2, text=label,
                          fill="white" if assigned else tk_color("text_dim"),
                          font=THEME["font_heading"] if assigned else THEME["font_small"],
                          tags=(f"slot_{i}", "slot"))

            if sw > 12 and sh > 12:
                hx = sx + sw - 6
                hy = sy + sh - 6
                c.create_rectangle(hx, hy, hx + 6, hy + 6,
                                   fill=tk_color("accent2"), outline="",
                                   tags=(f"handle_{i}", "handle"))

        try:
            mgr = self._get_mgr_geo()
            if mgr:
                mx, my, mw, mh = slot_to_canvas_rect(mgr, monitors, cw, ch)
                c.create_rectangle(mx, my, mx + mw, my + mh,
                                   fill="#1a1a1a", outline=tk_color("text_dim"),
                                   width=1, dash=(4, 3), tags=("mgr_cell",))
                c.create_text(mx + mw // 2, my + mh // 2, text="MGR",
                              fill=tk_color("text_dim"), font=THEME["font_small"],
                              tags=("mgr_cell",))
        except Exception:
            pass

        if not any_drawn:
            c.create_text(cw // 2, ch // 2,
                          text="No windows detected.\nUse Auto Detect or Launch All.",
                          fill=tk_color("text_dim"), font=THEME["font_small"],
                          justify="center")

        # Mode indicator (bottom-right corner)
        mode_text = "AUTO" if self._layout_mode == "auto" else "CUSTOM"
        mode_color = "#44bb44" if self._layout_mode == "auto" else "#ffaa00"
        c.create_text(cw - 4, ch - 4, anchor="se", text=mode_text,
                      fill=mode_color, font=THEME["font_small"])

    # ── Canvas interaction ────────────────────────────────────

    def _canvas_mouse_down(self, event):
        c = event.widget
        self._drag_slot = None
        self._drag_resize = False
        self._drag_canvas = c
        self._mgr_dragging = False

        cw = c.winfo_width()
        ch = c.winfo_height()
        items = c.find_overlapping(event.x - 3, event.y - 3, event.x + 3, event.y + 3)

        for item in items:
            for tag in c.gettags(item):
                if tag.startswith("handle_"):
                    self._drag_slot = int(tag.split("_")[1])
                    self._drag_resize = True
                    return

        for item in items:
            for tag in c.gettags(item):
                if tag.startswith("slot_"):
                    i = int(tag.split("_")[1])
                    slot = self.slots.slot(i)
                    geo = {"x": slot.x, "y": slot.y, "w": slot.w, "h": slot.h}
                    sx, sy, _, _ = slot_to_canvas_rect(geo, self.monitors, cw, ch)
                    self._drag_slot = i
                    self._drag_offset = (event.x - sx, event.y - sy)
                    self._drag_resize = False
                    return

        for item in items:
            for tag in c.gettags(item):
                if tag == "mgr_cell":
                    mgr = self._get_mgr_geo()
                    if mgr:
                        sx, sy, _, _ = slot_to_canvas_rect(mgr, self.monitors, cw, ch)
                        self._mgr_dragging = True
                        self._drag_offset = (event.x - sx, event.y - sy)
                    return

    def _canvas_mouse_drag(self, event):
        if self._drag_slot is None and not self._mgr_dragging:
            return
        c = getattr(self, "_drag_canvas", self.canvas)
        cw = c.winfo_width()
        ch = c.winfo_height()
        monitors = self.monitors

        total_w, total_h, ox, oy = _monitor_bounds(monitors)
        scale_x = total_w / cw
        scale_y = total_h / ch

        if self._mgr_dragging:
            mgr = self._get_mgr_geo()
            if mgr:
                cx = event.x - self._drag_offset[0]
                cy = event.y - self._drag_offset[1]
                nx = ox + int(cx * scale_x)
                ny = oy + int(cy * scale_y)
                nx, ny = self._snap_move(-1, nx, ny, mgr["w"], mgr["h"])
                self._mgr_custom_pos = {**mgr, "x": nx, "y": ny}
                self._enter_custom_mode()
                self._redraw_canvas()
            return

        # Entering custom mode on first drag
        if self._layout_mode == "auto":
            self._enter_custom_mode()

        slot = self.slots.slot(self._drag_slot)

        if self._drag_resize:
            geo = {"x": slot.x, "y": slot.y, "w": slot.w, "h": slot.h}
            sx, sy, _, _ = slot_to_canvas_rect(geo, monitors, cw, ch)
            new_cw = max(20, event.x - sx)
            new_ch = max(20, event.y - sy)
            slot.w = max(100, int(new_cw * scale_x))
            slot.h = max(80, int(new_ch * scale_y))
            slot.w, slot.h = self._snap_resize(self._drag_slot, slot.x, slot.y, slot.w, slot.h)
        else:
            cx = event.x - self._drag_offset[0]
            cy = event.y - self._drag_offset[1]
            slot.x = ox + int(cx * scale_x)
            slot.y = oy + int(cy * scale_y)
            slot.x, slot.y = self._snap_move(self._drag_slot, slot.x, slot.y, slot.w, slot.h)

        self._redraw_canvas()

    def _canvas_mouse_up(self, _event):
        self._drag_slot = None
        if self._mgr_dragging:
            self._mgr_dragging = False
            self.settings["layout"]["mgr_custom_pos"] = self._mgr_custom_pos
            save_settings(self.settings)

    def _canvas_right_click(self, event):
        """Right-click on canvas — show slot context menu."""
        c = event.widget
        items = c.find_overlapping(event.x - 3, event.y - 3, event.x + 3, event.y + 3)
        for item in items:
            for tag in c.gettags(item):
                if tag == "mgr_cell":
                    self._mgr_context_menu_at(event.x_root, event.y_root)
                    return
                if tag.startswith("slot_"):
                    i = int(tag.split("_")[1])
                    self._slot_context_menu_at(i, event.x_root, event.y_root)
                    return

    # ── Slot context menu ─────────────────────────────────────

    def _slot_context_menu(self, index: int, widget):
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height()
        self._slot_context_menu_at(index, x, y)

    def _slot_context_menu_at(self, index: int, x: int, y: int):
        slot = self.slots.slot(index)
        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=tk_color("panel_bg"),
            fg=tk_color("text"),
            activebackground=tk_color("card_bg"),
        )

        menu.add_command(label=f"Slot {index + 1}  [{slot.label}]", state="disabled")
        menu.add_separator()

        if slot.is_assigned:
            menu.add_command(label="Focus Window", command=lambda: slot.focus())
            menu.add_command(
                label="Quit to Desktop", command=lambda: self._quit_slot_desktop(index)
            )
            menu.add_command(
                label="Kill Client", command=lambda: self._kill_slot(index)
            )
            menu.add_command(
                label="Relaunch Client", command=lambda: self._relaunch_slot(index)
            )
            menu.add_command(
                label="Clear Slot (keep process)",
                command=lambda: self._clear_slot(index),
            )
        else:
            menu.add_command(
                label="Assign Window…",
                command=lambda: self._assign_window_dialog(index),
            )
            menu.add_command(
                label="Launch Client Here",
                command=lambda: self._launch_into_slot(index),
            )

        menu.add_separator()
        char_label = slot.character or slot.char_name or "(none)"
        menu.add_command(
            label=f"Character: {char_label}",
            command=lambda: self._pick_slot_character(index),
        )
        prof = slot.role_profile or "(no profile)"
        menu.add_command(
            label=f"Role Profile: {prof}",
            command=lambda: self._pick_role_profile(index),
        )
        if slot.character:
            menu.add_command(
                label="Loop Overrides…",
                command=lambda: self._edit_loop_overrides(index),
            )
        # Manual override: pick role abbreviation directly
        menu.add_command(
            label=f"Set Role: {slot.role or '(none)'}",
            command=lambda: self._pick_slot_role(index),
        )
        menu.add_separator()
        menu.add_command(
            label="Set Login Credentials…", command=lambda: self._set_slot_login(index)
        )
        top_label = "Always on Top: ON  ✓" if slot.stay_on_top else "Always on Top: OFF"
        menu.add_command(
            label=top_label, command=lambda: self._toggle_stay_on_top(index)
        )
        menu.add_separator()
        menu.add_command(
            label="Rename Window Title", command=lambda: self._rename_slot_window(index)
        )

        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # ── Event handlers ────────────────────────────────────────

    def _on_role_change(self, index: int, abbrev: str):
        slot = self.slots.slot(index)
        slot.set_role("" if abbrev == "—" else abbrev)
        self._update_slot_card_color(index)
        self._redraw_canvas()

    def _on_charname_change(self, index: int, name: str):
        self.slots.slot(index).set_char_name(name)

    def _on_slot_account_change(self, index: int):
        """Account changed in the slot card — narrow the character dropdown
        to characters that belong to this account."""
        sf = self.slot_frames[index]
        slot = self.slots.slot(index)
        acct = sf["account_var"].get().strip()

        # Block duplicate account selection across slots
        if acct:
            for i, other_sf in enumerate(self.slot_frames):
                if i == index:
                    continue
                if other_sf["account_var"].get().strip() == acct:
                    self._set_status(
                        f"Account '{acct}' is already assigned to slot {i + 1}"
                    )
                    sf["account_var"].set(slot.username or "")
                    return

        slot.username = acct
        if acct:
            chars = characters_for_account(acct)
        else:
            chars = list_characters()
        sf["char_cb"]["values"] = [""] + chars
        # Clear selection if it doesn't belong to the new account
        cur = sf["char_var"].get()
        if cur and cur not in chars:
            sf["char_var"].set("")
            cur = ""
        # Auto-select first character for this account if nothing is selected
        if acct and chars and not cur:
            sf["char_var"].set(chars[0])
            self._on_slot_character_change(index)
        elif not cur:
            self._on_slot_character_change(index)

    def _on_slot_character_change(self, index: int):
        """Character picked in the slot card — populate slot fields from the
        character profile (role, role_profile, credentials, name)."""
        sf = self.slot_frames[index]
        slot = self.slots.slot(index)
        chosen = sf["char_var"].get().strip()
        if not chosen:
            slot.character = ""
            sf["role_var"].set(slot.role or "—")
            self._redraw_canvas()
            return
        char = load_character(chosen)
        slot.apply_character(char)
        # Reflect into UI
        sf["account_var"].set(slot.username)
        sf["role_var"].set(slot.role or "—")
        self._update_slot_card_color(index)
        self._redraw_canvas()
        self._set_status(
            f"Slot {index + 1} → {chosen}  ({slot.role}/{slot.role_profile or '–'})"
        )

    def _on_layout_change(self):
        """Slider or monitor selector changed — recalculate layout preview."""
        # Update monitor info labels
        labels = self._mon_labels
        if labels:
            main_i = self.main_mon_var.get()
            sec_i = self.sec_mon_var.get()
            if hasattr(self, "_main_mon_info"):
                self._main_mon_info.configure(
                    text=labels[main_i] if main_i < len(labels) else ""
                )
            if hasattr(self, "_sec_mon_info"):
                self._sec_mon_info.configure(
                    text=labels[sec_i] if sec_i < len(labels) else ""
                )

        new_count = self.sec_count_var.get()
        # Forget any assigned slot that is now above the slider limit.
        for i in range(new_count + 1, MAX_SLOTS):
            slot = self.slots.slot(i)
            if slot.is_assigned:
                minimize_window(slot.window_id)
                self.slots.clear_slot(i)

        if self._layout_mode == "auto":
            self._auto_tile(apply=False)
        self._refresh_slot_cards()
        self._redraw_canvas()

    def _on_slots_changed(self):
        """Called by SlotManager when any slot state changes."""
        self.root.after(0, self._refresh_slot_cards)
        self.root.after(0, self._redraw_canvas)
        self.root.after(0, self._update_omit_indicator)

    def _refresh_slot_cards(self):
        """Update all slot card widgets to reflect current slot state."""
        sec_count = self.sec_count_var.get()
        all_chars = list_characters()
        all_accts = list_accounts()
        for i, sf in enumerate(self.slot_frames):
            # Slot 0 = driver (always visible); slots 1..sec_count = visible
            visible = (i == 0) or (i <= sec_count)
            card = sf["card"]
            if not visible:
                card.pack_forget()
                continue
            if not card.winfo_ismapped():
                card.pack(fill="x", pady=2)

            slot = self.slots.slot(i)
            sf["role_var"].set(slot.role or "—")
            # Refresh the dropdown values to reflect added/removed profiles.
            sf["account_cb"]["values"] = [""] + all_accts
            sf["account_var"].set(slot.username)
            chars = (
                characters_for_account(slot.username) if slot.username else all_chars
            )
            sf["char_cb"]["values"] = [""] + chars
            sf["char_var"].set(slot.character or slot.char_name)
            if slot.is_assigned:
                sf["status_var"].set("●")
                sf["card"].configure(
                    highlightbackground=slot_color(slot.role)
                    if slot.role
                    else tk_color("accent")
                )
            else:
                sf["status_var"].set("○")
                sf["card"].configure(highlightbackground=tk_color("slot_border"))

    def _update_slot_card_color(self, index: int):
        sf = self.slot_frames[index]
        slot = self.slots.slot(index)
        color = slot_color(slot.role) if slot.role else tk_color("slot_border")
        sf["card"].configure(highlightbackground=color)

    # ── Layout actions ────────────────────────────────────────

    def _auto_tile(self, apply: bool = False, resize_driver: bool = False):
        """Calculate auto-tile layout and write geometry to slots."""
        main_mon = self.main_mon_var.get()
        sec_mon = self.sec_mon_var.get()
        sec_count = self.sec_count_var.get()
        gap = self.settings["layout"].get("gap_px", 0)

        # Use full physical monitor dimensions — secondary slots are made
        # borderless before resize so Openbox doesn't clip their height.
        monitors = [dict(m) for m in self.monitors]

        if len(monitors) >= 2:
            layout = calculate_layout(
                monitors,
                self.slots.slots,
                secondary_count=sec_count,
                main_monitor=main_mon,
                secondary_monitor=sec_mon,
                gap=gap,
                ar_lock=self.settings["layout"].get("ar_lock", "none"),
            )
        else:
            mon = (
                monitors[0]
                if monitors
                else {"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080, "name": "?"}
            )
            layout = single_monitor_layout(mon, MAX_SLOTS, sec_count, gap, ar_lock=self.settings["layout"].get("ar_lock", "none"))

        apply_layout_to_slots(self.slots.slots, layout)

        if apply:
            self._apply_layout(resize_driver=resize_driver)
        self._redraw_canvas()

    # ── Layout mode ───────────────────────────────────────────

    def _enter_custom_mode(self):
        if self._layout_mode == "custom":
            return
        self._layout_mode = "custom"
        self.settings["layout"]["layout_mode"] = "custom"
        save_settings(self.settings)
        if hasattr(self, "_mode_label"):
            self._mode_label.configure(text="CUSTOM", fg=tk_color("accent2"))
        if hasattr(self, "_reset_auto_btn"):
            self._reset_auto_btn.configure(state="normal")

    def _enter_auto_mode(self):
        self._layout_mode = "auto"
        self.settings["layout"]["layout_mode"] = "auto"
        self._mgr_custom_pos = None
        self.settings["layout"]["mgr_custom_pos"] = None
        save_settings(self.settings)
        if hasattr(self, "_mode_label"):
            self._mode_label.configure(text="AUTO", fg=tk_color("success"))
        if hasattr(self, "_reset_auto_btn"):
            self._reset_auto_btn.configure(state="disabled")
        self._auto_tile(apply=False)

    def _reset_to_auto(self):
        self._enter_auto_mode()

    # ── Snap helpers ──────────────────────────────────────────

    def _snap(self, val, targets):
        if not targets:
            return val
        thr = self._snap_threshold_var.get()
        best = min(targets, key=lambda t: abs(val - t))
        return best if abs(val - best) <= thr else val

    def _snap_move(self, slot_idx, x, y, w, h):
        if not self._snap_var.get():
            return x, y
        tx, ty = [], []
        for mon in self.monitors:
            tx += [mon["x"], mon["x"] + mon["w"] - w]
            ty += [mon["y"], mon["y"] + mon["h"] - h]
        for i, slot in enumerate(self.slots.slots):
            if i == slot_idx:
                continue
            tx += [slot.x, slot.x + slot.w, slot.x - w, slot.x + slot.w - w]
            ty += [slot.y, slot.y + slot.h, slot.y - h, slot.y + slot.h - h]
        return self._snap(x, tx), self._snap(y, ty)

    def _snap_resize(self, slot_idx, x, y, w, h):
        if not self._snap_var.get():
            return w, h
        tx, ty = [], []
        for mon in self.monitors:
            tx += [mon["x"] + mon["w"]]
            ty += [mon["y"] + mon["h"]]
        for i, slot in enumerate(self.slots.slots):
            if i == slot_idx:
                continue
            tx += [slot.x, slot.x + slot.w]
            ty += [slot.y, slot.y + slot.h]
        new_right = self._snap(x + w, tx)
        new_bottom = self._snap(y + h, ty)
        return max(100, new_right - x), max(80, new_bottom - y)

    # ── MGR geometry ──────────────────────────────────────────

    def _get_mgr_geo(self):
        if self._mgr_custom_pos:
            return self._mgr_custom_pos
        gap = self.settings["layout"].get("gap_px", 0)
        sec_mon_idx = self.settings["layout"].get("secondary_monitor", 1)
        mon_sec = _get_monitor(self.monitors, sec_mon_idx)
        if mon_sec:
            return mgr_cell(mon_sec, self.sec_count_var.get(), gap)
        return None

    # ── Presets ───────────────────────────────────────────────

    def _get_builtin_presets(self):
        monitors = self.monitors or [{"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080, "name": "?"}]
        gap = self.settings["layout"].get("gap_px", 0)
        main_i = self.settings["layout"].get("main_monitor", 0)
        sec_i = self.settings["layout"].get("secondary_monitor", 1)
        result = []

        ar_lock = self.settings["layout"].get("ar_lock", "none")
        if len(monitors) >= 2:
            for sec_count, name in [(5,"Dual: 1+5"),(4,"Dual: 1+4"),(3,"Dual: 1+3"),(2,"Dual: 1+2"),(1,"Dual: 1+1")]:
                geo = calculate_layout(monitors, self.slots.slots, sec_count, main_i, sec_i, gap, ar_lock=ar_lock)
                result.append((name, geo))
            # 2 equal on main + 2 equal on secondary
            mon_main = _get_monitor(monitors, main_i) or monitors[0]
            mon_sec  = _get_monitor(monitors, sec_i)  or monitors[-1]
            geo = [None] * MAX_SLOTS
            for i, cell in enumerate(calculate_grid(mon_main, 2, gap, ar_lock=ar_lock)):
                geo[i] = {**cell, "monitor": main_i}
            for i, cell in enumerate(calculate_grid(mon_sec, 2, gap, ar_lock=ar_lock)):
                geo[i + 2] = {**cell, "monitor": sec_i}
            result.append(("Dual: 2×2", geo))

        mon0 = monitors[0]
        for count, name in [(6,"Single: 6 equal"),(4,"Single: 4 equal"),(3,"Single: 3 equal"),(2,"Single: 2 equal")]:
            # 6-equal fills row by row (1,2,3 / 4,5,6); others fill column by column
            grid = calculate_grid(mon0, count, gap, fill_vertical=(count != 6), ar_lock=ar_lock)
            geo = [None] * MAX_SLOTS
            for i, cell in enumerate(grid):
                if i < MAX_SLOTS:
                    geo[i] = {**cell, "monitor": 0}
            result.append((name, geo))

        for sec_count, name in [(5,"Single: 1 large+5"),(3,"Single: 1 large+3")]:
            geo = single_monitor_layout_large(mon0, sec_count, gap, ar_lock=ar_lock)
            result.append((name, geo))

        return result

    def _refresh_preset_dropdown(self):
        builtin_names = [n for n, _ in self._get_builtin_presets()]
        user_names = list(self.settings.get("layout_presets", {}).keys())
        all_names = builtin_names + (["─── My Presets ───"] if user_names else []) + user_names
        self._preset_combo["values"] = all_names
        cur = self._preset_var.get()
        can_delete = cur and cur in user_names
        if hasattr(self, "_delete_preset_btn"):
            self._delete_preset_btn.configure(state="normal" if can_delete else "disabled")

    def _geo_sec_count(self, geo):
        """Count non-None secondary slots (indices 1+) in a geometry list."""
        return sum(1 for i, g in enumerate(geo) if i > 0 and g is not None)

    def _restore_last_preset(self):
        """On startup: populate dropdown and select the last used preset."""
        self._refresh_preset_dropdown()
        last = self.settings["layout"].get("last_preset", "")
        all_vals = list(self._preset_combo["values"])
        if last and last in all_vals:
            self._preset_var.set(last)
        elif all_vals:
            self._preset_var.set(all_vals[0])
        self._refresh_preset_dropdown()

    def _apply_preset_geo(self, geo, sec_count, mgr_pos=None):
        self._preview_geo = None
        """Apply a geometry list, sync the sec_count slider, minimize extras, move windows.
        If no slots are assigned, runs detection first (without auto-tiling)."""
        needed = sec_count + 1  # driver + secondaries
        if self.slots.count_assigned() < needed:
            self._set_status("Scanning for windows…")
            self.slots.auto_detect(exclude_ids=self._independent_wids)
            for slot in self.slots.assigned_slots():
                set_window_borderless(slot.window_id, True)
                set_stay_on_top(slot.window_id, slot.stay_on_top)
                set_bypass_compositor(slot.window_id)
        apply_layout_to_slots(self.slots.slots, geo)
        self._mgr_custom_pos = mgr_pos
        self.sec_count_var.set(sec_count)
        self._enter_custom_mode()
        self._on_layout_change()          # minimizes/clears slots above sec_count, redraws
        self._apply_layout(resize_driver=True)

    def _on_preset_selected(self):
        self._refresh_preset_dropdown()
        name = self._preset_var.get()
        if not name or name.startswith("─"):
            self._preview_geo = None
            self._redraw_canvas()
            return
        for bname, geo in self._get_builtin_presets():
            if bname == name:
                self._preview_geo = geo
                self._redraw_canvas()
                return
        user = self.settings.get("layout_presets", {})
        if name in user:
            slots_data = user[name].get("slots", [])
            geo = [{"x": g[0], "y": g[1], "w": g[2], "h": g[3], "monitor": 0}
                   if g else None for g in slots_data]
            while len(geo) < MAX_SLOTS:
                geo.append(None)
            self._preview_geo = geo
            self._redraw_canvas()
            return
        self._preview_geo = None
        self._redraw_canvas()

    def _apply_selected_preset(self):
        name = self._preset_var.get()
        if not name or name.startswith("─"):
            return
        for bname, geo in self._get_builtin_presets():
            if bname == name:
                self._apply_preset_geo(geo, self._geo_sec_count(geo))
                self._save_last_preset(name)
                return
        user = self.settings.get("layout_presets", {})
        if name in user:
            slots_data = user[name]["slots"]
            geo = [{"x": g[0], "y": g[1], "w": g[2], "h": g[3], "monitor": 0}
                   if g else None for g in slots_data]
            sec_count = user[name].get("sec_count", self._geo_sec_count(geo))
            self._apply_preset_geo(geo, sec_count, user[name].get("mgr_pos"))
            self._save_last_preset(name)

    def _save_last_preset(self, name: str):
        self.settings["layout"]["last_preset"] = name
        save_settings(self.settings)

    def _save_preset_dialog(self):
        name = simpledialog.askstring("Save Preset", "Preset name:", parent=self.root)
        if not name:
            return
        builtin_names = [n for n, _ in self._get_builtin_presets()]
        if name in builtin_names:
            messagebox.showwarning("Name taken", f"'{name}' is a built-in preset name.", parent=self.root)
            return
        if name in self.settings.get("layout_presets", {}):
            if not messagebox.askyesno("Overwrite?", f"Preset '{name}' already exists. Overwrite?", parent=self.root):
                return
        slots_data = [[s.x, s.y, s.w, s.h] for s in self.slots.slots]
        presets = self.settings.setdefault("layout_presets", {})
        presets[name] = {"slots": slots_data, "mgr_pos": self._mgr_custom_pos,
                         "sec_count": self.sec_count_var.get()}
        save_settings(self.settings)
        self._refresh_preset_dropdown()
        self._preset_var.set(name)

    def _delete_selected_preset(self):
        name = self._preset_var.get()
        builtin_names = [n for n, _ in self._get_builtin_presets()]
        if name in builtin_names or name.startswith("─"):
            return
        presets = self.settings.get("layout_presets", {})
        if name in presets:
            del presets[name]
            save_settings(self.settings)
            self._refresh_preset_dropdown()
            vals = self._preset_combo["values"]
            self._preset_var.set(vals[0] if vals else "")

    def _on_apply_layout_click(self):
        """Apply Layout button handler — recalculates for auto mode and built-in presets."""
        self._preview_geo = None
        if self._layout_mode == "auto":
            self._auto_tile(apply=True, resize_driver=True)
            return
        name = self._preset_var.get()
        for bname, geo in self._get_builtin_presets():
            if bname == name:
                self._apply_preset_geo(geo, self._geo_sec_count(geo))
                return
        self._apply_layout(resize_driver=True)

    def _apply_layout(self, slot_index: int = None, resize_driver: bool = False):
        """Apply current slot x/y/w/h to actual windows (does NOT recalculate positions).
        If slot_index is given, only that slot is processed (used by relaunch).
        resize_driver=True forces winresize on slot 0 (safe after Detect, not during cycles)."""
        assigned = self.slots.assigned_slots()
        if not assigned:
            self._set_status("No windows assigned — nothing to move")
            return
        self._set_status("Applying layout…")
        threading.Thread(
            target=self._apply_layout_thread, args=(slot_index, resize_driver), daemon=True
        ).start()

    def _apply_layout_thread(self, slot_index: int = None, resize_driver: bool = False):



        assigned = self.slots.assigned_slots()
        # When slot_index is set (relaunch), only process that one slot so we
        # don't disturb the running driver or other in-game secondary slots.
        if slot_index is not None:
            assigned = [s for s in assigned if s.index == slot_index]
        secondary = [s for s in assigned if s.index > 0]

        # Phase 0: un-minimize any iconified windows before touching state.
        # xdotool windowmove silently no-ops on minimized windows, so restore
        # them first. remove,hidden is harmless on already-visible windows.
        for slot in assigned:
            restore_window(slot.window_id)
        if any(True for _ in assigned):
            time.sleep(0.2)

        # Phase 1: remove fullscreen/maximize from the target slots BEFORE
        # checking frame extents. A fullscreen window reports ext=(0,0,0,0)
        # even though it will get a title bar when un-fullscreened. Only run
        # for secondary slots — don't kick the driver out of fullscreen.
        for slot in secondary:
            restore_window(slot.window_id)

        # For the driver slot specifically (slot_index == 0), also remove
        # fullscreen so it can be repositioned after a relaunch.
        if slot_index == 0:
            driver = next((s for s in assigned if s.index == 0), None)
            if driver:
                restore_window(driver.window_id)

        # Let Openbox process the state changes before reading frame extents.
        time.sleep(0.3)

        # Phase 2 (serial): strip decorations from target slots. Secondary
        # slots and a relaunched driver all need borderless applied here since
        # _auto_detect is not called on the relaunch path.
        # Per LESSONS: per-slot 0.3s, not batched.
        for slot in assigned:
            set_bypass_compositor(slot.window_id)
            ext = get_frame_extents(slot.window_id)
            if ext[0] + ext[1] + ext[2] + ext[3] > 0:
                set_window_borderless(slot.window_id, True)
                slot.borderless = True
                time.sleep(0.3)

        # Phase 3 (parallel): resize + move target slots.
        def _move_one(slot):
            if sys.platform == "win32":
                move_resize_window(slot.window_id, slot.x, slot.y, slot.w, slot.h)
            else:
                # Wine/X11: use winresize to fight Openbox decoration + xdotool to position.
                # Different Wine prefixes have independent wineservers — concurrent is safe.
                ext = get_frame_extents(slot.window_id)
                ob_w = ext[0] + ext[1]
                ob_h = ext[2] + ext[3]
                rw = slot.w + WIN32_NC_W - ob_w
                rh = slot.h + WIN32_NC_H - ob_h
                # Skip winresize for driver during normal Apply Layout — driver is already
                # fullscreen and winresize during a cycle causes jumping.
                # Run for driver on relaunch (slot_index == 0) or after Detect (resize_driver).
                if slot.index != 0 or slot_index == 0 or resize_driver:
                    winresize_wine_window(slot.index, ENB_WINDOW_TITLE, slot.x, slot.y, rw, rh)
                _run(
                    ["xdotool", "windowmove", str(slot.window_id), str(slot.x), str(slot.y)]
                )

        threads = [
            threading.Thread(target=_move_one, args=(s,), daemon=True) for s in assigned
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Phase 4 (serial): if Openbox re-decorated a slot during the move
        # (strut-overlap edge case), re-apply borderless and re-move.
        time.sleep(0.2)
        for slot in assigned:
            ext = get_frame_extents(slot.window_id)
            if ext[0] + ext[1] + ext[2] + ext[3] > 0:
                set_window_borderless(slot.window_id, True)
                time.sleep(0.3)
                reposition_window(slot.window_id, slot.x, slot.y)

        for slot in assigned:
            if slot.window_id is None:
                continue
            set_stay_on_top(slot.window_id, slot.stay_on_top)
            raise_window(slot.window_id)

        if self._compact_mode and self._mgr_custom_pos:
            mgr = self._mgr_custom_pos
            self.root.after(0, lambda: self.root.geometry(
                f"{mgr['w']}x{mgr['h']}+{mgr['x']}+{mgr['y']}"))
        self.root.after(0, lambda: self._set_status("Layout applied ✓"))

    # ── Auto detect ───────────────────────────────────────────

    def _auto_detect(self):
        self._set_status("Scanning for EnB clients…")
        new_count, changes = self.slots.auto_detect(exclude_ids=self._independent_wids)


        for slot in self.slots.assigned_slots():
            set_window_borderless(slot.window_id, True)
            set_stay_on_top(slot.window_id, slot.stay_on_top)
            set_bypass_compositor(slot.window_id)
        total = self.slots.count_assigned()
        if new_count > 0:
            msg = f"Found {new_count} new client(s). Total: {total}"
        elif changes > 0:
            msg = f"Reassigned {changes} client(s) to correct slots. Total: {total}"
        else:
            msg = f"No changes. Total assigned: {total}"
        self._set_status(msg)
        self._refresh_slot_cards()
        self._redraw_canvas()
        # Tile whenever any assignment changed — new or reassigned.
        # resize_driver=True so slot 0 gets winresized if it ended mid-cycle at secondary size.
        if changes > 0:
            if self._layout_mode == "auto":
                self._auto_tile(apply=True, resize_driver=True)
            else:
                name = self._preset_var.get()
                for bname, geo in self._get_builtin_presets():
                    if bname == name:
                        apply_layout_to_slots(self.slots.slots, geo)
                        break
                self._apply_layout(resize_driver=True)

    # ── Quit to Desktop / Kill All ────────────────────────────

    def _quit_to_desktop_all(self):
        if not messagebox.askyesno(
            "Quit to Desktop", "Send Quit to Desktop to all running clients?"
        ):
            return
        self._set_status("Quitting to desktop…")
        threading.Thread(target=self._quit_to_desktop_thread, daemon=True).start()

    def _quit_to_desktop_thread(self):
        # Sequential, highest slot first — each slot needs undivided focus.
        assigned = [
            (i, self.slots.slot(i))
            for i in range(MAX_SLOTS - 1, -1, -1)
            if self.slots.slot(i).is_assigned
        ]

        for i, _ in assigned:
            self._relaunching.add(
                i
            )  # suppress crash detection while we intentionally quit
        # Interrupt any in-progress autologin/char-select thread so it releases
        # _autologin_lock before we return. Without this, the lock stays held
        # through the char-select sleep and blocks the next login attempt.
        self._abort_flag.set()
        # Iconify the manager so it doesn't block the click on game windows.
        self.root.after(0, self.root.iconify)
        time.sleep(0.5)
        try:
            count = 0
            for i, slot in assigned:
                self.root.after(
                    0, lambda n=i + 1: self._set_status(f"Quitting slot {n}…")
                )
                if slot.pid:
                    self._quit_slot_gracefully(slot)
                    count += 1
                self.slots.clear_slot(i)

            for i in range(MAX_SLOTS):
                self.slots.clear_slot(i)
        finally:
            for i in range(MAX_SLOTS):
                self._relaunching.discard(i)
            self._abort_flag.clear()
            self.root.after(0, self.root.deiconify)

        self.root.after(0, self._refresh_slot_cards)
        self.root.after(0, self._redraw_canvas)
        self.root.after(
            0, lambda: self._set_status(f"Quit to desktop sent to {count} client(s)")
        )

    def _kill_all_clients(self):
        if not messagebox.askyesno(
            "Kill All", "Force-kill all running client processes immediately?"
        ):
            return
        self._set_status("Killing all clients…")
        threading.Thread(target=self._kill_all_thread, daemon=True).start()

    def _kill_all_thread(self):
        self._abort_flag.set()
        for i in range(MAX_SLOTS):
            self._relaunching.add(
                i
            )  # suppress crash detection while we intentionally kill
        try:
            count = 0
            for i in range(MAX_SLOTS):
                slot = self.slots.slot(i)
                if slot.is_assigned:
                    slot.kill()
                    count += 1
                self.slots.clear_slot(i)

            # Also kill unassigned EnB windows (loading/never detected)
            my_pid = os.getpid()
            for w in find_enb_windows():
                pid = w["pid"]
                if pid != my_pid and is_enb_client_pid(pid):
                    kill_window_process(pid)
                    count += 1

            # Comprehensive pkill sweep — catches net7proxy, launcher, etc.
            # with no assigned window

            kill_all_enb_processes()

            self.root.after(0, self._refresh_slot_cards)
            self.root.after(0, self._redraw_canvas)
        finally:
            # Delay clearing _relaunching so monitor crash callbacks queued on
            # the main thread (fired by the OFFLINE state transitions) still see
            # these slots as intentionally killed and skip auto-relaunch.
            # 12s > the 6s liveness check interval.
            self.root.after(12000, lambda: [self._relaunching.discard(i) for i in range(MAX_SLOTS)])
            self._abort_flag.clear()
        self.root.after(
            0, lambda: self._set_status(f"Killed {count} client(s) — all slots cleared")
        )

    # ── Auto Login ────────────────────────────────────────────

    def _set_theme(self, name: str):
        self.settings["theme"] = name
        save_settings(self.settings)
        messagebox.showinfo(
            "Theme Changed",
            f"Theme set to '{name}'.\nRestart the app to apply.",
        )

    def _on_autologin_toggle(self):
        self.settings["autologin_on_launch"] = bool(self.autologin_var.get())

    def _on_auto_relaunch_toggle(self):
        self.settings["auto_relaunch"] = bool(self.auto_relaunch_var.get())

    def _on_zone_freeze_toggle(self):
        self.settings["zone_freeze_enabled"] = bool(self.zone_freeze_var.get())

    def _get_slot_monitor_state(self, slot) -> str:
        """Read this slot's current state ("IN GAME", "CHAR SELECT", etc.) from
        logs/monitor_state.json. Returns "" if unavailable."""
        try:
            ms_path = os.path.join(os.path.dirname(__file__), "logs", "monitor_state.json")
            if os.path.exists(ms_path):
                import json as _json
                with open(ms_path) as f:
                    ms = _json.load(f)
                return ms.get("slots", {}).get(str(slot.index + 1), {}).get("state", "")
        except Exception:
            pass
        return ""

    def _auto_login(self):
        slots_with_creds = [s for s in self.slots.assigned_slots() if s.username]
        already_in_game = [s for s in slots_with_creds if self._get_slot_monitor_state(s) == "IN GAME"]
        slots_with_creds = [s for s in slots_with_creds if s not in already_in_game]
        skip_note = ""
        if already_in_game:
            skipped = ", ".join(f"slot {s.index + 1}" for s in already_in_game)
            skip_note = f" (skipping already in-game: {skipped})"
        if not slots_with_creds:
            self._set_status(
                "Auto-login: all credentialed slots already in-game, nothing to do"
                if already_in_game else
                "No slots have login credentials set (right-click → Set Login Credentials)"
            )
            return
        self._abort_flag.clear()
        self._set_status(f"Auto-login: {len(slots_with_creds)} slot(s)…{skip_note}")
        threading.Thread(
            target=self._auto_login_thread, args=(slots_with_creds,), daemon=True
        ).start()

    def _auto_login_thread(self, slots, do_char_select: bool = True):
        """Run username/password login, then (if do_char_select) click the
        assigned character's button on the character-select screen and click
        Accept. do_char_select can be turned off for the legacy flow."""
        with self._autologin_lock:
            try:
                self._auto_login_thread_body(slots, do_char_select)
            except Exception as e:
                self.root.after(
                    0, lambda e=e: self._set_status(f"Auto-login error: {e}")
                )

    def _auto_login_thread_body(self, slots, do_char_select: bool = True):
        al = self.settings.get("autologin", {})
        cs_cfg = self.settings.get("char_select", {})
        cs_positions  = cs_cfg.get("positions", [[0.0, 0.0]] * 5)
        cs_settle     = cs_cfg.get("settle_ms", 6000) / 1000.0
        cs_accept_d   = cs_cfg.get("accept_delay_ms", 1200) / 1000.0
        cs_btn_ready  = cs_cfg.get("button_ready_ms", 1200) / 1000.0
        # first_slot_wait = al.get("first_slot_login_wait_s", 9.0)
        # Intended to make the single-slot login pre-wait configurable (currently
        # hardcoded to 5.0s single / 1.0s multi at the pre_wait line below).

        # Pct coords — one set covers all window sizes
        login_x_pct = al.get("login_x_pct", 0.0)
        login_y_pct = al.get("login_y_pct", 0.0)

        def activate_and_ready(wid):
            # Raise first so the window is on top in Z-order before we click.
            # activate_window gives keyboard focus but does not guarantee Z-order;
            # other slots raised by _apply_layout_thread may be on top otherwise.
            raise_window(wid)
            activate_window(wid)
            # Poll until the WM confirms the window is active — activation may
            # be requested asynchronously (race condition, worst on the first slot).
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if get_active_window_id() == wid:
                    break
                time.sleep(0.1)
            time.sleep(0.2)

        os.makedirs(LOG_DIR, exist_ok=True)
        login_dbg_path = os.path.join(LOG_DIR, "enbmb-login-debug.log")

        with open(login_dbg_path, "a", encoding="utf-8") as ldbg:

            def llog(msg):
                ts = (
                    time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
                )
                line = f"[{ts}] {msg}"
                print(line)
                ldbg.write(line + "\n")
                ldbg.flush()

            def click_abs(ax, ay):
                llog(f"    click ({ax},{ay})")
                click_at(ax, ay)

            for slot_i, slot in enumerate(slots):
                if self._abort_flag.is_set():
                    self.root.after(0, lambda: self._set_status("Auto-login aborted"))
                    return
                win = get_window_by_id(slot.window_id)
                wx = win["x"] if win else slot.x
                wy = win["y"] if win else slot.y
                ww = win["w"] if win else slot.w
                wh = win["h"] if win else slot.h
                llog(
                    f"=== login slot {slot.index + 1} wid={slot.window_id} base=({wx},{wy}) size=({ww},{wh})"
                )
                llog(
                    f"  login_abs=({wx + login_x_pct*ww:.0f},{wy + login_y_pct*wh:.0f})"
                )
                self.root.after(
                    0,
                    lambda n=slot.index + 1: self._set_status(f"Auto-login: slot {n}…"),
                )
                if self._abort_flag.is_set():
                    self.root.after(0, lambda: self._set_status("Auto-login aborted"))
                    return
                activate_and_ready(slot.window_id)
                aw = get_active_window_id()
                llog(f"  active after ready: {aw!r} (want {slot.window_id!r})")
                pre_wait = 5.0 if len(slots) == 1 else 1.0
                llog(f"  waiting {pre_wait}s for login screen to settle")
                time.sleep(pre_wait)
                # Wine windows don't reliably move keyboard focus on click.
                # Tab navigation from the default password-field focus is the
                # only reliable way to reach each field.
                # Tab order: password → login button → username → password.
                llog(f"  tab 1 (password -> login button)")
                key_to_focused("Tab")
                time.sleep(0.2)
                llog(f"  tab 2 (login button -> username)")
                key_to_focused("Tab")
                time.sleep(0.2)
                llog(f"  type username ({len(slot.username)} chars)")
                type_to_focused(slot.username)
                time.sleep(0.2)
                llog(f"  tab 3 (username -> password)")
                key_to_focused("Tab")
                time.sleep(0.2)
                llog(f"  type password ({len(slot.password)} chars)")
                type_to_focused(slot.password)
                time.sleep(0.2)
                # Re-read geometry at click time — window may have moved during
                # the pre_wait (layout thread or net7proxy restart).
                win2 = get_window_by_id(slot.window_id)
                if win2:
                    wx2, wy2, ww2, wh2 = win2["x"], win2["y"], win2["w"], win2["h"]
                else:
                    wx2, wy2, ww2, wh2 = wx, wy, ww, wh
                cx = int(wx2 + login_x_pct * ww2)
                cy = int(wy2 + login_y_pct * wh2)
                llog(f"  geometry at click: base=({wx2},{wy2}) size=({ww2},{wh2})")
                wid_at = get_mouse_position()
                llog(f"  click login ({cx},{cy})  mouse pos before move: {wid_at!r}")
                click_abs(cx, cy)
                wid_at2 = get_mouse_position()
                llog(f"  mouse pos after click: {wid_at2!r}  (target={slot.window_id})")
                time.sleep(0.15)
                llog(f"  login sequence done")

        if not do_char_select:
            self.root.after(0, lambda: self._set_status("Auto-login complete"))
            return

        if self._abort_flag.is_set():
            self.root.after(0, lambda: self._set_status("Auto-login aborted"))
            return

        # Character-select pass: wait for char-select screen to load, then
        # click each slot's character button and Accept.
        self.root.after(
            0,
            lambda: self._set_status(
                f"Waiting {int(cs_settle)}s for char-select screens…"
            ),
        )
        if self._abortable_sleep(cs_settle):
            self.root.after(0, lambda: self._set_status("Auto-login aborted"))
            return

        os.makedirs(LOG_DIR, exist_ok=True)
        dbg_path = os.path.join(LOG_DIR, "enbmb-charselect-debug.log")
        with open(dbg_path, "w", encoding="utf-8") as dbg:

            def log(msg):
                ts = (
                    time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
                )
                line = f"[{ts}] {msg}"
                print(line)
                dbg.write(line + "\n")
                dbg.flush()

            log(f"char-select pass: {len(slots)} slot(s)")

            for slot in slots:
                if self._abort_flag.is_set():
                    log("abort flag set — stopping char-select")
                    self.root.after(0, lambda: self._set_status("Auto-login aborted"))
                    return
                win = get_window_by_id(slot.window_id)
                wx = win["x"] if win else slot.x
                wy = win["y"] if win else slot.y
                ww = win["w"] if win else slot.w
                wh = win["h"] if win else slot.h
                log(
                    f"--- slot {slot.index + 1} wid={slot.window_id} "
                    f"base=({wx},{wy}) size=({ww},{wh}) char={slot.character!r} "
                    f"char_name={slot.char_name!r}"
                )
                char_key = slot.character or slot.char_name
                if not char_key:
                    log("  SKIP: no char_key")
                    continue
                try:
                    char = load_character(char_key)
                except Exception as e:
                    log(f"  SKIP: load_character({char_key!r}) failed: {e}")
                    continue
                cs_pos = char.get("char_select_pos", 0)
                accept_x = int(wx + login_x_pct * ww)
                accept_y = int(wy + login_y_pct * wh)
                log(
                    f"  cs_pos={cs_pos} accept=({accept_x},{accept_y}) "
                    f"positions len={len(cs_positions)}"
                )

                self.root.after(
                    0,
                    lambda n=slot.index + 1, k=char_key: self._set_status(
                        f"Char-select: slot {n} → {k}"
                    ),
                )

                log(f"  activate_and_ready wid={slot.window_id}")
                activate_and_ready(slot.window_id)
                aw = get_active_window_id()
                log(f"  active after ready: {aw!r} (want {slot.window_id})")
                time.sleep(max(0, cs_btn_ready - 1.0))

                if cs_pos and 1 <= cs_pos <= len(cs_positions):
                    xp, yp = cs_positions[cs_pos - 1]
                    cx = int(wx + xp * ww)
                    cy = int(wy + yp * wh)
                    log(f"  char-btn pos{cs_pos}: abs=({cx},{cy})")
                    click_at(cx, cy)
                    log(f"  waiting {cs_accept_d}s before accept")
                    time.sleep(cs_accept_d)

                    log(f"  accept btn: abs=({accept_x},{accept_y})")
                    click_at(accept_x, accept_y)
                    time.sleep(0.2)
                else:
                    log(
                        f"  SKIP accept: cs_pos={cs_pos} not valid for positions len {len(cs_positions)}"
                    )

            log("char-select pass complete")

        self.root.after(
            0, lambda: self._set_status(f"Auto-login complete ✓ — debug: {dbg_path}")
        )

    def _set_slot_login(self, index: int):
        slot = self.slots.slot(index)
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Login — Slot {index + 1} ({slot.label})")
        dlg.configure(bg=tk_color("bg"))
        dlg.geometry("320x160")
        dlg.grab_set()
        dlg.resizable(False, False)
        _center_on_parent(dlg, self.root)

        tk.Label(
            dlg,
            text="Username:",
            bg=tk_color("bg"),
            fg=tk_color("text"),
            font=THEME["font_main"],
        ).grid(row=0, column=0, sticky="e", padx=8, pady=8)
        user_var = tk.StringVar(value=slot.username)
        tk.Entry(
            dlg,
            textvariable=user_var,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_main"],
            insertbackground="white",
            width=22,
        ).grid(row=0, column=1, padx=8)

        tk.Label(
            dlg,
            text="Password:",
            bg=tk_color("bg"),
            fg=tk_color("text"),
            font=THEME["font_main"],
        ).grid(row=1, column=0, sticky="e", padx=8)
        pass_var = tk.StringVar(value=slot.password)
        tk.Entry(
            dlg,
            textvariable=pass_var,
            show="*",
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_main"],
            insertbackground="white",
            width=22,
        ).grid(row=1, column=1, padx=8)

        def save():
            slot.username = user_var.get()
            slot.password = pass_var.get()
            dlg.destroy()

        tk.Button(
            dlg,
            text="Save",
            command=save,
            bg=tk_color("success"),
            fg="white",
            font=THEME["font_main"],
            relief="flat",
            padx=16,
        ).grid(row=2, column=0, columnspan=2, pady=14)

    # ── Always-on-top ─────────────────────────────────────────

    def _toggle_stay_on_top(self, index: int):
        slot = self.slots.slot(index)
        slot.stay_on_top = not slot.stay_on_top
        if slot.is_assigned:
            set_stay_on_top(slot.window_id, slot.stay_on_top)
        state = "ON" if slot.stay_on_top else "OFF"
        self._set_status(f"Slot {index + 1} always-on-top: {state}")

    def _toggle_stay_on_top_all(self):
        assigned = self.slots.assigned_slots()
        if not assigned:
            self._set_status("No slots assigned")
            return
        all_on = all(s.stay_on_top for s in assigned)
        enable = not all_on
        for slot in assigned:
            slot.stay_on_top = enable
            set_stay_on_top(slot.window_id, enable)
        self._refresh_slot_cards()
        state = "ON" if enable else "OFF"
        self._set_status(f"Always-on-top ALL: {state}")
        if enable and not self._compact_mode:
            self._toggle_compact()

    # ── Compact mode ──────────────────────────────────────────

    def _build_compact_view(self):
        """Build the compact view frame (swaps with self.pane when compact mode active)."""
        self._compact_view_frame = tk.Frame(self.root, bg=tk_color("bg"))

        # ── Canvas ──────────────────────────────────────────────
        canvas_outer = tk.Frame(self._compact_view_frame, bg=tk_color("bg"))
        canvas_outer.pack(fill="x", padx=2, pady=(2, 0))

        self._compact_canvas = tk.Canvas(
            canvas_outer,
            bg="#0d0d1a",
            height=160,
            highlightthickness=1,
            highlightbackground=tk_color("slot_border"),
            cursor="crosshair",
        )
        self._compact_canvas.pack(fill="x")
        self._compact_canvas.bind("<Configure>", self._on_compact_canvas_configure)
        self._compact_canvas.bind("<ButtonPress-1>", self._canvas_mouse_down)
        self._compact_canvas.bind("<B1-Motion>", self._canvas_mouse_drag)
        self._compact_canvas.bind("<ButtonRelease-1>", self._canvas_mouse_up)
        self._compact_canvas.bind("<Button-3>", self._canvas_right_click)

        # ── Body (plain frame — content fits without scrolling) ──
        inner = tk.Frame(self._compact_view_frame, bg=tk_color("panel_bg"))
        inner.pack(fill="x")

        # ── Profile row ─────────────────────────────────────────
        prof = tk.Frame(inner, bg=tk_color("panel_bg"), padx=4, pady=3)
        prof.pack(fill="x")
        self._compact_profile_combo = ttk.Combobox(
            prof,
            textvariable=self.profile_var,
            values=list_profiles(),
            width=14,
            state="readonly",
            font=THEME["font_small"],
        )
        self._compact_profile_combo.pack(side="left")
        self._compact_profile_combo.bind(
            "<<ComboboxSelected>>",
            lambda _: self._load_profile(self.profile_var.get()),
        )
        for text, cmd, bg, fg in [
            ("Layout",     lambda: self._apply_layout(resize_driver=True), tk_color("card_bg"), tk_color("accent2")),
            ("Detect",     self._auto_detect,        tk_color("card_bg"), tk_color("text")),
            ("Launch All", self._launch_all_clients, tk_color("success"), "white"),
        ]:
            tk.Button(prof, text=text, command=cmd,
                      bg=bg, fg=fg,
                      font=THEME["font_small"], relief="flat",
                      padx=6, pady=1).pack(side="right", padx=2)

        tk.Frame(inner, bg=tk_color("slot_border"), height=1).pack(fill="x")

        # ── Loop buttons (4 per row) ─────────────────────────────
        loops_hdr = tk.Frame(inner, bg=tk_color("panel_bg"), padx=4)
        loops_hdr.pack(fill="x")
        compact_gear = tk.Button(
            loops_hdr, text="⚙",
            command=self._open_button_visibility_editor,
            bg=tk_color("panel_bg"), fg=tk_color("text_dim"),
            font=THEME["font_small"], relief="flat", padx=4,
        )
        compact_gear.pack(side="right")
        ToolTip(compact_gear, "Show/hide buttons for this view mode")

        self._compact_loop_frame = tk.Frame(inner, bg=tk_color("panel_bg"), padx=4, pady=3)
        self._compact_loop_frame.pack(fill="x")
        self._compact_loop_specs = [
            ["c_combat",      "Combat",                lambda: self._start_loop("combat"), tk_color("accent"),   "white"],
            ["c_debuff",      "Debuff",                lambda: self._start_loop("debuff"), tk_color("card_bg"),  tk_color("accent2")],
            ["c_buff",        "Buff",                  lambda: self._start_loop("buff"),   tk_color("card_bg"),  tk_color("accent")],
            ["c_heal",        "Heal",                  lambda: self._start_loop("heal"),   tk_color("card_bg"),  tk_color("text")],
            ["c_energy",      "Energy",                self._start_energy_loop,            tk_color("card_bg"),  tk_color("accent2")],
            ["c_daimyo",      "Daimyo",                self._start_daimyo_action,          tk_color("card_bg"),  tk_color("accent")],
            ["c_daimyo_mode", self._daimyo_mode_text(), self._toggle_daimyo_mode,           tk_color("card_bg"),  tk_color("text_dim")],
            ["c_stop",        "■ Stop",                self._stop_loop,                    tk_color("danger"),   "white"],
        ]
        self._rebuild_compact_loop_buttons()

        tk.Frame(inner, bg=tk_color("slot_border"), height=1).pack(fill="x")

        # ── Utility buttons (3-column grid, rebuilt on visibility change)
        self._compact_util_frame = tk.Frame(inner, bg=tk_color("panel_bg"), padx=4, pady=3)
        self._compact_util_frame.pack(fill="x")
        self._compact_util_specs = [
            ("c_invite",       "Invite",       self._run_invite,             tk_color("card_bg"), tk_color("text")),
            ("c_reform",       "Reform",       self._run_reform,             tk_color("card_bg"), tk_color("text")),
            ("c_autologin",    "Auto Login",   self._auto_login,             tk_color("card_bg"), tk_color("text")),
            ("c_top_all",      "Top All",      self._toggle_stay_on_top_all, tk_color("card_bg"), tk_color("text")),
            ("c_quit_desktop", "Quit Desktop", self._quit_to_desktop_all,    tk_color("warning"),  "white"),
            ("c_kill_all",     "Kill All",     self._kill_all_clients,       tk_color("danger"),   "white"),
        ]
        self._rebuild_compact_util_buttons()

        tk.Frame(inner, bg=tk_color("slot_border"), height=1).pack(fill="x")

        # ── Checkboxes + expand ──────────────────────────────────
        bottom = tk.Frame(inner, bg=tk_color("panel_bg"), padx=4, pady=3)
        bottom.pack(fill="x")
        for text, var, cmd in [
            ("Autologin on Launch All", self.autologin_var,     self._on_autologin_toggle),
            ("Auto-relaunch on crash",  self.auto_relaunch_var, self._on_auto_relaunch_toggle),
            ("Zone freeze detection",   self.zone_freeze_var,   self._on_zone_freeze_toggle),
        ]:
            tk.Checkbutton(bottom, text=text, variable=var, command=cmd,
                           bg=tk_color("panel_bg"), fg=tk_color("text"),
                           selectcolor=tk_color("card_bg"),
                           activebackground=tk_color("panel_bg"),
                           font=THEME["font_small"], anchor="w").pack(anchor="w")
        tk.Button(bottom, text="⬆ Expand", command=self._toggle_compact,
                  bg=tk_color("card_bg"), fg=tk_color("accent2"),
                  font=THEME["font_small"], relief="flat", pady=2
                  ).pack(fill="x", pady=(4, 0))

        tk.Label(bottom, textvariable=self.status_var,
                 bg=tk_color("bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"], anchor="w", padx=2
                 ).pack(fill="x", pady=(2, 0))

    def _rebuild_compact_loop_buttons(self):
        """Rebuild the compact loop button grid respecting compact_ui_buttons visibility."""
        for w in self._compact_loop_frame.winfo_children():
            w.destroy()
        vis = self.settings.get("compact_ui_buttons", {})
        for col in range(4):
            self._compact_loop_frame.columnconfigure(col, weight=1)
        j = 0
        for key, text, cmd, bg, fg in self._compact_loop_specs:
            if not vis.get(key, True):
                continue
            tk.Button(
                self._compact_loop_frame, text=text, command=cmd, bg=bg, fg=fg,
                font=THEME["font_small"], relief="flat", pady=3,
            ).grid(row=j // 4, column=j % 4, sticky="ew", padx=1, pady=1)
            j += 1

    def _rebuild_compact_util_buttons(self):
        """Rebuild the compact utility button grid respecting compact_ui_buttons visibility."""
        for w in self._compact_util_frame.winfo_children():
            w.destroy()
        vis = self.settings.get("compact_ui_buttons", {})
        for col in range(3):
            self._compact_util_frame.columnconfigure(col, weight=1)
        j = 0
        for key, text, cmd, bg, fg in self._compact_util_specs:
            if not vis.get(key, True):
                continue
            tk.Button(
                self._compact_util_frame, text=text, command=cmd, bg=bg, fg=fg,
                font=THEME["font_small"], relief="flat", pady=3,
            ).grid(row=j // 3, column=j % 3, sticky="ew", padx=1, pady=1)
            j += 1

    def _on_compact_canvas_configure(self, event):
        """Maintain aspect ratio for the compact canvas."""

        monitors = self.monitors or [{"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080}]
        total_w, total_h, _, _ = _monitor_bounds(monitors)
        if total_w > 0 and event.width > 10:
            correct_h = max(80, int(event.width * total_h / total_w))
            self._compact_canvas.configure(height=correct_h)
        self._draw_on_canvas(self._compact_canvas)

    def _toggle_compact(self):
        if self._compact_mode:
            self._compact_view_frame.pack_forget()
            self.pane.pack(fill="both", expand=True, padx=4, pady=4)
            self.root.minsize(900, 560)
            self.root.geometry(self._pre_compact_geometry)
            self._compact_mode = False
            self.root.after(50, lambda: set_window_borderless(get_toplevel_hwnd(self.root.winfo_id()), False))
            self._set_status("Manager restored")
            return




        gap      = self.settings["layout"].get("gap_px", 0)
        sec_mon  = self.settings["layout"].get("secondary_monitor", 1)
        sec_count = self.sec_count_var.get()

        # self.monitors already has the taskbar reservation applied (see __init__).
        monitors = self.monitors

        mon = _get_monitor(monitors, sec_mon) or (
            monitors[0] if monitors else {"index": 0, "x": 0, "y": 0, "w": 1920, "h": 1080}
        )
        cells = calculate_grid(mon, sec_count + 1, gap)

        self._pre_compact_geometry = self.root.geometry()
        self.pane.pack_forget()
        self._compact_view_frame.pack(fill="both", expand=True)
        self.root.minsize(0, 0)

        if cells:
            cell = cells[-1]
        else:
            cell = {"x": 0, "y": 0, "w": 640, "h": 540}
        if self._mgr_custom_pos:
            cell = self._mgr_custom_pos
        self.root.geometry(f"{cell['w']}x{cell['h']}+{cell['x']}+{cell['y']}")

        self._compact_mode = True
        self._compact_profile_combo.configure(values=list_profiles())
        self.root.after(100, lambda: self._draw_on_canvas(self._compact_canvas))

        def _finish_compact_borderless():
            set_window_borderless(get_toplevel_hwnd(self.root.winfo_id()), True)
            if sys.platform == "win32":
                # Removing the title bar frees up the height it was occupying —
                # re-apply the cell geometry so content (incl. the Expand button
                # at the bottom) isn't pushed past the cell's visible bounds.
                self.root.after(
                    50,
                    lambda: self.root.geometry(f"{cell['w']}x{cell['h']}+{cell['x']}+{cell['y']}"),
                )

        self.root.after(150, _finish_compact_borderless)
        self._set_status("Compact — click Expand to restore")

    # ── Slot management ───────────────────────────────────────

    def _quit_slot_gracefully(self, slot) -> bool:
        """Focus window, press Escape, click Quit to Desktop. Returns True if window closed."""
        # Capture mutable slot fields up front — parallel threads may clear
        # slot.pid / slot.window_id mid-function via unassign().
        pid = slot.pid
        wid = slot.window_id
        if not pid or not wid:
            return False

        # Get actual window geometry from X11 — slot values may be stale.
        win = get_window_by_id(wid)
        sx = win["x"] if win else slot.x
        sy = win["y"] if win else slot.y
        sw = win["w"] if win else slot.w
        sh = win["h"] if win else slot.h

        # Check monitor state to detect pre-game screens (login / char select) vs in-game.
        _slot_state = self._get_slot_monitor_state(slot)

        # Quit button as percentage of window size.
        qtd = self.settings.get("quit_to_desktop", {})
        pre_game = _slot_state in ("LOGIN SCREEN", "CHAR SELECT")
        cfg = qtd.get("pre_game" if pre_game else "in_game", {"x_pct": 0.0, "y_pct": 0.0})
        quit_x_pct = cfg.get("x_pct", 0.0)
        quit_y_pct = cfg.get("y_pct", 0.0)

        # Focus the window using the same reliable pattern as autologin.
        raise_window(wid)
        activate_window(wid)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if get_active_window_id() == wid:
                break
            time.sleep(0.1)
        time.sleep(0.2)

        # Escape opens the quit menu at all screens (login, char-select, in-game).
        # Fall back to Alt+F4 only if pre-game coords are unconfigured (0,0).
        if pre_game and quit_x_pct == 0.0 and quit_y_pct == 0.0:
            key_to_focused("alt+F4")
        else:
            key_to_focused("Escape")
            time.sleep(0.6)
            qx = int(sx + quit_x_pct * sw)
            qy = int(sy + quit_y_pct * sh)
            click_at(qx, qy)

        deadline = time.time() + 30.0
        while time.time() < deadline:
            time.sleep(0.5)
            if not pid_exists(pid):
                return True
        return False

    def _quit_slot_desktop(self, index: int):
        """Gracefully quit one slot to desktop — clears it so auto-relaunch won't trigger."""
        slot = self.slots.slot(index)
        if not slot.is_assigned:
            return
        threading.Thread(
            target=self._quit_slot_desktop_thread, args=(index,), daemon=True
        ).start()

    def _quit_slot_desktop_thread(self, index: int):
        slot = self.slots.slot(index)
        self._relaunching.add(
            index
        )  # prevent liveness monitor from treating this as a crash
        try:
            self.root.after(
                0, lambda: self._set_status(f"Slot {index + 1}: quitting to desktop…")
            )
            self._quit_slot_gracefully(slot)
            self.slots.clear_slot(index)
            self.root.after(0, self._refresh_slot_cards)
            self.root.after(0, self._redraw_canvas)
            self.root.after(
                0, lambda: self._set_status(f"Slot {index + 1}: quit to desktop ✓")
            )
        finally:
            self._relaunching.discard(index)

    def _kill_slot(self, index: int):
        slot = self.slots.slot(index)
        if not messagebox.askyesno(
            "Close Client", f"Close the client in slot {index + 1} ({slot.label})?"
        ):
            return
        threading.Thread(
            target=self._kill_slot_thread, args=(index,), daemon=True
        ).start()

    def _kill_slot_thread(self, index: int):
        slot = self.slots.slot(index)
        self._relaunching.add(
            index
        )  # prevent liveness monitor from treating this as a crash
        try:
            if slot.is_assigned and slot.pid:
                closed = self._quit_slot_gracefully(slot)
                if not closed:
                    slot.kill()
            self.slots.clear_slot(index)
            self.root.after(0, self._refresh_slot_cards)
            self.root.after(0, self._redraw_canvas)
            self.root.after(
                0, lambda: self._set_status(f"Slot {index + 1} client closed")
            )
        finally:
            self._relaunching.discard(index)

    def _clear_slot(self, index: int):
        self.slots.clear_slot(index)
        self._set_status(f"Slot {index + 1} cleared")

    def _slot_command(self, index: int) -> str:
        cmds = self.settings.get("slot_commands", [])
        if index < len(cmds) and cmds[index].strip():
            return cmds[index].strip()
        return f"bash ~/.local/bin/enb-slot{index + 1}"

    def _relaunch_slot(self, index: int):
        self._set_status(f"Slot {index + 1}: killing and relaunching…")
        self._relaunching.add(index)
        # Capture on the main thread — reading Tkinter vars from background threads is unsafe.
        self._relaunch_slot_impl(index, bool(self.autologin_var.get()))

    # ── launch-pipeline helpers ──────────────────────────────────────────────

    def _wait_for_eula_window(
        self,
        known_ids: set,
        claimed: set | None = None,
        timeout: float = 60.0,
    ) -> int | None:
        """Poll until a new EnB window (EULA) appears. Returns wid or None."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort_flag.is_set():
                return None
            for w in find_enb_windows():
                if w["id"] not in known_ids and (
                    claimed is None or w["id"] not in claimed
                ):
                    return w["id"]
            time.sleep(0.2)
        return None

    def _dismiss_launcher_if_present(
        self, known_ids: set, timeout: float = 10.0, pre_enter_delay: float = 0.2
    ) -> None:
        """Windows-only: wait for and dismiss the LaunchNet7 launcher before EULA.
        Adds the launcher wid to known_ids so _wait_for_eula_window skips it.

        pre_enter_delay: how long to wait after the launcher window appears
        before pressing Enter. The launcher does a server-status check before
        its "Enter" actually dismisses it — usually fast (cached), but the
        first launch of a session is uncached and needs longer."""
        if sys.platform != "win32":
            return
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort_flag.is_set():
                return
            # The LaunchNet7 launcher window's title doesn't match
            # find_enb_windows()'s title patterns, so look it up by process
            # name instead (ENB_PROCESS_NAMES includes "LaunchNet7.exe").
            for w in find_enb_windows_by_process():
                if w["id"] not in known_ids:
                    launcher_wid = w["id"]
                    known_ids.add(launcher_wid)
                    activate_window(launcher_wid)
                    time.sleep(pre_enter_delay)
                    key_to_focused("space")
                    time.sleep(0.5)
                    return
            time.sleep(0.2)

    def _dismiss_eula_window(
        self, eula_wid: int, activate_first: bool = False
    ) -> None:
        """Dismiss the EULA dialog. activate_first raises the window before sending Space.

        Space, not Return/Enter: if window detection ever misfires and this
        gets sent to an already-in-game window instead of the real EULA
        (e.g. during a crash/relaunch race under raid lag), Return would open
        chat -- and the autologin credentials typed right after would get
        sent as a chat message. Space carries no such risk.
        """
        if sys.platform == "win32":
            activate_window(eula_wid)
            time.sleep(0.2)
            key_to_focused("space")
        else:
            if activate_first:
                _run(["xdotool", "windowactivate", "--sync", str(eula_wid)])
            time.sleep(1.0)
            _run(["xdotool", "key", "--window", str(eula_wid), "space"])
        time.sleep(0.5)

    def _find_login_window(
        self,
        known_ids: set,
        eula_wid: int | None,
        launch_delay: float,
    ) -> tuple[int | None, int | None]:
        """
        Wait launch_delay then find the login window via 3-case fallback:
          1. New window appeared (different wid from EULA)
          2. EULA window reused as login
          3. Window appeared late — retry once after 1 s
        Returns (login_wid, pid) or (None, None).
        """
        time.sleep(launch_delay)
        current_windows = find_enb_windows()
        current_ids = {w["id"] for w in current_windows}

        login_wid = next(
            (w["id"] for w in current_windows if w["id"] not in known_ids), None
        )
        if login_wid is None and eula_wid and eula_wid in current_ids:
            login_wid = eula_wid
        if login_wid is None:
            time.sleep(1.0)
            current_windows = find_enb_windows()
            login_wid = next(
                (w["id"] for w in current_windows if w["id"] not in known_ids), None
            )
        if login_wid is None:
            return None, None
        pid = next(
            (w["pid"] for w in current_windows if w["id"] == login_wid), None
        )
        return login_wid, pid

    # ─────────────────────────────────────────────────────────────────────────

    def _relaunch_slot_thread(self, index: int, do_autologin: bool):
        self._relaunch_lock.acquire()
        try:
            if self._abort_flag.is_set():
                return

            # Capture credentials before clearing the slot.
            username = self.slots.slot(index).username
            known_ids = {s.window_id for s in self.slots.slots if s.is_assigned}

            cmd = self._slot_command(index)
            self.slots.kill_slot(index)
            time.sleep(_RELAUNCH_KILL_WAIT_S)

            if self._abort_flag.is_set():
                return

            pid = launch_enb_client(cmd)
            if not pid:
                self.root.after(
                    0, lambda: self._set_status(f"Slot {index + 1}: launch failed")
                )
                return

            self.root.after(
                0, lambda: self._set_status(f"Slot {index + 1}: waiting for EULA…")
            )

            claimed = {s.window_id for s in self.slots.slots if s.window_id}
            # Same pre-Enter delay as non-first slots in Launch All — pressing
            # Enter before the launcher's server-status check settles makes it
            # just close without launching net7proxy/client.
            self._dismiss_launcher_if_present(known_ids, pre_enter_delay=2.0)
            eula_wid = self._wait_for_eula_window(known_ids, claimed)
            if not eula_wid:
                self.root.after(
                    0, lambda: self._set_status(f"Slot {index + 1}: window not detected")
                )
                return

            self.root.after(
                0, lambda: self._set_status(f"Slot {index + 1}: EULA — dismissing…")
            )
            self._dismiss_eula_window(eula_wid, activate_first=True)

            # Poll for the login window — reuses EULA wid or a new window appears.
            self.root.after(
                0,
                lambda: self._set_status(
                    f"Slot {index + 1}: waiting for login screen…"
                ),
            )
            # X11 can reuse the exact same window ID for the relaunched
            # client (confirmed live: slot 4 got wid=153092100 both before
            # and after a kill+relaunch), which silently defeats an
            # ID-novelty check ("not in known_ids") forever. Match by Wine
            # prefix instead — find_enb_windows() already tags each window
            # with the prefix it belongs to, and that's stable across
            # relaunches regardless of X11 ID reuse.
            expected_prefix = slot_wine_prefix(index)

            login_win = None
            for attempt in range(2):
                if attempt > 0:
                    self.root.after(
                        0,
                        lambda: self._set_status(
                            f"Slot {index + 1}: login window not found — retrying…"
                        ),
                    )
                    # Re-snapshot and re-dismiss in case a launcher/EULA
                    # window appeared late and is blocking the login screen.
                    self._dismiss_launcher_if_present(known_ids, pre_enter_delay=2.0)
                    claimed = {s.window_id for s in self.slots.slots if s.window_id}
                    for w in find_enb_windows():
                        if (w.get("wine_prefix") == expected_prefix
                                or w["id"] not in known_ids) and w["id"] not in claimed:
                            self._dismiss_eula_window(w["id"], activate_first=True)
                    time.sleep(1.0)

                deadline = time.time() + 20.0
                while time.time() < deadline:
                    if self._abort_flag.is_set():
                        return
                    claimed = {s.window_id for s in self.slots.slots if s.window_id}
                    current_windows = find_enb_windows()
                    current_ids = {w["id"] for w in current_windows}
                    login_win = next(
                        (
                            w
                            for w in current_windows
                            if w["id"] not in claimed
                            and w.get("wine_prefix") == expected_prefix
                        ),
                        None,
                    )
                    if login_win is None:
                        login_win = next(
                            (
                                w
                                for w in current_windows
                                if w["id"] not in known_ids
                                and w["id"] not in claimed
                                and w["id"] != eula_wid
                            ),
                            None,
                        )
                    if login_win is None and eula_wid in current_ids:
                        login_win = next(
                            (w for w in current_windows if w["id"] == eula_wid), None
                        )
                    if login_win:
                        break
                    time.sleep(0.2)

                if login_win:
                    break

            if not login_win:
                self.root.after(
                    0,
                    lambda: self._set_status(
                        f"Slot {index + 1}: login window not found — relaunch incomplete, slot left unassigned"
                    ),
                )
                return

            wid = login_win["id"]
            win_pid = login_win.get("pid") or pid
            self.slots.assign_window_to_slot(index, wid, win_pid)

            # Wait for net7proxy to potentially restart and replace the login
            # window with a new wid. If the original window dies and a new one
            # appears, re-assign so autologin uses the correct wid.
            time.sleep(3.5)
            current = find_enb_windows()
            current_ids = {w["id"] for w in current}
            if wid not in current_ids:
                replacement = next(
                    (w for w in current
                     if w["id"] not in known_ids and w["id"] != wid),
                    None,
                )
                if replacement:
                    wid = replacement["id"]
                    win_pid = replacement.get("pid") or win_pid
                    self.slots.assign_window_to_slot(index, wid, win_pid)

            # Update UI immediately so the slot shows as assigned.
            self.root.after(0, self._refresh_slot_cards)
            self.root.after(0, self._redraw_canvas)

            # Run layout synchronously so the window is positioned before
            # autologin clicks — an async layout was racing autologin and
            # producing clicks against stale/wrong geometry (slot 3, 14:27:39).
            self._apply_layout_thread(slot_index=index)

            if do_autologin and username and not self._abort_flag.is_set():
                slot = self.slots.slot(index)
                self.root.after(
                    0, lambda: self._set_status(f"Slot {index + 1}: auto-login…")
                )
                self._auto_login_thread(
                    [slot]
                )  # inline — keeps _relaunching set until autologin+char-select complete
            else:
                self.root.after(
                    0,
                    lambda: self._set_status(f"Slot {index + 1}: relaunch complete ✓"),
                )
        finally:
            self._relaunching.discard(index)
            self._relaunch_lock.release()

    def _launch_into_slot(self, index: int):
        cmd = self._slot_command(index)
        launch_enb_client(cmd)
        self._set_status(f"Slot {index + 1}: waiting for EULA…")

        def _do():
            launch_delay = self.settings.get("launch_delay_ms", 3000) / 1000.0
            known_ids = {
                w["id"]
                for w in find_enb_windows()
                if w["id"] != self.slots.slot(index).window_id
            }

            self._dismiss_launcher_if_present(known_ids, pre_enter_delay=2.0)
            eula_wid = self._wait_for_eula_window(known_ids)

            if not eula_wid:
                self.root.after(
                    0, lambda: self._set_status(f"Slot {index + 1}: window not detected")
                )
                return
            self.root.after(
                0, lambda: self._set_status(f"Slot {index + 1}: EULA — pressing Enter…")
            )
            self._dismiss_eula_window(eula_wid)

            login_wid, pid = self._find_login_window(known_ids, eula_wid, launch_delay)
            if login_wid:
                self.slots.assign_window_to_slot(index, login_wid, pid)
                self.root.after(0, self._refresh_slot_cards)
                self.root.after(0, self._redraw_canvas)
                time.sleep(3.5)
                if self._layout_mode == "auto":
                    self.root.after(0, lambda: self._auto_tile(apply=True))
                else:
                    self.root.after(0, lambda i=index: self._apply_layout(slot_index=i, resize_driver=(i == 0)))
                self.root.after(
                    0, lambda: self._set_status(f"Slot {index + 1}: ready ✓")
                )
                if self.autologin_var.get():
                    slot = self.slots.slot(index)
                    if slot.username:
                        threading.Thread(
                            target=self._auto_login_thread, args=([slot],), daemon=True
                        ).start()
            else:
                self.root.after(
                    0,
                    lambda: self._set_status(
                        f"Slot {index + 1}: login window not found"
                    ),
                )

        threading.Thread(target=_do, daemon=True).start()

    def _launch_independent_slot(self):
        """Launch independent client — a normal movable window, not tracked or tiled."""
        if sys.platform == "win32":
            cmd = (self.settings.get("slot_commands") or [None])[0]
            if not cmd:
                self._set_status("Independent client: no launch command configured")
                return
            self._set_status("Independent client launching…")
            threading.Thread(target=self._launch_independent_thread, args=(cmd,), daemon=True).start()
            return
        extra_script = os.path.expanduser("~/.local/bin/enb-extra")
        if not os.path.exists(extra_script):
            self._set_status("Independent client: ~/.local/bin/enb-extra not found — run setup_prefixes.sh")
            return
        self._set_status("Independent client launching…")
        threading.Thread(target=self._launch_independent_thread, args=(extra_script,), daemon=True).start()

    def _launch_independent_thread(self, cmd: str):
        if sys.platform == "win32":
            import psutil
            known_game_pids = set()
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    name = (proc.info['name'] or '').lower()
                    if 'net7proxy' in name or name == 'client.exe':
                        known_game_pids.add(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            known_ids = {w["id"] for w in find_enb_windows_by_process()}
            pid = launch_enb_client(cmd)
            if not pid:
                self.root.after(0, lambda: self._set_status("Independent client: launch failed"))
                return

            self._dismiss_launcher_if_present(known_ids, pre_enter_delay=2.0)
            eula_wid = self._wait_for_eula_window(known_ids)
            if eula_wid:
                self._dismiss_eula_window(eula_wid, activate_first=True)

            new_wid, _pid = self._find_login_window(known_ids, eula_wid, _GAME_SETTLE_S)
            if not new_wid:
                self.root.after(0, lambda: self._set_status("Independent client: window not detected"))
                return
        else:
            known_ids = {w["id"] for w in find_enb_windows_any()}
            launch_enb_client(f"bash {cmd}")

            new_wid = None
            deadline = time.time() + 30.0
            while time.time() < deadline:
                for w in find_enb_windows_any():
                    if w["id"] not in known_ids:
                        new_wid = w["id"]
                        break
                if new_wid:
                    break
                time.sleep(0.5)

            if not new_wid:
                self.root.after(0, lambda: self._set_status("Independent client: window not detected"))
                return

            time.sleep(_GAME_SETTLE_S)

            fresh = {w["id"] for w in find_enb_windows_any()} - known_ids
            if fresh:
                new_wid = max(fresh)

        # Intentionally NOT borderless and NOT repositioned/resized — this is a
        # normal window the user can drag wherever they want (any monitor,
        # single-monitor setups included), unlike the managed slots.
        self._independent_wids.add(new_wid)

        if sys.platform == "win32":
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    name = (proc.info['name'] or '').lower()
                    pid  = proc.info['pid']
                    if pid not in known_game_pids and ('net7proxy' in name or name == 'client.exe'):
                        self._independent_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        self.root.after(0, lambda: self._set_status("Independent client ready ✓"))

    def _assign_window_dialog(self, index: int):
        """Show list of unassigned EnB windows for manual assignment."""
        wins = find_enb_windows()
        known = {s.window_id for s in self.slots.slots if s.is_assigned}
        avail = [w for w in wins if w["id"] not in known]

        if not avail:
            messagebox.showinfo(
                "No Windows", "No unassigned EnB windows found.\nLaunch clients first."
            )
            return

        # Simple picker dialog
        dlg = tk.Toplevel(self.root)
        dlg.title("Assign Window")
        dlg.configure(bg=tk_color("bg"))
        dlg.grab_set()

        tk.Label(
            dlg,
            text="Select window to assign to this slot:",
            bg=tk_color("bg"),
            fg=tk_color("text"),
            font=THEME["font_main"],
        ).pack(padx=12, pady=8)

        listbox = tk.Listbox(
            dlg,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_mono"],
            width=50,
            height=8,
            selectbackground=tk_color("accent"),
        )
        listbox.pack(padx=12, pady=4)

        for w in avail:
            listbox.insert("end", f"[{hex(w['id'])}]  {w['title']}")

        def confirm():
            sel = listbox.curselection()
            if not sel:
                return
            win = avail[sel[0]]
            self.slots.assign_window_to_slot(index, win["id"], win.get("pid"))
            dlg.destroy()

        tk.Button(
            dlg,
            text="Assign",
            command=confirm,
            bg=tk_color("success"),
            fg="white",
            font=THEME["font_main"],
            relief="flat",
            padx=10,
        ).pack(pady=8)

    def _pick_role_profile(self, slot_index: int):
        profiles = list_role_profiles()
        slot = self.slots.slot(slot_index)

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Role Profile — Slot {slot_index + 1}")
        dlg.configure(bg=tk_color("bg"))
        dlg.geometry("300x200")
        dlg.grab_set()
        _center_on_parent(dlg, self.root)

        tk.Label(
            dlg,
            text="Select role profile for this slot:",
            bg=tk_color("bg"),
            fg=tk_color("text"),
            font=THEME["font_small"],
        ).pack(padx=12, pady=(12, 4), anchor="w")

        var = tk.StringVar(value=slot.role_profile)
        combo = ttk.Combobox(
            dlg,
            textvariable=var,
            values=["(none)"] + profiles,
            state="readonly",
            font=THEME["font_main"],
            width=24,
        )
        combo.pack(padx=12, pady=4)

        def open_editor():
            dlg.destroy()
            from gui_settings import SettingsWindow

            SettingsWindow(
                self.root,
                self.settings,
                self._on_settings_saved,
                monitors=self.monitors,
                initial_tab="Roles",
                capture_click=self._capture_click,
            )

        tk.Button(
            dlg,
            text="Manage Profiles…",
            command=open_editor,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_small"],
            relief="flat",
        ).pack(pady=4)

        def confirm():
            chosen = var.get()
            slot.role_profile = "" if chosen == "(none)" else chosen
            self._redraw_canvas()
            dlg.destroy()

        tk.Button(
            dlg,
            text="Assign",
            command=confirm,
            bg=tk_color("success"),
            fg="white",
            font=THEME["font_main"],
            relief="flat",
            padx=12,
            pady=4,
        ).pack(pady=(4, 12))

    def _edit_loop_overrides(self, slot_index: int):
        """Per-character loop key overrides layered on top of the role
        profile. Each section has its own checkbox — unchecked sections
        are removed from loop_overrides and fall through to the profile."""
        slot = self.slots.slot(slot_index)
        char_name = slot.character
        if not char_name:
            return
        char = load_character(char_name)
        overrides = char.get("loop_overrides", {}) or {}

        FKEY_OPTIONS = ["", "f1", "f2", "f3", "f4", "f5", "f6"]

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Loop Overrides — {char_name}")
        dlg.configure(bg=tk_color("bg"))
        dlg.geometry("560x440")
        dlg.grab_set()
        dlg.resizable(True, True)
        _center_on_parent(dlg, self.root)

        autowrap(tk.Label(
            dlg,
            text=f"Per-character exceptions on top of role profile "
                 f"\"{slot.role_profile or '(none)'}\".\n"
                 "Check a section to override it for this character only — "
                 "unchecked sections fall through to the shared profile.",
            bg=tk_color("bg"), fg=tk_color("text_dim"),
            font=THEME["font_small"], justify="left",
        )).pack(fill="x", padx=12, pady=(10, 4))

        nb = ttk.Notebook(dlg)
        nb.pack(fill="both", expand=True, padx=12, pady=8)

        enable_vars = {}
        key_vars = {}
        heal_target_var = tk.StringVar(value=overrides.get("heal_target_key", ""))
        heal_target_enable = tk.BooleanVar(value="heal_target_key" in overrides)
        buff_device_vars = []
        buff_devices_enable = tk.BooleanVar(value="buff_devices" in overrides)

        override_loop_types = [
            t for t in LOOP_TYPES if t[0] in ("combat", "buff", "debuff", "heal")
        ]

        for loop_type, loop_label in override_loop_types:
            tab = tk.Frame(nb, bg=tk_color("bg"))
            nb.add(tab, text=loop_label)

            key_field = f"{loop_type}_keys"
            enable_var = tk.BooleanVar(value=key_field in overrides)
            enable_vars[key_field] = enable_var

            tk.Checkbutton(
                tab, text=f"Override {loop_label} Keys",
                variable=enable_var,
                bg=tk_color("bg"), fg=tk_color("text"),
                selectcolor=tk_color("card_bg"),
                activebackground=tk_color("bg"),
                font=THEME["font_small"],
            ).pack(anchor="w", padx=8, pady=(8, 2))

            existing = overrides.get(key_field, [])
            padded = (existing + [""] * 6)[:6]

            grid_f = tk.Frame(tab, bg=tk_color("bg"))
            grid_f.pack(padx=16, pady=4, anchor="w")

            vars_for_type = []
            for col, lbl in enumerate(
                ["Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6"]
            ):
                tk.Label(
                    grid_f, text=lbl,
                    bg=tk_color("bg"), fg=tk_color("text_dim"),
                    font=THEME["font_small"], anchor="center",
                ).grid(row=0, column=col, padx=2, sticky="ew")
                v = tk.StringVar(value=padded[col])
                ttk.Combobox(
                    grid_f, textvariable=v,
                    values=LOOP_KEY_OPTIONS,
                    width=5, font=THEME["font_small"],
                ).grid(row=1, column=col, padx=2, pady=2)
                vars_for_type.append(v)
            key_vars[key_field] = vars_for_type

            if loop_type == "heal":
                hrow = tk.Frame(tab, bg=tk_color("bg"))
                hrow.pack(anchor="w", padx=8, pady=(10, 0))
                tk.Checkbutton(
                    hrow, text="Override target driver key (TT only):",
                    variable=heal_target_enable,
                    bg=tk_color("bg"), fg=tk_color("text"),
                    selectcolor=tk_color("card_bg"),
                    activebackground=tk_color("bg"),
                    font=THEME["font_small"],
                ).pack(side="left")
                ttk.Combobox(
                    hrow, textvariable=heal_target_var,
                    values=FKEY_OPTIONS, width=5,
                    state="readonly", font=THEME["font_small"],
                ).pack(side="left", padx=6)

            if loop_type == "buff":
                tk.Frame(tab, bg=tk_color("slot_border"), height=1
                         ).pack(fill="x", padx=8, pady=(10, 0))

                tk.Checkbutton(
                    tab, text="Override Targeted Devices",
                    variable=buff_devices_enable,
                    bg=tk_color("bg"), fg=tk_color("text"),
                    selectcolor=tk_color("card_bg"),
                    activebackground=tk_color("bg"),
                    font=THEME["font_small"],
                ).pack(anchor="w", padx=8, pady=(6, 2))

                existing_devs = overrides.get("buff_devices", [])
                existing_devs = (existing_devs + [{}, {}, {}])[:3]

                for di, dev in enumerate(existing_devs):
                    dev_key_var = tk.StringVar(value=dev.get("key", ""))
                    dev_reassist_var = tk.BooleanVar(value=dev.get("reassist", True))
                    dev_casttime_var = tk.StringVar(value=str(dev.get("cast_time_s", 0.0)))
                    raw_targets = dev.get("targets", [])
                    raw_targets = (raw_targets + [""] * 6)[:6]
                    dev_target_vars = [tk.StringVar(value=t) for t in raw_targets]
                    buff_device_vars.append({
                        "key_var": dev_key_var,
                        "target_vars": dev_target_vars,
                        "reassist_var": dev_reassist_var,
                        "casttime_var": dev_casttime_var,
                    })

                    dev_frame = tk.Frame(
                        tab, bg=tk_color("card_bg"),
                        relief="flat", bd=0,
                        highlightthickness=1,
                        highlightbackground=tk_color("slot_border"),
                    )
                    dev_frame.pack(fill="x", padx=8, pady=(4, 0))

                    hdr_row = tk.Frame(dev_frame, bg=tk_color("card_bg"))
                    hdr_row.pack(fill="x", padx=6, pady=(4, 2))
                    tk.Label(
                        hdr_row, text=f"Device {di + 1}:",
                        bg=tk_color("card_bg"), fg=tk_color("text"),
                        font=THEME["font_small"], width=9, anchor="w",
                    ).pack(side="left")
                    ttk.Combobox(
                        hdr_row, textvariable=dev_key_var,
                        values=LOOP_KEY_OPTIONS, width=7,
                        font=THEME["font_small"],
                    ).pack(side="left", padx=(0, 8))
                    tk.Label(
                        hdr_row, text="Cast time (s):",
                        bg=tk_color("card_bg"), fg=tk_color("text"),
                        font=THEME["font_small"],
                    ).pack(side="left")
                    tk.Entry(
                        hdr_row, textvariable=dev_casttime_var, width=5,
                        bg=tk_color("bg"), fg=tk_color("text"),
                        insertbackground=tk_color("text"),
                        font=THEME["font_mono"], relief="flat",
                    ).pack(side="left", padx=(2, 8))

                    tgt_row = tk.Frame(dev_frame, bg=tk_color("card_bg"))
                    tgt_row.pack(anchor="w", padx=6, pady=(0, 2))
                    tk.Label(
                        tgt_row, text="Targets:",
                        bg=tk_color("card_bg"), fg=tk_color("text_dim"),
                        font=THEME["font_small"],
                    ).pack(side="left", padx=(0, 6))
                    for ti, tv in enumerate(dev_target_vars):
                        lf = tk.Frame(tgt_row, bg=tk_color("card_bg"))
                        lf.pack(side="left", padx=(0, 4))
                        tk.Label(
                            lf, text=f"{ti + 1}:",
                            bg=tk_color("card_bg"), fg=tk_color("text_dim"),
                            font=THEME["font_small"],
                        ).pack()
                        ttk.Combobox(
                            lf, textvariable=tv, values=FKEY_OPTIONS,
                            width=4, state="readonly",
                            font=THEME["font_small"],
                        ).pack()

                    reassist_row = tk.Frame(dev_frame, bg=tk_color("card_bg"))
                    reassist_row.pack(anchor="w", padx=6, pady=(0, 6))
                    tk.Checkbutton(
                        reassist_row,
                        text="Re-assist + fire after each target",
                        variable=dev_reassist_var,
                        bg=tk_color("card_bg"), fg=tk_color("text"),
                        selectcolor=tk_color("bg"),
                        activebackground=tk_color("card_bg"),
                        font=THEME["font_small"],
                    ).pack(side="left")

        def _safe_float(val, default):
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        def save_overrides():
            new_overrides = {}
            for loop_type, _ in override_loop_types:
                key_field = f"{loop_type}_keys"
                if enable_vars[key_field].get():
                    new_overrides[key_field] = [
                        v.get() for v in key_vars[key_field] if v.get()
                    ]
            if heal_target_enable.get():
                new_overrides["heal_target_key"] = heal_target_var.get()
            if buff_devices_enable.get():
                new_overrides["buff_devices"] = [
                    {
                        "key": d["key_var"].get(),
                        "targets": [v.get() for v in d["target_vars"] if v.get()],
                        "reassist": d["reassist_var"].get(),
                        "cast_time_s": _safe_float(d["casttime_var"].get(), 0.0),
                    }
                    for d in buff_device_vars
                    if d["key_var"].get()
                ]
            char["loop_overrides"] = new_overrides
            save_character(char)
            dlg.destroy()
            self._set_status(f"Loop overrides saved for {char_name}")

        btn_row = tk.Frame(dlg, bg=tk_color("bg"))
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(
            btn_row, text="Save", command=save_overrides,
            bg=tk_color("success"), fg="white",
            font=THEME["font_main"], relief="flat",
            padx=12, pady=4,
        ).pack(side="right")
        tk.Button(
            btn_row, text="Cancel", command=dlg.destroy,
            bg=tk_color("card_bg"), fg=tk_color("text"),
            font=THEME["font_small"], relief="flat",
            padx=12, pady=4,
        ).pack(side="right", padx=(0, 8))

    def _pick_slot_character(self, slot_index: int):
        """Pick a character profile for this slot. Selecting one populates
        role/role_profile/credentials from the character profile."""
        slot = self.slots.slot(slot_index)
        chars = list_characters()

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Character — Slot {slot_index + 1}")
        dlg.configure(bg=tk_color("bg"))
        dlg.geometry("320x200")
        dlg.grab_set()
        _center_on_parent(dlg, self.root)

        tk.Label(
            dlg,
            text="Assign character to this slot:",
            bg=tk_color("bg"),
            fg=tk_color("text"),
            font=THEME["font_small"],
        ).pack(padx=12, pady=(12, 4), anchor="w")

        var = tk.StringVar(value=slot.character)
        ttk.Combobox(
            dlg,
            textvariable=var,
            values=["(none)"] + chars,
            state="readonly",
            font=THEME["font_main"],
            width=24,
        ).pack(padx=12, pady=4)

        def open_editor():
            dlg.destroy()
            from gui_settings import SettingsWindow

            SettingsWindow(
                self.root,
                self.settings,
                self._on_settings_saved,
                monitors=self.monitors,
                initial_tab="Characters",
                capture_click=self._capture_click,
            )

        tk.Button(
            dlg,
            text="Manage Characters…",
            command=open_editor,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_small"],
            relief="flat",
        ).pack(pady=4)

        def confirm():
            chosen = var.get()
            if chosen == "(none)" or not chosen:
                slot.character = ""
            else:
                slot.apply_character(load_character(chosen))
            self._refresh_slot_cards()
            self._redraw_canvas()
            dlg.destroy()

        tk.Button(
            dlg,
            text="Assign",
            command=confirm,
            bg=tk_color("success"),
            fg="white",
            font=THEME["font_main"],
            relief="flat",
            padx=12,
            pady=4,
        ).pack(pady=(4, 12))

    def _pick_slot_role(self, slot_index: int):
        """Manually set a role abbreviation when no character is assigned."""
        slot = self.slots.slot(slot_index)
        choice = simpledialog.askstring(
            "Set Role",
            f"Class abbreviation for slot {slot_index + 1}\n"
            f"({', '.join(CLASS_ABBREVS)} or empty):",
            initialvalue=slot.role,
            parent=self.root,
        )
        if choice is None:
            return
        choice = choice.strip().upper()
        slot.set_role(choice if choice in CLASS_ABBREVS else "")
        self._refresh_slot_cards()
        self._redraw_canvas()

    def _rename_slot_window(self, index: int):
        slot = self.slots.slot(index)
        if not slot.is_assigned:
            messagebox.showinfo("Not Assigned", "No window assigned to this slot.")
            return
        name = simpledialog.askstring(
            "Rename Window",
            f"New title for slot {index + 1}:",
            initialvalue=slot.role,
            parent=self.root,
        )
        if name:
            rename_window(slot.window_id, name)

    # ── Driver helpers ────────────────────────────────────────


    def _get_driver_slot(self):
        """Return the slot designated as driver.
        Default is slot 0. Alt+G permanently reassigns it to whoever is on
        the main monitor at that moment via _cycle_mgr._driver_idx."""
        if self._cycle_mgr is not None:
            return self.slots.slot(self._cycle_mgr._driver_idx)
        return self.slots.slot(0)

    def _assign_driver(self):
        """Alt+G handler: make whoever is on the main monitor the permanent driver."""
        if self._cycle_mgr is None:
            return
        swapped = self._cycle_mgr._swapped_slot
        new_idx = swapped if swapped is not None else 0
        self._cycle_mgr._driver_idx = new_idx
        slot = self.slots.slot(new_idx)
        name = slot.char_name or slot.character or f"Slot {new_idx + 1}"
        self._set_status(f"Driver → {name}")
        self._update_omit_indicator()

    def _get_secondary_slots(self):
        """Return all assigned slots that are NOT currently on the main monitor."""
        driver = self._get_driver_slot()
        return [s for s in self.slots.assigned_slots() if s.index != driver.index]

    def _get_loop_slots(self):
        """Secondary slots eligible for loops/reform."""
        return self._get_secondary_slots()

    # ── Macros ────────────────────────────────────────────────

    def _run_invite(self):
        if self._invite_running:
            self._set_status("Invite already running")
            return
        profile_name = self.invite_var.get()
        if not profile_name:
            messagebox.showinfo(
                "No Invite List", "Create or select an invite list first."
            )
            return
        if profile_name == INVITE_FROM_SLOTS:
            names = self._invite_names_from_slots()
            if not names:
                messagebox.showinfo(
                    "No Slot Characters",
                    "No characters/char-names set on slots 2–6.",
                )
                return
        else:
            profile = load_invite_profile(profile_name)
            names = profile.get("names", [])
            if not names:
                messagebox.showinfo(
                    "Empty List",
                    f"Invite list '{profile_name}' has no names.\n"
                    "Click Edit to add names.",
                )
                return
        if not self._get_driver_slot().is_assigned:
            messagebox.showinfo(
                "No Driver", "No window assigned to the current driver slot."
            )
            return
        self._abort_flag.clear()
        self._invite_running = True
        self._set_status(f"Running invite: {profile_name}…")
        t = threading.Thread(target=self._invite_thread, args=(names,), daemon=True)
        t.start()

    def _invite_thread(self, names: list):
        try:
            self._invite_thread_body(names)
        except Exception as e:
            self.root.after(0, lambda e=e: self._set_status(f"Invite error: {e}"))
        finally:
            self._invite_running = False

    def _invite_thread_body(self, names: list):
        wait_modifiers_released()
        release_modifiers()
        delay          = self.settings.get("action_delay_ms", 50) / 1000.0
        accept         = self.settings.get("invite_accept", {})
        slide_down_px  = accept.get("slide_down_px", 500)
        slide_down_ms  = accept.get("slide_down_ms", 300)
        driver = self._get_driver_slot()

        # Camera-rotation amount scales with window height — a 500px drag on a
        # 540px-tall window is a much bigger turn than on a 1080px-tall one.
        # Scale relative to the standard secondary slot height (540px).
        def _scaled_slide_px(win_h: int) -> int:
            if not win_h:
                return slide_down_px
            ratio = win_h / 540
            return int(slide_down_px * ratio * ratio)

        # ── Step 1: send /invite from driver ──────────────────
        activate_window(driver.window_id)
        time.sleep(0.2)

        # Slide the camera back on the driver's 3rd person view, same as the
        # accept-side slide on secondary slots.
        if slide_down_px:
            dwin = get_window_by_id(driver.window_id)
            dwh = dwin["h"] if dwin else driver.h
            mouse_slide_relative(dy=_scaled_slide_px(dwh), duration_ms=slide_down_ms)

        for name in names:
            if self._abort_flag.is_set():
                break
            key_to_focused("Return")
            time.sleep(0.05)
            type_to_focused(f"/invite {name}")
            time.sleep(0.05)
            key_to_focused("Return")
            time.sleep(delay)

        if self._abort_flag.is_set():
            self.root.after(0, lambda: self._set_status("Invite aborted"))
            return

        # ── Step 2: accept invite on each assigned secondary ──
        time.sleep(0.5)
        secondary = self._get_loop_slots()

        per_window = accept.get("per_window", [])
        for slot in secondary:
            if self._abort_flag.is_set():
                break
            idx = slot.index - 1
            if idx < len(per_window):
                cx = per_window[idx].get("x_pct", 0.0)
                cy = per_window[idx].get("y_pct", 0.0)
                if cx or cy:
                    activate_window(slot.window_id)
                    time.sleep(0.1)
                    win = get_window_by_id(slot.window_id)
                    wx = win["x"] if win else slot.x
                    wy = win["y"] if win else slot.y
                    ww = win["w"] if win else slot.w
                    wh = win["h"] if win else slot.h
                    click_at(int(wx + cx * ww), int(wy + cy * wh))
                    time.sleep(0.02)
                    if slide_down_px:
                        mouse_slide_relative(dy=_scaled_slide_px(wh), duration_ms=slide_down_ms)

        # Return focus to driver
        activate_window(driver.window_id)
        self.root.after(0, lambda: self._set_status("Invite complete ✓"))

    def _new_invite_profile(self):
        name = simpledialog.askstring("New Invite List", "List name:", parent=self.root)
        if not name:
            return
        save_invite_profile({"name": name, "names": []})
        profiles = [INVITE_FROM_SLOTS] + list_invite_profiles()
        self.invite_combo.configure(values=profiles)
        self.invite_var.set(name)
        self._edit_invite_list()

    def _invite_names_from_slots(self) -> list:
        """Auto-build invite list from slots 2–6 (non-driver) in slot order.
        Slots are listed in slot order; driver is excluded.
        Falls back to slot.char_name when no character profile is set.
        Empty entries are skipped."""
        driver_idx = self._get_driver_slot().index
        names = []
        for s in self.slots.slots:
            if s.index == driver_idx:
                continue
            n = (s.character or s.char_name or "").strip()
            if n and n not in names:
                names.append(n)
        return names

    def _edit_invite_list(self):
        profile_name = self.invite_var.get()
        if not profile_name:
            messagebox.showinfo(
                "No List Selected", "Select or create an invite list first."
            )
            return
        if profile_name == INVITE_FROM_SLOTS:
            names = self._invite_names_from_slots()
            messagebox.showinfo(
                "Auto Invite List",
                "This list is auto-built from characters assigned to "
                "slots 2–6 in slot order. The list is read-only.\n\n"
                f"Current names: {', '.join(names) if names else '(none)'}",
            )
            return
        profile = load_invite_profile(profile_name)

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Invite List — {profile_name}")
        dlg.configure(bg=tk_color("bg"))
        dlg.geometry("340x400")
        dlg.grab_set()
        _center_on_parent(dlg, self.root)
        dlg.resizable(True, True)

        tk.Label(
            dlg,
            text=f"Names in '{profile_name}':",
            bg=tk_color("bg"),
            fg=tk_color("text_dim"),
            font=THEME["font_small"],
        ).pack(anchor="w", padx=12, pady=(10, 2))

        listbox = tk.Listbox(
            dlg,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_main"],
            selectbackground=tk_color("accent"),
            activestyle="none",
            height=12,
        )
        listbox.pack(fill="both", expand=True, padx=12, pady=4)

        for n in profile.get("names", []):
            listbox.insert("end", n)

        # Add row
        add_frame = tk.Frame(dlg, bg=tk_color("bg"))
        add_frame.pack(fill="x", padx=12, pady=(0, 4))
        entry_var = tk.StringVar()
        entry = tk.Entry(
            add_frame,
            textvariable=entry_var,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            insertbackground=tk_color("text"),
            font=THEME["font_main"],
            relief="flat",
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        def add_name():
            name = entry_var.get().strip()
            if name and name not in listbox.get(0, "end"):
                listbox.insert("end", name)
                entry_var.set("")
            entry.focus_set()

        entry.bind("<Return>", lambda _: add_name())
        tk.Button(
            add_frame,
            text="Add",
            command=add_name,
            bg=tk_color("success"),
            fg="white",
            font=THEME["font_small"],
            relief="flat",
            padx=8,
        ).pack(side="left")

        def remove_selected():
            sel = listbox.curselection()
            for i in reversed(sel):
                listbox.delete(i)

        tk.Button(
            dlg,
            text="Remove Selected",
            command=remove_selected,
            bg=tk_color("danger"),
            fg="white",
            font=THEME["font_small"],
            relief="flat",
            padx=8,
            pady=3,
        ).pack(pady=(0, 4))

        def save_and_close():
            profile["names"] = list(listbox.get(0, "end"))
            save_invite_profile(profile)
            dlg.destroy()
            self._set_status(f"Invite list '{profile_name}' saved")

        tk.Button(
            dlg,
            text="Save & Close",
            command=save_and_close,
            bg=tk_color("accent"),
            fg="white",
            font=THEME["font_main"],
            relief="flat",
            padx=12,
            pady=5,
        ).pack(pady=(0, 10))

    def _run_reform(self):
        if self._reform_running:
            self._set_status("Reform already running")
            return
        if not self._get_driver_slot().is_assigned:
            messagebox.showinfo(
                "No Driver", "No window assigned to the current driver slot."
            )
            return
        self._abort_flag.clear()
        self._reform_running = True
        self._set_status("Running reform…")
        t = threading.Thread(target=self._reform_thread, daemon=True)
        t.start()

    def _reform_thread(self):
        try:
            self._reform_thread_body()
        except Exception as e:
            self.root.after(0, lambda e=e: self._set_status(f"Reform error: {e}"))
        finally:
            self._reform_running = False

    def _reform_thread_body(self):
        wait_modifiers_released()
        release_modifiers()
        cfg = self.settings.get("reform", {})
        click_1 = cfg.get("click_1", {"x_pct": 0.0, "y_pct": 0.0})
        click_2 = cfg.get("click_2", {"x_pct": 0.0, "y_pct": 0.0})
        click_delay = cfg.get("click_delay_ms", 200) / 1000.0
        settle = cfg.get("settle_ms", 1000) / 1000.0
        form_key = cfg.get("key", "t")
        key_delay = cfg.get("key_delay_ms", 300) / 1000.0

        driver = self._get_driver_slot()
        if self._abort_flag.is_set():
            return
        activate_window(driver.window_id)
        time.sleep(0.4)

        # Driver: click formation button then formation type to create the formation
        dwin = get_window_by_id(driver.window_id)
        dwx = dwin["x"] if dwin else driver.x
        dwy = dwin["y"] if dwin else driver.y
        dww = dwin["w"] if dwin else driver.w
        dwh = dwin["h"] if dwin else driver.h
        c1x = click_1.get("x_pct", 0.0)
        c1y = click_1.get("y_pct", 0.0)
        c2x = click_2.get("x_pct", 0.0)
        c2y = click_2.get("y_pct", 0.0)
        if c1x or c1y:
            click_at(int(dwx + c1x * dww), int(dwy + c1y * dwh))
        time.sleep(click_delay)
        if c2x or c2y:
            click_at(int(dwx + c2x * dww), int(dwy + c2y * dwh))

        # Wait for formation to register before members join
        time.sleep(settle)

        if self._abort_flag.is_set():
            self.root.after(0, lambda: self._set_status("Reform aborted"))
            return

        # Each secondary: focus it, wait briefly, press the join key — no coordinate clicks
        secondary = self._get_loop_slots()
        for slot in secondary:
            if self._abort_flag.is_set():
                break
            activate_window(slot.window_id)
            time.sleep(key_delay)
            key_to_focused(form_key)

        activate_window(driver.window_id)
        self.root.after(0, lambda: self._set_status("Reform complete ✓"))

    def _start_loop(self, loop_type: str):
        if self._loop_running:
            self._set_status(f"{loop_type} loop already running")
            return
        self._abort_flag.clear()
        self._loop_running = True
        labels = {
            "combat": "Combat",
            "buff": "Buff",
            "debuff": "Debuff",
            "heal": "Heal",
        }
        self._set_status(f"{labels.get(loop_type, loop_type)} loop running…")
        t = threading.Thread(
            target=self._loop_pass_thread, args=(loop_type,), daemon=True
        )
        t.start()

    def _abortable_sleep(self, seconds: float) -> bool:
        """Sleep in small chunks, checking the abort flag. Returns True if
        aborted early. Used for long settle waits (e.g. char-select settle)
        that would otherwise outlast _stop_loop's abort-flag auto-clear."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self._abort_flag.is_set():
                return True
            time.sleep(min(0.2, deadline - time.time()))
        return self._abort_flag.is_set()

    def _stop_loop(self):
        """Stop all running scripts — loops, autologin sequences, in-progress launches."""
        self._abort_flag.set()
        self._loop_running = False
        self._energy_running = False
        self._daimyo_running = False
        self._set_status("⛔ All scripts stopped")
        # Clear after a delay so crash-relaunch autologin isn't permanently
        # blocked. Must be longer than the longest single uninterruptible wait
        # any in-progress thread might be in — currently the char-select settle
        # delay (config/settings.json char_select.settle_ms, default 6000ms) is
        # the largest, so clear 1s after that to be safe.
        cs_settle_ms = self.settings.get("char_select", {}).get("settle_ms", 6000)
        clear_delay_ms = max(5000, cs_settle_ms + 1000)
        self.root.after(clear_delay_ms, self._abort_flag.clear)

    def _abort_and_stop(self):
        self._stop_loop()

    def _effective_profile(self, slot) -> dict:
        """Role profile for this slot with the character's loop_overrides
        merged on top. Per-character exceptions (e.g. a different hotbar
        key) without duplicating the whole role profile."""
        profile = dict(load_role_profile(slot.role_profile)) if slot.role_profile else {}
        if slot.character:
            overrides = load_character(slot.character).get("loop_overrides", {})
            if overrides:
                profile.update(overrides)
        return profile

    def _loop_pass_thread(self, loop_type: str):
        try:
            self._loop_active_wid = None
            wait_modifiers_released()
            release_modifiers()
            loops = self.settings.get("loops", {})
            key_delay = self._raid_ms(loops.get("key_delay_ms", 300)) / 1000.0
            fire_key = loops.get("fire_key", "f")
            assist_per = loops.get("assist_per_window", [])
            secondary = self._get_loop_slots()
            if not secondary:
                self.root.after(
                    0, lambda: self._set_status("No secondary slots assigned")
                )
                return

            slot_profiles = {s.index: self._effective_profile(s) for s in secondary}

            if loop_type == "buff" and loops.get("interleave_buffs", False):
                self._run_interleaved_buffs(
                    secondary, slot_profiles, key_delay, fire_key, assist_per
                )

            for slot in secondary:
                if not self._loop_running or self._abort_flag.is_set():
                    break

                profile = slot_profiles[slot.index]
                cls = profile.get("class", "")

                if loop_type == "combat":
                    keys = [k for k in profile.get("combat_keys", []) if k]
                    self._activate(slot.window_id)
                    self._do_assist_fire(slot, assist_per, fire_key, key_delay)
                    if keys:
                        # Re-focus after assist click + fire before sending combat keys.
                        self._activate(slot.window_id)
                        for key in keys:
                            if not self._loop_running:
                                break
                            key_to_focused(key)
                            time.sleep(key_delay)

                elif loop_type == "buff":
                    if loops.get("interleave_buffs", False):
                        # Handled once, across all slots, before this loop.
                        continue

                    simple_keys = [k for k in profile.get("buff_keys", []) if k]
                    devices = [
                        d for d in profile.get("buff_devices", []) if d.get("key")
                    ]
                    if not simple_keys and not devices:
                        continue

                    # Activate window once for this slot — not repeated per device/target
                    self._activate(slot.window_id)

                    # Simple casts — no targeting, no cast time
                    for key in simple_keys:
                        if not self._loop_running:
                            break
                        key_to_focused(key)
                        time.sleep(key_delay)

                    # Devices — each has optional targets, cast_time, reassist
                    for device in devices:
                        if not self._loop_running:
                            break
                        dev_key = device["key"]
                        targets = [t for t in device.get("targets", []) if t]
                        reassist = device.get("reassist", True)
                        cast_time = float(device.get("cast_time_s", 0.0))

                        if not targets:
                            # No targets = group buff or self-buff: cast once, move on
                            key_to_focused(dev_key)
                            if cast_time > 0:
                                time.sleep(cast_time)
                            # If cast_time==0: instant, no wait — proceed immediately
                            if reassist and cast_time > 0:
                                self._do_assist_fire(
                                    slot, assist_per, fire_key, key_delay
                                )
                        else:
                            # Targeted: window already active from initial activate above.
                            # _do_assist_fire re-activates internally after its click,
                            # so window stays focused between targets on the same slot.
                            for target_key in targets:
                                if not self._loop_running:
                                    break
                                key_to_focused(target_key)
                                time.sleep(key_delay)
                                key_to_focused(dev_key)
                                if cast_time > 0:
                                    time.sleep(cast_time)
                                else:
                                    time.sleep(key_delay)
                                if reassist:
                                    self._do_assist_fire(
                                        slot, assist_per, fire_key, key_delay
                                    )

                elif loop_type == "debuff":
                    keys = [k for k in profile.get("debuff_keys", []) if k]
                    if not keys:
                        continue
                    self._activate(slot.window_id)
                    for key in keys:
                        if not self._loop_running:
                            break
                        key_to_focused(key)
                        time.sleep(key_delay)

                elif loop_type == "heal":
                    keys = [k for k in profile.get("heal_keys", []) if k]
                    if not keys:
                        continue
                    self._activate(slot.window_id)
                    if cls == "TT":
                        target_key = profile.get("heal_target_key", "")
                        if target_key:
                            key_to_focused(target_key)
                            time.sleep(key_delay)
                        for key in keys:
                            if not self._loop_running:
                                break
                            key_to_focused(key)
                            time.sleep(key_delay)
                        self._do_assist_fire(slot, assist_per, fire_key, key_delay)
                    else:
                        for key in keys:
                            if not self._loop_running:
                                break
                            key_to_focused(key)
                            time.sleep(key_delay)

            driver = self._get_driver_slot()
            if driver.is_assigned:
                cx = driver.x + driver.w // 2
                cy = driver.y + driver.h // 2
                return_to_driver(driver.window_id, cx, cy)

        except Exception as e:
            print(f"[loop] {loop_type} error: {e}")
        finally:
            self._loop_running = False
            self.root.after(
                0, lambda: self._set_status(f"{loop_type.capitalize()} loop complete ✓")
            )

    def _run_interleaved_buffs(self, secondary, slot_profiles, key_delay, fire_key, assist_per):
        """Buff loop, target-outer: every buffer hits F1 before anyone moves
        to F2. Cast-time waits are folded across slots — by the time the last
        slot fires on a target, earlier slots' casts are already mid-flight,
        so a single shared wait covers the whole round instead of N separate
        waits."""
        # Simple casts (group/self buffs, no targeting) — per-slot, no benefit to interleaving
        for slot in secondary:
            if not self._loop_running or self._abort_flag.is_set():
                return
            simple_keys = [k for k in slot_profiles[slot.index].get("buff_keys", []) if k]
            if not simple_keys:
                continue
            self._activate(slot.window_id)
            for key in simple_keys:
                if not self._loop_running:
                    return
                key_to_focused(key)
                time.sleep(key_delay)

        max_devices = max(
            (len(p.get("buff_devices", [])) for p in slot_profiles.values()), default=0
        )
        for di in range(max_devices):
            if not self._loop_running or self._abort_flag.is_set():
                return

            round_slots = []
            for slot in secondary:
                devices = slot_profiles[slot.index].get("buff_devices", [])
                if di < len(devices) and devices[di].get("key"):
                    round_slots.append((slot, devices[di]))
            if not round_slots:
                continue

            targeted = [
                (s, d) for s, d in round_slots if [t for t in d.get("targets", []) if t]
            ]
            targetless = [
                (s, d) for s, d in round_slots if not [t for t in d.get("targets", []) if t]
            ]

            # Targeted devices: target-outer, interleaved across slots so a
            # single cast_time wait covers everyone in the round.
            if targeted:
                max_targets = max(
                    len([t for t in d.get("targets", []) if t]) for _, d in targeted
                )
                for ti in range(max_targets):
                    if not self._loop_running or self._abort_flag.is_set():
                        return
                    for slot, device in targeted:
                        targets = [t for t in device.get("targets", []) if t]
                        if ti >= len(targets):
                            continue
                        self._activate(slot.window_id)
                        key_to_focused(targets[ti])
                        time.sleep(key_delay)
                        key_to_focused(device["key"])
                        time.sleep(key_delay)

                    max_cast = max(
                        float(d.get("cast_time_s", 0.0)) for _, d in targeted
                    )
                    if max_cast > 0:
                        time.sleep(max_cast)

                    for slot, device in targeted:
                        if not self._loop_running:
                            return
                        if device.get("reassist", True):
                            self._do_assist_fire(slot, assist_per, fire_key, key_delay)

            # Targetless devices (group/self buff): per-slot, can't interleave
            for slot, device in targetless:
                if not self._loop_running or self._abort_flag.is_set():
                    return
                cast_time = float(device.get("cast_time_s", 0.0))
                self._activate(slot.window_id)
                key_to_focused(device["key"])
                if cast_time > 0:
                    time.sleep(cast_time)
                    if device.get("reassist", True):
                        self._do_assist_fire(slot, assist_per, fire_key, key_delay)
                else:
                    time.sleep(key_delay)

    def _do_assist_fire(self, slot, assist_per, fire_key, key_delay):
        """Click assist target then press fire key for one slot."""
        coord_idx = slot.index
        if 0 <= coord_idx < len(assist_per):
            ax = assist_per[coord_idx].get("x_pct", 0.0)
            ay = assist_per[coord_idx].get("y_pct", 0.0)
            if ax or ay:
                win = get_window_by_id(slot.window_id)
                wx = win["x"] if win else slot.x
                wy = win["y"] if win else slot.y
                ww = win["w"] if win else slot.w
                wh = win["h"] if win else slot.h
                click_at(int(wx + ax * ww), int(wy + ay * wh))
                time.sleep(key_delay)
                self._activate(slot.window_id)
        if fire_key:
            key_to_focused(fire_key)
            time.sleep(key_delay)

    def _daimyo_mode_text(self):
        mode = self.settings.get("daimyo_mode", 1)
        return f"⚗  Daimyo Mode {mode}"

    def _toggle_daimyo_mode(self):
        current = self.settings.get("daimyo_mode", 1)
        new_mode = 2 if current == 1 else 1
        self.settings["daimyo_mode"] = new_mode
        self._daimyo_step_indices.clear()
        self._daimyo_step_last_times.clear()
        save_settings(self.settings)
        new_text = self._daimyo_mode_text()
        # Update normal view button
        for key, btn in self._action_btn_ordered:
            if key == "daimyo_mode_toggle":
                btn.config(text=new_text)
                break
        # Update compact view spec + rebuild
        for spec in self._compact_loop_specs:
            if spec[0] == "c_daimyo_mode":
                spec[1] = new_text
                break
        self._rebuild_compact_loop_buttons()
        self._set_status(f"Daimyo Mode {new_mode} active")

    def _start_daimyo_action(self):
        mode = self.settings.get("daimyo_mode", 1)
        if mode == 2:
            self._start_daimyo_step()
        else:
            self._start_daimyo_loop()

    def _start_daimyo_step(self):
        if self._daimyo_running:
            self._set_status("Daimyo already running")
            return
        secondary = self._get_loop_slots()
        slot_profiles = {s.index: self._effective_profile(s) for s in secondary}
        participating = []
        for slot in secondary:
            profile = slot_profiles[slot.index]
            cls = profile.get("class", "")
            if cls == "PS" and profile.get("daimyo_key"):
                participating.append(slot)
            elif profile.get("fotw_enabled") and profile.get("fotw_key"):
                participating.append(slot)
        if not participating:
            self._set_status("No secondary slot has Daimyo (PS) or FotW configured")
            return
        self._abort_flag.clear()
        self._daimyo_running = True
        self._set_status("Daimyo step…")
        threading.Thread(target=self._daimyo_step_thread, daemon=True).start()

    def _daimyo_step_thread(self):


        try:
            self._loop_active_wid = None
            wait_modifiers_released()
            release_modifiers()
            loops = self.settings.get("loops", {})
            key_delay = self._raid_ms(loops.get("key_delay_ms", 300)) / 1000.0
            fire_key = loops.get("fire_key", "f")
            assist_per = loops.get("assist_per_window", [])
            slots = self._get_loop_slots()
            slot_profiles = {s.index: self._effective_profile(s) for s in slots}
            for slot in slots:
                if not self._daimyo_running or self._abort_flag.is_set():
                    break
                profile = slot_profiles[slot.index]
                cls = profile.get("class", "")
                if cls == "PS" and profile.get("daimyo_key"):
                    dev_key = profile["daimyo_key"]
                    targets = [t for t in profile.get("daimyo_targets", []) if t]
                    interval = float(profile.get("daimyo_interval_s", 30.0))
                elif profile.get("fotw_enabled") and profile.get("fotw_key"):
                    dev_key = profile["fotw_key"]
                    targets = [t for t in profile.get("fotw_targets", []) if t]
                    interval = float(profile.get("fotw_interval_s", 6.0))
                else:
                    continue

                now = time.time()
                if now - self._daimyo_step_last_times.get(slot.index, 0) < interval:
                    continue

                self._activate(slot.window_id)

                if targets:
                    idx = self._daimyo_step_indices.get(slot.index, 0) % len(targets)
                    key_to_focused(targets[idx])
                    time.sleep(key_delay)
                    self._daimyo_step_indices[slot.index] = (idx + 1) % len(targets)

                key_to_focused(dev_key)
                time.sleep(key_delay)
                self._do_assist_fire(slot, assist_per, fire_key, key_delay)
                self._daimyo_step_last_times[slot.index] = time.time()

            driver = self._get_driver_slot()
            if driver.is_assigned:
                return_to_driver(driver.window_id, driver.x + driver.w // 2, driver.y + driver.h // 2)

        except Exception as e:
            print(f"[daimyo_step] error: {e}")
        finally:
            self._daimyo_running = False
            self.root.after(0, lambda: self._set_status("Daimyo step ✓"))

    def _start_daimyo_loop(self):
        if self._daimyo_running:
            self._set_status("Daimyo loop already running")
            return
        slot = self._get_driver_slot()
        if not slot.is_assigned:
            self._set_status("No client in the current driver slot")
            return
        profile = self._effective_profile(slot)
        is_fotw = profile.get("fotw_enabled") and profile.get("fotw_key")
        has_daimyo = bool(profile.get("daimyo_key"))
        if not is_fotw and not has_daimyo:
            self._set_status("Current driver slot has no Daimyo or FotW configured")
            return
        self._abort_flag.clear()
        self._daimyo_running = True
        label = "FotW" if is_fotw else "Daimyo"
        self._set_status(f"{label} loop running…")
        threading.Thread(
            target=self._daimyo_loop_thread, args=([slot],), daemon=True
        ).start()

    def _daimyo_loop_thread(self, slots):


        try:
            self._loop_active_wid = None
            wait_modifiers_released()
            release_modifiers()
            loops = self.settings.get("loops", {})
            key_delay = self._raid_ms(loops.get("key_delay_ms", 300)) / 1000.0
            fire_key = loops.get("fire_key", "f")
            assist_per = loops.get("assist_per_window", [])
            fotw_done = set()
            slot_profiles = {s.index: self._effective_profile(s) for s in slots}

            while self._daimyo_running and not self._abort_flag.is_set():
                has_daimyo = False
                for slot in slots:
                    if not self._daimyo_running or self._abort_flag.is_set():
                        break
                    profile = slot_profiles[slot.index]
                    is_fotw = profile.get("fotw_enabled") and profile.get("fotw_key")

                    if is_fotw:
                        if id(slot) in fotw_done:
                            continue
                        dev_key = profile["fotw_key"]
                        targets = [t for t in profile.get("fotw_targets", []) if t]
                        interval = float(profile.get("fotw_interval_s", 6.0))
                        self._daimyo_buff_targets(
                            slot, dev_key, targets, interval, assist_per, fire_key, key_delay,
                        )
                        fotw_done.add(id(slot))
                    else:
                        dev_key = profile.get("daimyo_key", "")
                        if not dev_key:
                            continue
                        has_daimyo = True
                        targets = [t for t in profile.get("daimyo_targets", []) if t]
                        interval = float(profile.get("daimyo_interval_s", 30.0))
                        self._daimyo_buff_targets(
                            slot, dev_key, targets, interval, assist_per, fire_key, key_delay,
                        )

                if not has_daimyo:
                    break

        except Exception as e:
            print(f"[daimyo] error: {e}")
        finally:
            self._daimyo_running = False
            self.root.after(0, lambda: self._set_status("Daimyo loop stopped"))

    def _daimyo_buff_targets(
        self, slot, dev_key, targets, interval, assist_per, fire_key, key_delay
    ):
        """F-key → device key → assist click → fire → wait interval. Repeated per target."""


        if not targets:
            self._activate(slot.window_id)
            key_to_focused(dev_key)
            time.sleep(key_delay)
            self._do_assist_fire(slot, assist_per, fire_key, key_delay)
            deadline = time.time() + interval
            while time.time() < deadline:
                if not self._daimyo_running or self._abort_flag.is_set():
                    return
                time.sleep(0.25)
            return
        for target_key in targets:
            if not self._daimyo_running or self._abort_flag.is_set():
                break
            self._activate(slot.window_id)
            key_to_focused(target_key)
            time.sleep(key_delay)
            key_to_focused(dev_key)
            time.sleep(key_delay)
            self._do_assist_fire(slot, assist_per, fire_key, key_delay)
            deadline = time.time() + interval
            while time.time() < deadline:
                if not self._daimyo_running or self._abort_flag.is_set():
                    return
                time.sleep(0.25)

    def _start_energy_loop(self):
        if self._loop_running or self._energy_running:
            return
        secondary = self._get_loop_slots()
        if not secondary:
            self._set_status("No secondary slots assigned")
            return
        self._abort_flag.clear()
        self._energy_running = True
        self._set_status("Energy loop running…")
        threading.Thread(
            target=self._energy_loop_thread, args=(secondary,), daemon=True
        ).start()

    def _energy_loop_thread(self, secondary):
        try:
            self._loop_active_wid = None
            wait_modifiers_released()
            release_modifiers()
            loops = self.settings.get("loops", {})
            key_delay = self._raid_ms(loops.get("key_delay_ms", 300)) / 1000.0
            fire_key = loops.get("fire_key", "f")
            assist_per = loops.get("assist_per_window", [])
            slot_profiles = {s.index: self._effective_profile(s) for s in secondary}
            # Energy keys
            for slot in secondary:
                if self._abort_flag.is_set():
                    break
                profile = slot_profiles[slot.index]
                keys = [k for k in profile.get("energy_keys", []) if k]
                if not keys:
                    continue
                self._activate(slot.window_id)
                for key in keys:
                    key_to_focused(key)
                    time.sleep(key_delay)

            # PV9 — one pass through slots that have it enabled
            if not self._abort_flag.is_set():
                time.sleep(0.1)
            for slot in secondary:
                if self._abort_flag.is_set():
                    break
                profile = slot_profiles[slot.index]
                if not profile.get("pv9_enabled") or not profile.get("pv9_key"):
                    continue
                pv9_key = profile["pv9_key"]
                targets = profile.get("pv9_targets", [])
                if not targets:
                    self._activate(slot.window_id)
                    key_to_focused(pv9_key)
                    time.sleep(key_delay)
                    self._do_assist_fire(slot, assist_per, fire_key, key_delay)
                else:
                    for target_key in targets:
                        if self._abort_flag.is_set():
                            break
                        self._activate(slot.window_id)
                        key_to_focused(target_key)
                        time.sleep(key_delay)
                        key_to_focused(pv9_key)
                        time.sleep(key_delay)
                        self._do_assist_fire(slot, assist_per, fire_key, key_delay)

            # Return focus to driver
            driver = self._get_driver_slot()
            if driver.is_assigned:
                cx = driver.x + driver.w // 2
                cy = driver.y + driver.h // 2
                return_to_driver(driver.window_id, cx, cy)

        except Exception as e:
            print(f"[energy] error: {e}")
        finally:
            self._energy_running = False
            self.root.after(0, lambda: self._set_status("Energy loop complete ✓"))

    # ── Profile management ────────────────────────────────────

    def _load_profile(self, name: str):
        profile = load_profile(name)
        self.slots.from_list(profile.get("slots", []))
        if self._cycle_mgr is not None:
            self._cycle_mgr.reset()
        self.profile_var.set(name)
        self.settings["active_profile"] = name
        self._refresh_slot_cards()
        self._redraw_canvas()
        self._set_status(f"Profile loaded: {name}")

    def _save_current_profile(self):
        name = self.profile_var.get() or "default"
        profile = load_profile(name)
        profile["slots"] = self.slots.to_list()
        save_profile(profile)
        self._set_status(f"Profile saved: {name}")

    def _new_profile(self):
        name = simpledialog.askstring("New Profile", "Profile name:", parent=self.root)
        if not name:
            return
        save_profile(default_group_profile(name))
        profiles = list_profiles()
        self.profile_combo.configure(values=profiles)
        self._load_profile(name)

    def _delete_profile(self):
        name = self.profile_var.get()
        if not name:
            return
        if name == "default":
            messagebox.showwarning(
                "Delete Profile", "Cannot delete the default profile."
            )
            return
        if not messagebox.askyesno(
            "Delete Profile", f"Delete profile '{name}'? This cannot be undone."
        ):
            return
        delete_profile(name)
        profiles = list_profiles() or ["default"]
        self.profile_combo.configure(values=profiles)
        self._load_profile(profiles[0])
        self._set_status(f"Profile deleted: {name}")

    # ── Settings window ───────────────────────────────────────

    def _capture_click(self, callback):
        """Show a floating instruction bar. User hovers over the target in the game window,
        then presses Space to confirm. Calls callback(x_pct, y_pct) or callback(None, None)."""
        mon   = self.monitors[0] if self.monitors else {"x": 0, "y": 0, "w": 1920}
        ow    = 480
        ox    = mon["x"] + (mon["w"] - ow) // 2
        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{ow}x64+{ox}+8")
        overlay.configure(bg=tk_color("panel_bg"),
                          highlightthickness=2,
                          highlightbackground=tk_color("accent"))

        tk.Label(overlay,
                 text="Hover over the target  →  press Space to set",
                 bg=tk_color("panel_bg"), fg=tk_color("accent"),
                 font=THEME["font_main"]).pack(pady=(8, 2))
        tk.Label(overlay,
                 text="Escape to cancel",
                 bg=tk_color("panel_bg"), fg=tk_color("text_dim"),
                 font=THEME["font_small"]).pack()

        def _confirm(event=None):
            cx = overlay.winfo_pointerx()
            cy = overlay.winfo_pointery()
            overlay.destroy()
            x_pct, y_pct = None, None
            for i in range(MAX_SLOTS):
                slot = self.slots.slot(i)
                if not slot.is_assigned or not slot.window_id:
                    continue
                win = get_window_by_id(slot.window_id)
                if not win:
                    continue
                if win["x"] <= cx < win["x"] + win["w"] and win["y"] <= cy < win["y"] + win["h"]:
                    x_pct = (cx - win["x"]) / win["w"]
                    y_pct = (cy - win["y"]) / win["h"]
                    break
            callback(x_pct, y_pct)

        def _cancel(event=None):
            overlay.destroy()
            callback(None, None)

        overlay.bind("<space>", _confirm)
        overlay.bind("<Escape>", _cancel)
        overlay.grab_set()
        overlay.focus_force()

    def _open_settings_window(self):
        from gui_settings import SettingsWindow

        sw = SettingsWindow(
            self.root, self.settings, self._on_settings_saved,
            monitors=self.monitors,
            drag_mode_toggle=self._toggle_indicator_drag_mode,
            capture_click=self._capture_click,
        )
        self._active_settings_win = sw
        sw.win.bind('<Destroy>', lambda e: setattr(self, '_active_settings_win', None))

    def _rebuild_canvas_only(self, parent):
        """Build just the canvas widget inside parent — no controls."""
        self._aspect_updating = False
        self.canvas = tk.Canvas(
            parent,
            bg="#0d0d1a",
            height=200,
            highlightthickness=1,
            highlightbackground=tk_color("slot_border"),
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self._drag_slot = None
        self._drag_offset = (0, 0)
        self._drag_resize = False
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self._canvas_mouse_down)
        self.canvas.bind("<B1-Motion>", self._canvas_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._canvas_mouse_up)
        self.canvas.bind("<Button-3>", self._canvas_right_click)

    # ── Hotkeys ───────────────────────────────────────────────

    def _bind_hotkeys(self):
        """Start global hotkey listener via pynput."""
        from cycle_manager import CycleManager
        from hotkey_manager import HotkeyManager

        self._cycle_mgr = CycleManager(self.slots, self.settings)
        self._hk_mgr = HotkeyManager()

        # Register all actions
        self._hk_mgr.register(
            "cycle_next", lambda: self.root.after(0, self._cycle_next)
        )
        self._hk_mgr.register(
            "cycle_prev", lambda: self.root.after(0, self._cycle_prev)
        )
        self._hk_mgr.register(
            "slot_driver", lambda: self.root.after(0, self._cycle_return_driver)
        )
        for i in range(MAX_SLOTS):
            self._hk_mgr.register(
                f"slot_{i+1}", lambda idx=i: self.root.after(0, lambda: self._cycle_to(idx))
            )
        self._hk_mgr.register(
            "combat_loop",
            lambda: self.root.after(0, lambda: self._start_loop("combat")),
        )
        self._hk_mgr.register(
            "buff_loop", lambda: self.root.after(0, lambda: self._start_loop("buff"))
        )
        self._hk_mgr.register(
            "debuff_cycle",
            lambda: self.root.after(0, lambda: self._start_loop("debuff")),
        )
        self._hk_mgr.register(
            "heal_cycle", lambda: self.root.after(0, lambda: self._start_loop("heal"))
        )
        self._hk_mgr.register(
            "energy_loop", lambda: self.root.after(0, self._start_energy_loop)
        )
        self._hk_mgr.register(
            "daimyo_loop", lambda: self.root.after(0, self._start_daimyo_action)
        )
        self._hk_mgr.register(
            "daimyo_step", lambda: self.root.after(0, self._start_daimyo_action)
        )
        self._hk_mgr.register("abort", lambda: self.root.after(0, self._abort_and_stop))
        self._hk_mgr.register("invite", lambda: self.root.after(0, self._run_invite))
        self._hk_mgr.register("reform", lambda: self.root.after(0, self._run_reform))
        self._hk_mgr.register(
            "assign_driver", lambda: self.root.after(0, self._assign_driver)
        )
        self._hk_mgr.register(
            "manager_front", lambda: self.root.after(0, self._bring_to_front)
        )

        # Start listener
        self._hk_mgr.start(self.settings.get("hotkeys", {}))

        # Also keep tkinter Escape binding as fallback
        try:
            self.root.bind_all("<Escape>", lambda _: self._stop_loop())
        except Exception:
            pass

    def _cycle_will_return_to_driver(self, direction: str) -> bool:
        """True if the next cycle op will call _return_to_driver_impl."""
        if self._cycle_mgr is None or self._cycle_mgr._swapped_slot is None:
            return False
        secondary = [s for s in self.slots.assigned_slots() if s.index != 0]
        idxs = [s.index for s in secondary]
        if self._cycle_mgr._swapped_slot not in idxs:
            return False
        pos = idxs.index(self._cycle_mgr._swapped_slot)
        if direction == "next":
            return pos == len(idxs) - 1
        if direction == "prev":
            return pos == 0
        return False

    def _cycle_next(self):
        going_to_driver = self._cycle_will_return_to_driver("next")
        self._indicator_cycling = going_to_driver
        t = threading.Thread(
            target=self._cycle_mgr.cycle_next, args=(self.monitors,), daemon=True
        )
        t.start()
        self._set_status("Cycling to next window")
        self._redraw_canvas()
        if going_to_driver:
            self.root.after(100, self._poll_cycle_indicator)
        else:
            self.root.after(150, self._update_omit_indicator)

    def _cycle_prev(self):
        going_to_driver = self._cycle_will_return_to_driver("prev")
        self._indicator_cycling = going_to_driver
        t = threading.Thread(
            target=self._cycle_mgr.cycle_prev, args=(self.monitors,), daemon=True
        )
        t.start()
        self._set_status("Cycling to previous window")
        self._redraw_canvas()
        if going_to_driver:
            self.root.after(100, self._poll_cycle_indicator)
        else:
            self.root.after(150, self._update_omit_indicator)

    def _cycle_return_driver(self):
        self._indicator_cycling = True
        t = threading.Thread(
            target=self._cycle_mgr.return_to_driver, args=(self.monitors,), daemon=True
        )
        t.start()
        self._set_status("Returned to driver")
        self._redraw_canvas()
        self.root.after(100, self._poll_cycle_indicator)

    def _cycle_to(self, slot_index: int):
        self._indicator_cycling = True
        t = threading.Thread(
            target=self._cycle_mgr.cycle_to_slot,
            args=(slot_index, self.monitors),
            daemon=True,
        )
        t.start()
        self._set_status(f"Cycling to slot {slot_index + 1}")
        self._redraw_canvas()
        self.root.after(100, self._poll_cycle_indicator)

    def _poll_cycle_indicator(self, attempts: int = 0):
        """Wait for cycle lock to release then write indicator state."""
        if self._cycle_mgr is None or not self._cycle_mgr._cycle_lock.locked():
            self._indicator_cycling = False
            self._write_indicator_state()
        elif attempts < 40:
            self.root.after(100, lambda: self._poll_cycle_indicator(attempts + 1))
        else:
            self._indicator_cycling = False
            self._write_indicator_state()

    def _apply_key_timing(self):
        loops = self.settings.get("loops", {})
        configure_key_timing(
            hold_ms=self._raid_ms(loops.get("key_hold_ms", 30)),
            mod_delay_ms=self._raid_ms(loops.get("modifier_delay_ms", 50)),
        )

    def _raid_ms(self, ms: float) -> float:
        """Return ms scaled by the current raid factor, or unchanged if raid mode is off."""
        return ms * self._raid_factor if self._raid_mode else ms

    def _activate_settle_s(self) -> float:
        """Delay after activate_window before sending input.

        Window activation under Wine/X11 appears to trigger a focus-state
        transition that can drop a character out of formation if input
        (especially with Autofollow engaged) lands too soon afterward.
        Tunable via loops.activate_settle_ms (and the _2x/_3x raid-mode
        variants) — set independently per raid mode, not scaled by
        _raid_ms()."""
        loops = self.settings.get("loops", {})
        key, default = {1: ("activate_settle_ms", 300),
                         2: ("activate_settle_ms_2x", 400),
                         3: ("activate_settle_ms_3x", 500)}[self._raid_factor]
        return loops.get(key, default) / 1000.0

    def _activate(self, wid: int) -> None:
        """Activate a window, waiting the long settle only if this switches
        focus away from whatever window was last activated by the loop.
        Re-activating the same window (e.g. re-focus after a click) uses a
        short delay instead."""
        is_switch = wid != getattr(self, "_loop_active_wid", None)
        activate_window(wid)
        self._loop_active_wid = wid
        time.sleep(self._activate_settle_s() if is_switch else 0.1)

    def _fmt_hotkey(self, hk_key: str) -> str:
        """Return a display string like '  [Alt+F]' for a hotkey settings key, or ''."""
        if not hk_key:
            return ""
        raw = self.settings.get("hotkeys", {}).get(hk_key) or DEFAULT_HOTKEYS.get(hk_key, "")
        if not raw:
            return ""
        _abbrev = {
            "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Super",
            "escape": "Esc", "return": "Enter", "grave": "`",
            "tab": "Tab", "space": "Space",
            "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
            "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
            "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
        }
        parts = raw.split("+")
        display = "+".join(
            _abbrev.get(p.lower(), p.upper() if len(p) == 1 else p.capitalize())
            for p in parts
        )
        return f"  [{display}]"

    def _on_raid_mode_change(self):
        mode = self._raid_var.get()
        self.settings["raid_mode"] = mode
        self._raid_mode = mode != "off"
        self._raid_factor = {"off": 1, "2x": 2, "3x": 3}.get(mode, 1)
        self._apply_key_timing()
        label = {"off": "Off", "2x": "2×", "3x": "3×"}.get(mode, mode)
        self._set_status(f"Raid Mode: {label}")

    def _restart_app(self):
        """Save and relaunch the manager."""
        import subprocess
        import sys
        self._stop_loop()
        if self._hk_mgr:
            self._hk_mgr.stop()
        self._kill_omit_indicator()
        self._save_current_profile()
        save_settings(self.settings)
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        subprocess.Popen([sys.executable, script])
        self.root.destroy()

    def _open_button_visibility_editor(self):
        """Dialog to show/hide buttons for the current view mode."""
        in_compact = self._compact_mode
        dlg = tk.Toplevel(self.root)
        dlg.title("Button Visibility — " + ("compact" if in_compact else "normal") + " mode")
        dlg.configure(bg=tk_color("bg"))
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        _center_on_parent(dlg, self.root)

        tk.Label(
            dlg, text="Visible buttons in " + ("compact" if in_compact else "normal") + " mode:",
            bg=tk_color("bg"), fg=tk_color("text"), font=THEME["font_small"],
        ).pack(padx=14, pady=(12, 4), anchor="w")

        check_vars = {}

        if in_compact:
            vis = self.settings.setdefault("compact_ui_buttons", {})
            all_specs = (
                [(k, t) for k, t, *_ in self._compact_loop_specs]
                + [(k, t) for k, t, *_ in self._compact_util_specs]
            )
            for key, text in all_specs:
                var = tk.BooleanVar(value=vis.get(key, True))
                check_vars[key] = var
                tk.Checkbutton(
                    dlg, text=text, variable=var,
                    bg=tk_color("bg"), fg=tk_color("text"),
                    selectcolor=tk_color("card_bg"),
                    activebackground=tk_color("bg"),
                    font=THEME["font_main"], anchor="w",
                ).pack(fill="x", padx=16, pady=1)

            def _apply():
                for key, var in check_vars.items():
                    vis[key] = var.get()
                self._rebuild_compact_loop_buttons()
                self._rebuild_compact_util_buttons()
                dlg.destroy()
        else:
            vis = self.settings.setdefault("ui_buttons", {})
            mode = "normal"
            for key, btn in self._action_btn_ordered:
                var = tk.BooleanVar(value=vis.get(key, {}).get(mode, True))
                check_vars[key] = var
                tk.Checkbutton(
                    dlg, text=btn.cget("text"), variable=var,
                    bg=tk_color("bg"), fg=tk_color("text"),
                    selectcolor=tk_color("card_bg"),
                    activebackground=tk_color("bg"),
                    font=THEME["font_main"], anchor="w",
                ).pack(fill="x", padx=16, pady=1)

            def _apply():
                for key, var in check_vars.items():
                    vis.setdefault(key, {})["normal"] = var.get()
                self._apply_button_visibility()
                dlg.destroy()

        tk.Button(
            dlg, text="Apply", command=_apply,
            bg=tk_color("accent"), fg="white",
            font=THEME["font_main"], relief="flat", pady=4,
        ).pack(fill="x", padx=14, pady=10)
        dlg.wait_window()

    def _apply_button_visibility(self):
        """Show/hide action buttons based on ui_buttons settings and current mode."""
        if not self._action_btn_ordered:
            return
        vis = self.settings.get("ui_buttons", {})
        mode = "compact" if self._compact_mode else "normal"
        # Forget all first to maintain pack order, then re-pack visible ones
        for _key, btn in self._action_btn_ordered:
            btn.pack_forget()
        for key, btn in self._action_btn_ordered:
            if vis.get(key, {}).get(mode, True):
                btn.pack(fill="x", pady=2)

    def _on_settings_saved(self, new_settings: dict):
        self.settings = new_settings
        save_settings(new_settings)
        self._apply_key_timing()
        if hasattr(self, "_hk_mgr"):
            self._hk_mgr.restart(new_settings.get("hotkeys", {}))
        if hasattr(self, "_cycle_mgr") and self._cycle_mgr:
            self._cycle_mgr.settings = new_settings
        if hasattr(self, "_action_btn_meta"):
            for key, btn in self._action_btn_ordered:
                base_text, hk_key = self._action_btn_meta.get(key, ("", ""))
                btn.config(text=base_text + self._fmt_hotkey(hk_key))
        self._apply_omit_indicator_settings()
        self._set_status("Settings saved")

    # ── On-Main Indicator ─────────────────────────────────────

    def _build_omit_indicator(self):
        """Spawn the transparent overlay subprocess for the slot indicator."""
        import subprocess
        import sys
        import tempfile
        import glob
        import psutil
        # Kill any orphaned overlay processes from previous sessions
        try:
            for proc in psutil.process_iter(["pid", "cmdline"]):
                try:
                    cmd = " ".join(proc.info["cmdline"] or [])
                    if "omit_indicator_overlay" in cmd:
                        proc.terminate()
                except Exception:
                    pass
        except Exception:
            pass
        # Clean up all stale indicator temp files from previous sessions
        _tmp = tempfile.gettempdir()
        for stale in glob.glob(os.path.join(_tmp, 'enbmb-indicator-*.json')):
            try:
                os.remove(stale)
            except OSError:
                pass
        fd, path = tempfile.mkstemp(suffix='.json', prefix='enbmb-indicator-')
        os.close(fd)
        fd2, drag_path = tempfile.mkstemp(suffix='.json', prefix='enbmb-indicator-drag-')
        os.close(fd2)
        self._omit_state_file = path
        self._omit_drag_file  = drag_path
        self._omit_drag_mtime = 0
        self._indicator_drag_mode = False
        self._omit_proc = None
        _overlay_file = ('omit_indicator_overlay_windows.py' if sys.platform == 'win32'
                         else 'omit_indicator_overlay.py')
        overlay = os.path.join(os.path.dirname(os.path.abspath(__file__)), _overlay_file)
        if os.path.exists(overlay):
            self._omit_proc = subprocess.Popen(
                [sys.executable, overlay, path, drag_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        self._apply_omit_indicator_settings()
        self.root.after(200, self._check_indicator_drag)

    def _kill_omit_indicator(self):
        proc = self._omit_proc
        if proc and proc.poll() is None:
            proc.terminate()
        for attr in ('_omit_state_file', '_omit_drag_file'):
            path = getattr(self, attr, None)
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _toggle_indicator_drag_mode(self):
        self._indicator_drag_mode = not self._indicator_drag_mode
        self._write_indicator_state()
        return self._indicator_drag_mode

    def _check_indicator_drag(self):
        path = self._omit_drag_file
        if path and os.path.exists(path):
            try:
                mtime = os.path.getmtime(path)
                if mtime != self._omit_drag_mtime:
                    self._omit_drag_mtime = mtime
                    import json as _json
                    with open(path) as f:
                        data = _json.load(f)
                    x = int(data.get('x', 20))
                    y = int(data.get('y', 280))
                    cfg = self.settings.setdefault('omit_indicator', {})
                    cfg['x'] = x
                    cfg['y'] = y
                    save_settings(self.settings)
                    self._indicator_drag_mode = False
                    self._write_indicator_state()
                    # push into open settings dialog so Save picks up the dragged position
                    sw = self._active_settings_win
                    if sw is not None:
                        try:
                            sw._ind_x_var.set(str(x))
                            sw._ind_y_var.set(str(y))
                            sw._ind_drag_btn.config(text="Move indicator")
                        except Exception:
                            pass
            except Exception:
                pass
        self.root.after(200, self._check_indicator_drag)

    def _get_omit_text(self) -> str:
        cfg = self.settings.get("omit_indicator", {})
        content = cfg.get("content", "slot")
        try:
            # Show whoever is currently on the main monitor, not the permanent
            # (Alt+G) driver. cycle_manager always restores slot 0 to the main
            # monitor when nothing is swapped, regardless of _driver_idx.
            if self._cycle_mgr is not None and self._cycle_mgr._swapped_slot is not None:
                slot = self.slots.slot(self._cycle_mgr._swapped_slot)
            else:
                slot = self.slots.slot(0)
        except Exception:
            return "1"
        if content == "role":
            return slot.role or str(slot.index + 1)
        elif content == "char_name":
            return slot.char_name or slot.character or str(slot.index + 1)
        return str(slot.index + 1)

    def _write_indicator_state(self):
        import json
        path = self._omit_state_file
        if not path:
            return
        cfg = self.settings.get("omit_indicator", {})
        has_window = any(s.is_assigned for s in self.slots.slots)
        if not cfg.get("enabled", False) or not has_window:
            state = {"enabled": False}
        else:
            state = {
                "enabled":    True,
                "text":       self._get_omit_text(),
                "x":          int(cfg.get("x", 20)),
                "y":          int(cfg.get("y", 280)),
                "drag_mode":  self._indicator_drag_mode,
                "font_size":  max(8, int(cfg.get("font_size", 48))),
                "text_color": cfg.get("text_color", "#ffffff"),
                "opacity":    max(0.1, min(1.0, float(cfg.get("opacity", 0.85)))),
            }
        with open(path, 'w') as f:
            json.dump(state, f)

    def _update_omit_indicator(self):
        """Refresh indicator text and position after a driver change."""
        if not self.settings.get("omit_indicator", {}).get("enabled", False):
            return
        if self._indicator_cycling:
            return  # poll will write when cycle completes
        self._write_indicator_state()

    def _apply_omit_indicator_settings(self):
        """Apply all indicator settings (called on startup and after save)."""
        self._write_indicator_state()

    # ── Liveness monitor ──────────────────────────────────────

    def _start_liveness_monitor(self):
        """Periodically check if assigned windows still exist."""

        def _check():
            try:
                self.slots.check_liveness()
            except Exception:
                pass
            finally:
                self.root.after(6000, _check)

        self.root.after(6000, _check)

    def _on_monitor_crash(self, slot_num: int, prev_state: str, new_state: str):
        """Called from the monitor thread (via root.after) on every state transition."""
        is_crash       = new_state in ("OFFLINE", "LOGIN SCREEN") and prev_state in ("IN GAME", "ZONING", "FROZEN?", "CRASHED?")
        is_zone_freeze = new_state == "ZONE FREEZE"
        if not is_crash and not is_zone_freeze:
            return
        if not self.settings.get("auto_relaunch", False):
            return
        if is_zone_freeze and not self.settings.get("zone_freeze_enabled", False):
            return
        # Capture on the main thread (this callback runs via root.after) — the
        # debounce timer that follows runs on a background thread, where reading
        # Tkinter vars is unsafe.
        self._crash_relaunch_autologin = bool(self.autologin_var.get())
        index = slot_num - 1
        slot  = self.slots.slot(index)
        if not slot or not slot.is_assigned or not slot.username or index in self._relaunching:
            return
        # Capture which slots were assigned at the moment the first crash fires,
        # before check_liveness() can clear them and make the set look empty.
        if not self._pending_crashes:
            self._crashes_assigned = {s.index for s in self.slots.assigned_slots()}
        self._relaunching.add(index)
        self._pending_crashes.add(index)

        # Debounce: wait 2s to see if more slots crash. If all assigned slots
        # go down together, do a single pkill + Launch All instead of sequential
        # per-slot relaunches.
        if self._crash_debounce_timer:
            self._crash_debounce_timer.cancel()
        self._crash_debounce_timer = threading.Timer(2.0, self._process_crashes)
        self._crash_debounce_timer.daemon = True
        self._crash_debounce_timer.start()

    def _process_crashes(self):
        """Debounce callback: decide between global relaunch and per-slot relaunch."""
        if self._abort_flag.is_set():
            self._pending_crashes.clear()
            self._relaunching.clear()
            return
        crashes = self._pending_crashes.copy()
        self._pending_crashes.clear()
        assigned = self._crashes_assigned
        self._crashes_assigned = set()

        if assigned and crashes >= assigned:
            # All assigned slots crashed — pkill everything and Launch All.
            kill_all_enb_processes()
            # Clear slot records so _launch_all_clients sees them as unassigned.
            for i in range(MAX_SLOTS):
                self.slots.clear_slot(i)
            self._relaunching.clear()
            self.root.after(0, lambda: self._set_status(
                "Global crash detected — killing and relaunching all…"))
            self.root.after(0, self._refresh_slot_cards)
            self.root.after(0, self._redraw_canvas)
            self.root.after(2000, self._launch_all_clients)
        else:
            # Partial crash — relaunch individual slots.
            do_autologin = getattr(self, "_crash_relaunch_autologin", True)
            for index in crashes:
                if index not in self._relaunching:
                    self._relaunching.add(index)
                self._relaunch_slot_impl(index, do_autologin)

    def _relaunch_slot_impl(self, index: int, do_autologin: bool):
        """Start the per-slot relaunch thread (called by both manual and crash paths)."""
        threading.Thread(
            target=self._relaunch_slot_thread, args=(index, do_autologin), daemon=True
        ).start()

    # ── Utilities ─────────────────────────────────────────────

    def _configured_slot_indices(self) -> list[int]:
        """Return indices of slots that have any meaningful configuration."""
        return [
            i
            for i in range(MAX_SLOTS)
            if self.slots.slot(i).username
            or self.slots.slot(i).char_name
            or self.slots.slot(i).character
            or self.slots.slot(i).role
        ]

    def _launch_all_clients(self):
        """Launch clients for unassigned slots, then auto-detect and apply layout."""
        configured = self._configured_slot_indices() or [0]
        unassigned = [i for i in configured if not self.slots.slot(i).is_assigned]
        if not unassigned:
            self._set_status(
                "All slots already assigned — use Quit to Desktop or Kill All first"
            )
            return
        # Capture on the main thread — reading Tkinter vars from background threads is unsafe.
        do_autologin = bool(self.autologin_var.get())

        def _do_launch():
            try:
                _do_launch_inner()
            except Exception as e:
                import traceback
                self.root.after(0, lambda e=e: self._set_status(f"Launch error: {e}"))
                print("[launch] EXCEPTION in _do_launch:", traceback.format_exc())

        def _do_launch_inner():
            launch_delay = self.settings.get("launch_delay_ms", 3000) / 1000.0
            known_ids = {w["id"] for w in find_enb_windows()}
            for n, i in enumerate(unassigned):
                if self._abort_flag.is_set():
                    return
                cmd = self._slot_command(i)
                self.root.after(
                    0, lambda i=i: self._set_status(f"Slot {i + 1}: waiting for EULA…")
                )
                launch_enb_client(cmd)
                # The first launcher of a session does an uncached
                # server-status check before Enter actually dismisses it —
                # wait longer before pressing Enter on the first slot.
                pre_enter_delay = 3.0 if n == 0 else 2.0
                self._dismiss_launcher_if_present(known_ids, pre_enter_delay=pre_enter_delay)

                eula_wid = self._wait_for_eula_window(known_ids)
                if self._abort_flag.is_set():
                    return
                if eula_wid:
                    self.root.after(
                        0, lambda i=i: self._set_status(f"Slot {i + 1}: EULA — pressing Enter…")
                    )
                    self._dismiss_eula_window(eula_wid)
                    self.root.after(
                        0,
                        lambda i=i: self._set_status(
                            f"Slot {i + 1}: EULA dismissed, waiting {int(launch_delay * 1000)}ms…"
                        ),
                    )
                else:
                    self.root.after(
                        0, lambda i=i: self._set_status(f"Slot {i + 1}: window not detected, continuing…")
                    )

                login_wid, pid = self._find_login_window(known_ids, eula_wid, launch_delay)
                if self._abort_flag.is_set():
                    return
                if login_wid:
                    self.slots.assign_window_to_slot(i, login_wid, pid)
                else:
                    self.root.after(
                        0, lambda i=i: self._set_status(f"Slot {i + 1}: login window not found, skipping")
                    )
                known_ids = {w["id"] for w in find_enb_windows()}

            if self._abort_flag.is_set():
                return

            # Refresh UI with assigned slots, then wait for the last window's
            # Win32 message loop to be fully ready before applying layout.
            self.root.after(0, self._refresh_slot_cards)
            self.root.after(0, self._redraw_canvas)
            time.sleep(4.0)
            if self._layout_mode == "auto":
                self.root.after(0, lambda: self._auto_tile(apply=True))
            else:
                self.root.after(0, lambda: self._apply_layout(resize_driver=True))
            self.root.after(0, lambda: self._set_status("Launch complete ✓"))

            # If "Autologin on Launch All" is checked, kick off the full
            # login + character-select pass for slots that have credentials.
            if do_autologin:
                time.sleep(2.0)
                newly_launched = [self.slots.slot(i) for i in unassigned if self.slots.slot(i).is_assigned]
                with_creds = [s for s in newly_launched if s.username]
                if with_creds:
                    self.root.after(
                        0,
                        lambda n=len(with_creds): self._set_status(
                            f"Auto-login: {n} slot(s)…"
                        ),
                    )
                    threading.Thread(
                        target=self._auto_login_thread,
                        args=(with_creds,),
                        daemon=True,
                    ).start()

        threading.Thread(target=_do_launch, daemon=True).start()
        self._set_status(f"Launching {len(unassigned)} client(s)…")

    def _launch_updater(self):
        """Open the Net7 launcher GUI for updates."""
        import subprocess

        if sys.platform == "win32":
            exe = (self.settings.get("slot_commands") or [None])[0]
            if not exe or not os.path.exists(exe):
                messagebox.showinfo(
                    "Not Found",
                    "Net-7 launcher not found.\n"
                    "Check the slot launch command in Settings.",
                )
                return
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
            self._set_status("Net7 launcher opening…")
            return

        wineprefix = os.path.expanduser("~/.wine-enb")
        bindir = os.path.join(
            wineprefix, "drive_c", "Program Files (x86)", "Net-7", "bin"
        )
        exe = os.path.join(bindir, "LaunchNet7.exe")
        if not os.path.exists(exe):
            messagebox.showinfo(
                "Not Found",
                "Net-7 launcher not found in wine prefix.\n"
                "Run setup_prefixes.sh first.",
            )
            return
        env = {**os.environ, "WINEPREFIX": wineprefix}
        subprocess.Popen(
            ["/usr/bin/wine", exe],
            env=env,
            cwd=bindir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._set_status("Net7 launcher opening…")

        def _show_launcher():
            # Wine creates the window but doesn't map it — wait then force-show it
            deadline = time.time() + 15
            while time.time() < deadline:
                time.sleep(0.5)
                out = subprocess.run(
                    ["xdotool", "search", "--name", "LaunchNet7"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                if out:
                    for wid in out.splitlines():
                        subprocess.run(
                            ["xdotool", "windowmap", wid], capture_output=True
                        )
                        subprocess.run(
                            ["xdotool", "windowraise", wid], capture_output=True
                        )
                        subprocess.run(
                            ["xdotool", "windowactivate", wid], capture_output=True
                        )
                    self.root.after(0, lambda: self._set_status("Net7 launcher ready"))
                    return
            self.root.after(
                0, lambda: self._set_status("Net7 launcher: window not found")
            )

        threading.Thread(target=_show_launcher, daemon=True).start()

    def _mute_login_sounds(self):
        """Run mute_login_sounds.py to zero login/voice/footstep volumes in sounds.ini."""
        import subprocess

        script = os.path.join(os.path.dirname(__file__), "mute_login_sounds.py")
        if not messagebox.askyesno(
            "Mute Login Sounds",
            "Zero SoundVolume for all login, voice, and footstep entries in sounds.ini?\n\n"
            "This affects all clients (shared Program Files). A backup is created on first run.",
        ):
            return
        try:
            result = subprocess.run(
                [sys.executable, script], capture_output=True, text=True, timeout=15
            )
            out = result.stdout.strip() or result.stderr.strip() or "Done"
            self._set_status(out)
        except Exception as e:
            self._set_status(f"Mute failed: {e}")

    def _apply_dark_mode(self):
        """Run dark_mode_dazzle.py to remove star halo/dazzle/lensflare from Dazzle.ini."""
        import subprocess

        script = os.path.join(os.path.dirname(__file__), "dark_mode_dazzle.py")
        if not messagebox.askyesno(
            "Dark Mode",
            "Zero HaloScale/DazzleScale and remove LensflareName for all star types in Dazzle.ini?\n\n"
            "This affects all clients (shared Program Files). A backup is created on first run.",
        ):
            return
        try:
            result = subprocess.run(
                [sys.executable, script], capture_output=True, text=True, timeout=15
            )
            out = result.stdout.strip() or result.stderr.strip() or "Done"
            self._set_status(out)
        except Exception as e:
            self._set_status(f"Dark mode failed: {e}")

    def _apply_privacy_settings(self):
        """Run privacy_settings.py to set channel/login defaults in all player*_options.ini."""
        import subprocess

        script = os.path.join(os.path.dirname(__file__), "privacy_settings.py")
        if not messagebox.askyesno(
            "Privacy Settings",
            "Apply privacy defaults to all player*_options.ini files?\n\n"
            "• Hide login from non-friends (RestrictedStatus=yes)\n"
            "• Disable Broadcast, Local, and all race/class channels\n"
            "• Keep Guild, Group, and Private channels on\n\n"
            "⚠  All characters must be logged OUT before running.\n"
            "The game overwrites these files on logout — changes made\n"
            "while logged in will be lost.\n\n"
            "Affects all characters (shared Program Files).",
        ):
            return
        try:
            result = subprocess.run(
                [sys.executable, script], capture_output=True, text=True, timeout=15
            )
            out = result.stdout.strip() or result.stderr.strip() or "Done"
            self._set_status(out)
        except Exception as e:
            self._set_status(f"Privacy settings failed: {e}")

    def _save_game_settings(self):
        """Back up shortcut.ini and player*_options.ini from the shared game output dir."""
        import glob
        import shutil

        if sys.platform == "win32":
            try:
                from enb_path import get_enb_install_path
                src_dir = os.path.join(get_enb_install_path(), "Data", "client", "output")
            except Exception as e:
                messagebox.showerror("Save Settings", f"Cannot locate EnB install path:\n{e}")
                return
        else:
            src_dir = os.path.expanduser(
                "~/.wine-enb/drive_c/Program Files/EA GAMES/"
                "Earth & Beyond/Data/client/output"
            )
        bak_dir = os.path.join(
            os.path.dirname(__file__), "config", "game_settings_backup"
        )

        files = [os.path.join(src_dir, "shortcut.ini")] + glob.glob(
            os.path.join(src_dir, "player*_options.ini")
        )
        files = [f for f in files if os.path.exists(f)]

        if not files:
            messagebox.showwarning(
                "Save Settings", "No settings files found to back up."
            )
            return

        if os.path.isdir(bak_dir):
            if not messagebox.askyesno(
                "Save Settings",
                f"Overwrite existing backup in:\n{bak_dir}\n\n"
                f"Files: {', '.join(os.path.basename(f) for f in files)}",
            ):
                return
        else:
            os.makedirs(bak_dir, exist_ok=True)

        try:
            for f in files:
                shutil.copy2(f, bak_dir)
            self._set_status(f"Game settings saved ({len(files)} files) ✓")
        except Exception as e:
            messagebox.showerror("Save Settings", f"Failed to save:\n{e}")

    def _load_game_settings(self):
        """Restore shortcut.ini and player*_options.ini from backup into the game output dir."""
        import glob
        import shutil

        bak_dir = os.path.join(
            os.path.dirname(__file__), "config", "game_settings_backup"
        )
        if sys.platform == "win32":
            try:
                from enb_path import get_enb_install_path
                dst_dir = os.path.join(get_enb_install_path(), "Data", "client", "output")
            except Exception as e:
                messagebox.showerror("Load Settings", f"Cannot locate EnB install path:\n{e}")
                return
        else:
            dst_dir = os.path.expanduser(
                "~/.wine-enb/drive_c/Program Files/EA GAMES/"
                "Earth & Beyond/Data/client/output"
            )

        if not os.path.isdir(bak_dir):
            messagebox.showwarning(
                "Load Settings", "No backup found. Use Save Settings first."
            )
            return

        files = [os.path.join(bak_dir, "shortcut.ini")] + glob.glob(
            os.path.join(bak_dir, "player*_options.ini")
        )
        files = [f for f in files if os.path.exists(f)]

        if not files:
            messagebox.showwarning("Load Settings", "Backup folder is empty.")
            return

        if not messagebox.askyesno(
            "Load Settings",
            f"Overwrite current game settings with backup?\n\n"
            f"Files: {', '.join(os.path.basename(f) for f in files)}\n\n"
            "This affects all clients immediately (shared Program Files).",
        ):
            return

        try:
            for f in files:
                shutil.copy2(f, dst_dir)
            self._set_status(f"Game settings restored ({len(files)} files) ✓")
        except Exception as e:
            messagebox.showerror("Load Settings", f"Failed to restore:\n{e}")

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    def _show_readme(self):
        self._show_doc("Read Me", "README.md")

    def _show_doc(self, title: str, relative_path: str):
        """Open a repo doc file (README.md or docs/*.md) in a scrollable in-app viewer."""
        doc_path = os.path.join(os.path.dirname(__file__), relative_path)
        try:
            with open(doc_path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            messagebox.showerror(title, f"Could not open {doc_path}")
            return

        win = tk.Toplevel(self.root)
        win.title(f"{APP_NAME} — {title}")
        win.configure(bg=tk_color("bg"))
        win.geometry("760x600")
        win.minsize(500, 400)
        _center_on_parent(win, self.root)

        frame = tk.Frame(win, bg=tk_color("bg"))
        frame.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        sb = ttk.Scrollbar(frame, orient="vertical")
        sb.pack(side="right", fill="y")

        txt = tk.Text(
            frame,
            wrap="word",
            bg=tk_color("panel_bg"),
            fg=tk_color("text"),
            font=THEME["font_mono"],
            relief="flat",
            borderwidth=0,
            yscrollcommand=sb.set,
            padx=10,
            pady=8,
            state="normal",
        )
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)
        txt.insert("1.0", text)
        txt.config(state="disabled")

        if sys.platform == "win32":
            def _scroll(e):
                txt.yview_scroll(-1 if e.delta > 0 else 1, "units")
            txt.bind("<MouseWheel>", _scroll)
        else:
            def _scroll(e):
                txt.yview_scroll(-1 if e.num == 4 else 1, "units")
            txt.bind("<Button-4>", _scroll)
            txt.bind("<Button-5>", _scroll)

        tk.Button(
            win,
            text="Close",
            command=win.destroy,
            bg=tk_color("card_bg"),
            fg=tk_color("text"),
            font=THEME["font_main"],
            relief="flat",
            padx=12,
            pady=4,
        ).pack(pady=(0, 8))

    def _show_about(self):
        if sys.platform == "win32":
            details = (
                f"Windows multibox manager for\n"
                f"Earth & Beyond Emulator\n\n"
                f"Requires: pywin32\n"
                f"Runs on: native Windows"
            )
        else:
            details = (
                f"Linux multibox manager for\n"
                f"Earth & Beyond Emulator\n\n"
                f"Requires: xdotool, wmctrl, xrandr\n"
                f"Runs on: X11 (not Wayland)"
            )
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME}  v{APP_VERSION}\n\n{details}",
        )

    def _quit(self):
        self._stop_loop()
        if self._hk_mgr:
            self._hk_mgr.stop()
        self._kill_omit_indicator()
        self._save_current_profile()
        save_settings(self.settings)
        self.root.destroy()
