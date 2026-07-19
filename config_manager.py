# ============================================================
#  EnB Multibox Manager — config_manager.py
#  Handles all JSON loading/saving for profiles, roles, layout
# ============================================================

import json
import os
import sys
from constants import DEFAULT_HOTKEYS, DEFAULT_LAYOUT, MAX_SLOTS

CONFIG_DIR    = os.path.join(os.path.dirname(__file__), "config")
PROFILE_DIR   = os.path.join(os.path.dirname(__file__), "profiles")
ROLE_DIR      = os.path.join(os.path.dirname(__file__), "roles")
CHARACTER_DIR = os.path.join(os.path.dirname(__file__), "characters")

for d in (CONFIG_DIR, PROFILE_DIR, ROLE_DIR, CHARACTER_DIR):
    os.makedirs(d, exist_ok=True)

SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")


# ── Default structures ────────────────────────────────────────

def default_settings():
    return {
        "hotkeys":          DEFAULT_HOTKEYS.copy(),
        "layout":           DEFAULT_LAYOUT.copy(),
        "active_profile":   "default",
        "action_delay_ms":  50,
        "launch_delay_ms":  3000,
        "canvas_docked":    True,
        "theme":            "Dark Navy",
        "slot_commands":    [f"enb-slot{i+1}" for i in range(MAX_SLOTS)],
        "invite_accept": {
            "mode":            "per_window",
            "cycle_settle_ms": 600,
            "cycle_coords":    {"x": 0, "y": 0},
            "per_window":      [{"x_pct": 0.0, "y_pct": 0.0} for _ in range(MAX_SLOTS - 1)],
        },
        "reform": {
            "click_1":        {"x_pct": 0.0, "y_pct": 0.0},
            "click_delay_ms": 200,
            "click_2":        {"x_pct": 0.0, "y_pct": 0.0},
            "settle_ms":      1000,
            "key":            "t",
        },
        "loops": {
            "key_delay_ms":      10,
            "fire_key":          "f",
            "interleave_buffs":  False,  # buff loop: round through targets across slots
            "assist_per_window": [{"x_pct": 0.0, "y_pct": 0.0} for _ in range(MAX_SLOTS)],
        },
        "frozen_zone_timeout_s": 20,    # seconds before a stalled zone triggers relaunch
        "zone_freeze_enabled": False,   # enable zone-freeze consensus detection (group play only)
        "autologin_on_launch": False,   # whether Launch All also runs autologin
        "daimyo_mode": 1,               # 1 = continuous loop (Mode 1), 2 = manual step (Mode 2)
        "quit_to_desktop": {
            # Percentage offsets from window top-left (0.0–1.0).
            # in_game: Escape opens the menu, then click Quit to Desktop.
            # pre_game: login + char-select share same Exit button location.
            # Set pre_game to {x_pct:0, y_pct:0} to fall back to Alt+F4.
            "in_game":  {"x_pct": 0.0, "y_pct": 0.0},
            "pre_game": {"x_pct": 0.0, "y_pct": 0.0},
        },
        "autologin": {
            # Tab navigation fills username/password fields (Wine windows don't
            # move keyboard focus on click). Only the login button is clicked.
            "login_x_pct": 0.0,
            "login_y_pct": 0.0,
        },
        "char_select": {
            # Percentage offsets from window top-left (0.0–1.0).
            # One set covers all window sizes.
            "positions":       [[0.0, 0.0] for _ in range(5)],
            "settle_ms":       6000,
            "button_ready_ms": 1200,
            "accept_delay_ms": 1200,
        },
        "layout_presets": {},  # user-saved presets: name → {slots: [[x,y,w,h],...], mgr_pos: ...}
    }

def default_slot():
    """One slot entry inside a group profile."""
    return {
        "role":         "",          # class abbreviation e.g. "PW"
        "char_name":    "",          # in-game character name
        "character":    "",          # name of character profile assigned to this slot
        "username":     "",          # login username for auto-login macro
        "password":     "",          # login password (stored plaintext, local use only)
        "window_id":    None,        # X11 window id (int), None if unassigned
        "monitor":      1,           # which monitor this slot lives on
        "x": 0, "y": 0,
        "w": 960, "h": 540,
        "stay_on_top":  False,
    }

