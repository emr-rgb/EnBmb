# ============================================================
#  EnB Multibox Manager — constants.py
#  Central definitions for classes, colors, layout defaults
# ============================================================

APP_NAME = "EnB Multibox Manager"
APP_VERSION = "1.0.0"

# --- EnB class definitions ---
# Each entry: (abbreviation, full_name, race, archetype)
ENB_CLASSES = [
    ("PW", "Progen Warrior", "Progen", "Warrior"),
    ("PS", "Progen Sentinel", "Progen", "Sentinel"),
    ("PP", "Progen Privateer", "Progen", "Privateer"),
    ("TE", "Terran Enforcer", "Terran", "Enforcer"),
    ("TT", "Terran Tradesman", "Terran", "Tradesman"),
    ("TS", "Terran Scout", "Terran", "Scout"),
    ("JE", "Jenquai Explorer", "Jenquai", "Explorer"),
    ("JD", "Jenquai Defender", "Jenquai", "Defender"),
    ("JS", "Jenquai Seeker", "Jenquai", "Seeker"),
]

CLASS_ABBREVS = [c[0] for c in ENB_CLASSES]
CLASS_FULLNAMES = {c[0]: c[1] for c in ENB_CLASSES}

# Color per race — used to tint slot boxes on the canvas
RACE_COLORS = {
    "Progen": "#c0392b",  # deep red
    "Terran": "#2471a3",  # steel blue
    "Jenquai": "#1e8449",  # forest green
}

ABBREV_TO_RACE = {c[0]: c[2] for c in ENB_CLASSES}


def slot_color(abbrev):
    """Return the race color for a given class abbreviation, or grey if empty."""
    race = ABBREV_TO_RACE.get(abbrev)
    return RACE_COLORS.get(race, "#444444")


# --- Max slots ---
MAX_SLOTS = 6

# --- Default hotkeys ---
# Keys stored as pynput-compatible strings.
# Users set these by clicking in the Settings → Hotkeys tab and pressing a key.

DEFAULT_HOTKEYS = {
    # Window cycling
    "cycle_next": "grave",  # ` backtick
    "cycle_prev": "alt+grave",  # Alt+`
    "slot_driver": "",  # Return to slot 1 (driver) — unset by default
    "slot_1": "shift+F1",
    "slot_2": "shift+F2",
    "slot_3": "shift+F3",
    "slot_4": "shift+F4",
    "slot_5": "shift+F5",
    "slot_6": "shift+F6",
    # Macros
    "combat_loop": "alt+f",
    "abort": "Escape",
    "invite": "alt+i",
    "reform": "alt+r",
    "heal_cycle": "alt+h",
    "debuff_cycle": "ctrl+d",
    "buff_loop": "",
    "energy_loop": "",
    "daimyo_loop": "",
    "daimyo_step": "alt+a",
    "assign_driver": "alt+g",
    # Tool window
    "manager_front": "ctrl+alt+m",
}

