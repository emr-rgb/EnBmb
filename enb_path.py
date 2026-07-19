# ============================================================
#  enb_path.py — Locate the Earth & Beyond installation
#
#  Search order:
#    1. User-configured path in config/settings.json ("enb_install_path")
#    2. Windows registry: HKLM\SOFTWARE\EA Games\Earth & Beyond
#    3. Common default install locations
# ============================================================

import os
import sys


_DEFAULT_PATHS = [
    r"C:\Program Files\EA GAMES\Earth & Beyond",
    r"C:\Program Files (x86)\EA GAMES\Earth & Beyond",
    r"C:\EA GAMES\Earth & Beyond",
]


def _from_registry() -> str | None:
    """Try to read the install path from the Windows registry."""
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (
                r"SOFTWARE\EA Games\Earth & Beyond",
                r"SOFTWARE\WOW6432Node\EA Games\Earth & Beyond",
            ):
                try:
                    with winreg.OpenKey(hive, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "Install Dir")
                        if val and os.path.isdir(val):
                            return val.rstrip("\\")
                except FileNotFoundError:
                    continue
    except Exception:
        pass
    return None


def _from_settings() -> str | None:
    """Try to read a user-configured path from config/settings.json."""
    try:
        import json
        cfg = os.path.join(os.path.dirname(__file__), "config", "settings.json")
        with open(cfg, encoding="utf-8") as f:
            data = json.load(f)
        path = data.get("enb_install_path", "")
        if path and os.path.isdir(path):
            return path.rstrip("\\")
    except Exception:
        pass
    return None


def get_enb_install_path() -> str:
    """
    Return the Earth & Beyond installation root directory.
    Raises RuntimeError if the path cannot be found.
    """
    for finder in (_from_settings, _from_registry):
        path = finder()
        if path:
            return path

    for path in _DEFAULT_PATHS:
        if os.path.isdir(path):
            return path

    raise RuntimeError(
        "Earth & Beyond installation not found.\n"
        "Set 'enb_install_path' in config/settings.json to your install directory.\n"
        "Example: C:\\Program Files\\EA GAMES\\Earth & Beyond"
    )


def get_enb_data_path() -> str:
    """Return the Data directory inside the EnB install path."""
    return os.path.join(get_enb_install_path(), "Data")