def default_group_profile(name="default"):
    return {
        "name":          name,
        "slots":         [default_slot() for _ in range(MAX_SLOTS)],
        "invite_list":   [],         # list of char names to /invite
        "formation_key": "t",        # key to join formation
        "combat_profiles": [],       # names of combat loop profiles
        "active_combat": "",
    }

def default_role_config(abbrev="PW"):
    return {
        "abbrev":        abbrev,

        "active_assist_profile": "per_monitor",

        "key_sequences": [],   # keys to press in combat loop for this role
        "auto_abilities": [],  # future: timed auto-cast entries

        # Future: special sequences (PS buff rotation, debuff cycles etc.)
        # These will have their own editor once base features are stable.
        "special_sequences": {},
    }

def default_combat_profile(name="default"):
    return {
        "name":        name,
        "description": "",
        "slots":       [],    # list of slot indices that participate (0-based)
        "loop":        True,  # continuous loop vs single pass
        "delay_ms":    50,
    }


# ── Platform-specific settings overrides ───────────────────────
# Some settings genuinely differ between Linux (Wine/X11) and native
# Windows: loop/cycle settle times (Wine/X11 wmctrl activation latency vs.
# native), and slot_commands (how each slot's game client is launched).
# Each (section, key) below may have "<key>_linux" / "<key>_windows"
# siblings in settings.json; the one matching the current platform is
# copied into the plain key so existing readers don't need to know about
# the split. section is None for top-level keys (e.g. slot_commands).
_PLATFORM_KEYS = [
    ("loops", "activate_settle_ms"),
    ("loops", "activate_settle_ms_2x"),
    ("loops", "activate_settle_ms_3x"),
    ("loops", "cycle_settle_ms"),
    ("invite_accept", "cycle_settle_ms"),
    ("reform", "settle_ms"),
    ("reform", "secondary_cycle_settle_ms"),
    (None, "slot_commands"),
]

_PLATFORM_SUFFIX = "windows" if sys.platform == "win32" else "linux"


def _resolve_platform_overrides(settings: dict) -> None:
    """Copy the current platform's "<key>_<platform>" override (if present)
    into the plain key, in place."""
    for section, key in _PLATFORM_KEYS:
        sect = settings if section is None else settings.get(section)
        if isinstance(sect, dict) and f"{key}_{_PLATFORM_SUFFIX}" in sect:
            sect[key] = sect[f"{key}_{_PLATFORM_SUFFIX}"]


def _sync_platform_overrides(settings: dict) -> None:
    """Write the (possibly user-edited) plain value of each platform-specific
    key back into this platform's override slot, so saving on one platform
    doesn't clobber the other platform's value."""
    for section, key in _PLATFORM_KEYS:
        sect = settings if section is None else settings.get(section)
        if isinstance(sect, dict) and key in sect:
            sect[f"{key}_{_PLATFORM_SUFFIX}"] = sect[key]


# ── Settings ─────────────────────────────────────────────────

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            # Merge with defaults so new keys are always present
            merged = default_settings()
            merged.update(data)
            merged["hotkeys"]  = {**DEFAULT_HOTKEYS,   **data.get("hotkeys", {})}
            merged["hotkeys"].pop("slot_7", None)
            merged["layout"]   = {**DEFAULT_LAYOUT,    **data.get("layout", {})}
            _resolve_platform_overrides(merged)
            return merged
        except Exception as e:
            print(f"[config] Error loading settings: {e} — using defaults")
    return default_settings()

def save_settings(settings: dict):
    _sync_platform_overrides(settings)
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"[config] Error saving settings: {e}")


# ── Group profiles ────────────────────────────────────────────

def profile_path(name: str) -> str:
    safe = name.replace(" ", "_").replace("/", "-")
    return os.path.join(PROFILE_DIR, f"{safe}.json")