# Human-readable metadata for each hotkey
HOTKEY_DEFS = {
    "cycle_next": (
        "Cycle Next Window",
        "Swap next client to main monitor (default: `)",
    ),
    "cycle_prev": (
        "Cycle Previous Window",
        "Swap previous client to main monitor (default: Alt+`)",
    ),
    "slot_driver": (
        "Return to Driver/Slot 1",
        "Restore slot 1 to main monitor (unset by default)",
    ),
    "slot_1": ("Focus Slot 1 Direct", "Directly swap slot 1 to main"),
    "slot_2": ("Focus Slot 2 Direct", "Directly swap slot 2 to main"),
    "slot_3": ("Focus Slot 3 Direct", "Directly swap slot 3 to main"),
    "slot_4": ("Focus Slot 4 Direct", "Directly swap slot 4 to main"),
    "slot_5": ("Focus Slot 5 Direct", "Directly swap slot 5 to main"),
    "slot_6": ("Focus Slot 6 Direct", "Directly swap slot 6 to main"),
    "combat_loop": ("Start Combat Loop", "Trigger the combat assist cycle"),
    "abort": ("Stop / Abort", "Immediately stop any running loop or macro"),
    "invite": (
        "Run Invite Macro",
        "Send /invite to all names in the active invite list",
    ),
    "reform": ("Run Reform Macro", "Set formation on driver, have all others join"),
    "heal_cycle": ("Heal Cycle", "Cycle through clients and use heal abilities"),
    "debuff_cycle": ("Debuff Cycle", "Cycle through clients and use debuff devices"),
    "buff_loop": ("Buff Loop", "One-pass buff cycle for all slots"),
    "energy_loop": ("Energy Loop", "Press energy keys + run PV9 pass for all slots"),
    "daimyo_loop": (
        "Daimyo Loop / Step",
        "Start Daimyo Mode 1 loop or fire one Mode 2 step (depends on active mode)",
    ),
    "daimyo_step": (
        "Daimyo Step (alt hotkey)",
        "Same action as Daimyo Loop / Step — assign to a second hotkey if desired",
    ),
    "assign_driver": (
        "Assign Driver",
        "Make whoever is on the main monitor the permanent driver for all loops",
    ),
    "manager_front": ("Bring Manager to Front", "Raise the multibox manager window"),
}

# Maps key names to human-friendly display strings
KEY_DISPLAY_NAMES = {
    "grave": "` (backtick)",
    "Tab": "Tab",
    "Escape": "Escape",
    "Return": "Enter",
    "space": "Space",
    "BackSpace": "Backspace",
    "Delete": "Delete",
    "F1": "F1",
    "F2": "F2",
    "F3": "F3",
    "F4": "F4",
    "F5": "F5",
    "F6": "F6",
    "F7": "F7",
    "F8": "F8",
    "F9": "F9",
    "F10": "F10",
    "F11": "F11",
    "F12": "F12",
}

# --- Layout defaults ---
DEFAULT_LAYOUT = {
    "main_monitor": 0,
    "secondary_monitor": 1,
    "secondary_count": 5,
    "secondary_columns": 2,
    "gap_px": 0,
    "taskbar_height": 0,  # px reserved for taskbar — set >0 if taskbar is not auto-hide
    "taskbar_monitor": 1,  # which monitor has the taskbar
    "layout_mode": "auto",       # "auto" (slider drives geometry) or "custom" (drag/preset)
    "ar_lock": "none",           # "none" or "4:3" — constrain secondary cells to aspect ratio
    "snap_enabled": True,
    "snap_threshold_px": 20,     # screen pixels to snap within
    "mgr_custom_pos": None,      # {x,y,w,h} when MGR manually positioned, else None
}

# Wine/Win32 non-client area correction (winresize.exe sizing accounts for Win32 chrome)
WIN32_NC_W = 6   # extra width added by Win32 non-client chrome
WIN32_NC_H = 32  # extra height added by Win32 title bar