def list_profiles() -> list:
    files = [f for f in os.listdir(PROFILE_DIR) if f.endswith(".json")]
    return [os.path.splitext(f)[0].replace("_", " ") for f in sorted(files)]

def load_profile(name: str) -> dict:
    path = profile_path(name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"[config] Error loading profile '{name}': {e}")
    # Return fresh default
    p = default_group_profile(name)
    save_profile(p)
    return p

def save_profile(profile: dict):
    path = profile_path(profile["name"])
    try:
        with open(path, "w") as f:
            json.dump(profile, f, indent=2)
    except Exception as e:
        print(f"[config] Error saving profile: {e}")

def delete_profile(name: str):
    path = profile_path(name)
    if os.path.exists(path):
        os.remove(path)


# ── Role configs ──────────────────────────────────────────────

def role_path(abbrev: str) -> str:
    return os.path.join(ROLE_DIR, f"{abbrev}.json")

def load_role(abbrev: str) -> dict:
    path = role_path(abbrev)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"[config] Error loading role '{abbrev}': {e}")
    return default_role_config(abbrev)

def save_role(role: dict):
    path = role_path(role["abbrev"])
    try:
        with open(path, "w") as f:
            json.dump(role, f, indent=2)
    except Exception as e:
        print(f"[config] Error saving role: {e}")


# ── Role profiles (named, per-slot key sequences) ─────────────

def default_role_profile(name="New Profile"):
    return {
        "name":              name,
        "description":       "",
        "class":             "",
        "combat_keys":       [],
        "buff_keys":         [],    # simple cast keys — pressed once, no targeting
        "buff_devices":      [],    # targeted devices: [{key, targets, reassist, cast_time_s}]
        "debuff_keys":       [],
        "heal_keys":         [],
        "heal_target_key":   "",    # TT: F-key to target driver before healing (e.g. "f2")
        "daimyo_key":        "",    # PS: device key to activate Daimyo
        "daimyo_targets":    [],    # PS: ordered F-key list to buff ([] = self only)
        "daimyo_interval_s": 30.0,  # PS: seconds between each buff in the cycle
        "fotw_enabled":      False, # use Focus of the Warder instead of Daimyo
        "fotw_key":          "",    # key to activate Focus of the Warder
        "fotw_targets":      [],    # ordered F-key list (same F1-F6 logic as Daimyo)
        "fotw_interval_s":   6.0,   # seconds between each FOTW activation (6s cooldown)
        "energy_keys":       [],    # energy management keys pressed each cycle
        "pv9_enabled":       False, # whether this slot uses Power Vortex EM9
        "pv9_key":           "",    # key/slot to activate Power Vortex EM9
        "pv9_targets":       [],    # ordered F-key list of characters to buff (one pass)
    }

def role_profile_path(name: str) -> str:
    safe = name.replace(" ", "_").replace("/", "-")
    return os.path.join(ROLE_DIR, f"profile_{safe}.json")

def list_role_profiles() -> list:
    files = [f for f in os.listdir(ROLE_DIR)
             if f.startswith("profile_") and f.endswith(".json")]
    return [os.path.splitext(f)[0][8:].replace("_", " ") for f in sorted(files)]

def load_role_profile(name: str) -> dict:
    path = role_profile_path(name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"[config] Error loading role profile '{name}': {e}")
    return default_role_profile(name)

def save_role_profile(profile: dict):
    path = role_profile_path(profile["name"])
    try:
        with open(path, "w") as f:
            json.dump(profile, f, indent=2)
    except Exception as e:
        print(f"[config] Error saving role profile: {e}")

def delete_role_profile(name: str):
    path = role_profile_path(name)
    if os.path.exists(path):
        os.remove(path)


# ── Character profiles (per-character: account + role + loops) ────