# --- UI themes ---
THEMES = {
    "Dark Navy": {
        "bg": "#1a1a2e",
        "panel_bg": "#16213e",
        "card_bg": "#0f3460",
        "accent": "#e94560",
        "accent2": "#f5a623",
        "text": "#eaeaea",
        "text_dim": "#888888",
        "text_dark": "#333333",
        "slot_empty": "#2a2a2a",
        "slot_border": "#444444",
        "success": "#27ae60",
        "warning": "#f39c12",
        "danger": "#e74c3c",
    },
    "Dark Minimal": {
        "bg": "#1c1c1c",
        "panel_bg": "#242424",
        "card_bg": "#2e2e2e",
        "accent": "#cc3333",
        "accent2": "#e0a020",
        "text": "#dedede",
        "text_dim": "#777777",
        "text_dark": "#333333",
        "slot_empty": "#2a2a2a",
        "slot_border": "#3a3a3a",
        "success": "#4a9e5c",
        "warning": "#c97f10",
        "danger": "#b03030",
    },
    "High Contrast": {
        "bg": "#000000",
        "panel_bg": "#0a0a0a",
        "card_bg": "#111111",
        "accent": "#ffff00",
        "accent2": "#00ffff",
        "text": "#ffffff",
        "text_dim": "#aaaaaa",
        "text_dark": "#222222",
        "slot_empty": "#1a1a1a",
        "slot_border": "#666666",
        "success": "#00dd00",
        "warning": "#ffaa00",
        "danger": "#ff3333",
    },
    "Terminal Green": {
        "bg": "#0a0f0a",
        "panel_bg": "#0d140d",
        "card_bg": "#111a11",
        "accent": "#00cc44",
        "accent2": "#44cc88",
        "text": "#00ee44",
        "text_dim": "#336633",
        "text_dark": "#0a1a0a",
        "slot_empty": "#0d180d",
        "slot_border": "#1a3a1a",
        "success": "#00aa33",
        "warning": "#aacc00",
        "danger": "#cc2200",
    },
    "Earth & Beyond": {
        "bg": "#0a0a1e",
        "panel_bg": "#10103a",
        "card_bg": "#1e1e5a",
        "accent": "#44ee00",
        "accent2": "#ffcc00",
        "text": "#e0e0e0",
        "text_dim": "#7070aa",
        "text_dark": "#05050f",
        "slot_empty": "#0d0d30",
        "slot_border": "#0055cc",
        "success": "#00cc00",
        "warning": "#ffcc00",
        "danger": "#ff2020",
    },
    "Classic Linux": {
        "bg": "#d4d0c8",
        "panel_bg": "#c0bdb5",
        "card_bg": "#ece9d8",
        "accent": "#000080",
        "accent2": "#800000",
        "text": "#000000",
        "text_dim": "#444444",
        "text_dark": "#000000",
        "slot_empty": "#b0aaa0",
        "slot_border": "#808080",
        "success": "#006400",
        "warning": "#8b6914",
        "danger": "#8b0000",
    },
}

_FONTS = {
    "font_main": ("Courier New", 12),
    "font_heading": ("Courier New", 14, "bold"),
    "font_title": ("Courier New", 16, "bold"),
    "font_small": ("Courier New", 10),
    "font_mono": ("Courier New", 11),
}


def get_theme(name: str) -> dict:
    colors = THEMES.get(name, THEMES["Dark Navy"]).copy()
    colors.update(_FONTS)
    return colors


THEME = get_theme("Dark Navy")

# Hotbar keys available in EnB (6 slots + alt bar)
LOOP_KEY_OPTIONS = [
    "",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "alt+1",
    "alt+2",
    "alt+3",
    "alt+4",
    "alt+5",
    "alt+6",
]

LOOP_TYPES = [
    ("combat", "Combat"),
    ("buff", "Buff"),
    ("debuff", "Debuff"),
    ("heal", "Heal"),
    ("energy", "Energy"),
]

ENB_WINDOW_TITLE = "Earth & Beyond"  # exact X11 window title of the EnB client

# EnB client process/window name to scan for
ENB_WINDOW_NAMES = [
    "Earth & Beyond",
    "Earth and Beyond",
    "net7proxy",
    "client",
]

# EnB-related process names for comprehensive kill/detect.
# Used by kill_all_enb_processes() and find_enb_processes() in window_manager.
# Excludes generic Wine processes (wineserver, conhost, explorer.exe) that
# would also kill unrelated Wine apps.
ENB_PROCESS_NAMES = [
    "client.exe",
    "net7proxy.exe",
    "LaunchNet7.exe",
    "enb_up.exe",
    "net7config.exe",
    "CharacterStarshipCreator.exe",
    "CnSC.exe",
]