def default_character(name="New Character"):
    """One in-game character. Holds login credentials, class/role,
    role profile pointer, and per-character autologin coords."""
    return {
        "name":          name,    # in-game character name
        "account":       "",      # account/username for login
        "password":      "",      # password (plaintext, local use only)
        "char_class":    "",      # class abbreviation e.g. "PW"
        "role_profile":  "",      # name of role profile (loops/keys)
        "loop_overrides": {},     # per-character overrides merged onto role_profile (e.g. {"buff_keys": ["8"]})
        "char_select": {
            # Click coordinate of this character's name button on the
            # character select screen (upper-left buttons are stable
            # across logins per spec).
            "x": 0, "y": 0,
        },
        "notes":         "",
    }

def character_path(name: str) -> str:
    safe = name.replace(" ", "_").replace("/", "-")
    return os.path.join(CHARACTER_DIR, f"{safe}.json")

def list_characters() -> list:
    """Return character profile names, sorted alphabetically."""
    files = [f for f in os.listdir(CHARACTER_DIR) if f.endswith(".json")]
    return [os.path.splitext(f)[0].replace("_", " ") for f in sorted(files)]

def load_character(name: str) -> dict:
    path = character_path(name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            # Merge with defaults so newly-added fields are always present
            merged = default_character(name)
            merged.update(data)
            merged.setdefault("char_select", {"x": 0, "y": 0})
            return merged
        except Exception as e:
            print(f"[config] Error loading character '{name}': {e}")
    return default_character(name)

def save_character(profile: dict):
    path = character_path(profile["name"])
    try:
        with open(path, "w") as f:
            json.dump(profile, f, indent=2)
    except Exception as e:
        print(f"[config] Error saving character: {e}")

def delete_character(name: str):
    path = character_path(name)
    if os.path.exists(path):
        os.remove(path)

def list_accounts() -> list:
    """Return unique account names across all character profiles."""
    accts = set()
    for n in list_characters():
        c = load_character(n)
        if c.get("account"):
            accts.add(c["account"])
    return sorted(accts)

def characters_for_account(account: str) -> list:
    """Return character names that belong to the given account."""
    out = []
    for n in list_characters():
        c = load_character(n)
        if c.get("account") == account:
            out.append(n)
    return sorted(out)


# ── Combat loop profiles ──────────────────────────────────────

def combat_profile_path(name: str) -> str:
    safe = name.replace(" ", "_").replace("/", "-")
    return os.path.join(CONFIG_DIR, f"combat_{safe}.json")

def list_combat_profiles() -> list:
    files = [f for f in os.listdir(CONFIG_DIR) if f.startswith("combat_") and f.endswith(".json")]
    return [os.path.splitext(f)[0][7:].replace("_", " ") for f in sorted(files)]

def load_combat_profile(name: str) -> dict:
    path = combat_profile_path(name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"[config] Error loading combat profile '{name}': {e}")
    return default_combat_profile(name)

def save_combat_profile(profile: dict):
    path = combat_profile_path(profile["name"])
    try:
        with open(path, "w") as f:
            json.dump(profile, f, indent=2)
    except Exception as e:
        print(f"[config] Error saving combat profile: {e}")


# ── Invite list profiles ──────────────────────────────────────

def invite_profile_path(name: str) -> str:
    safe = name.replace(" ", "_").replace("/", "-")
    return os.path.join(CONFIG_DIR, f"invite_{safe}.json")

def list_invite_profiles() -> list:
    files = [f for f in os.listdir(CONFIG_DIR)
             if f.startswith("invite_") and f.endswith(".json")]
    return [os.path.splitext(f)[0][7:].replace("_", " ") for f in sorted(files)]

def load_invite_profile(name: str) -> dict:
    path = invite_profile_path(name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"[config] Error loading invite profile '{name}': {e}")
    return {"name": name, "names": []}

def save_invite_profile(profile: dict):
    path = invite_profile_path(profile["name"])
    try:
        with open(path, "w") as f:
            json.dump(profile, f, indent=2)
    except Exception as e:
        print(f"[config] Error saving invite profile: {e}")

def delete_invite_profile(name: str):
    path = invite_profile_path(name)
    if os.path.exists(path):
        os.remove(path)
