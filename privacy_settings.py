#!/usr/bin/env python3
"""
Apply privacy/channel defaults to all player*_options.ini files.

Sets:
  RestrictedStatus   = yes   (hide login from non-friends)
  Starmap_Maximized  = no
  Channel_Broadcast  = no
  Channel_Local      = no
  Channel_General    = no
  Channel_OOC        = no
  Channel_Newbie     = no
  Channel_Explorers  = no
  Channel_Enforcers  = no
  Channel_Traders    = no
  Channel_Jenquai    = no
  Channel_Terran     = no
  Channel_Warriors   = no
  Channel_Progen     = no
  Channel_Defenders  = no
  Channel_Sentinels  = no
  Channel_Market     = no

  Channel_Guild      = yes
  Channel_Group      = yes
  Channel_Private    = yes

Safe to run multiple times (idempotent).
Preserves original file format exactly (no spaces added around =).
"""

import os
import sys
import glob
import re

if sys.platform == "win32":
    from enb_path import get_enb_install_path
    OUTPUT_DIR = os.path.join(get_enb_install_path(), "Data", "client", "output")
else:
    OUTPUT_DIR = os.path.expanduser(
        "~/.wine-enb/drive_c/Program Files/EA GAMES/Earth & Beyond/"
        "Data/client/output"
    )

PRIVACY_SETTINGS = {
    "RestrictedStatus":   "yes",
    "Starmap_Maximized":  "no",
    "Channel_Broadcast":  "no",
    "Channel_Local":      "no",
    "Channel_General":    "no",
    "Channel_OOC":        "no",
    "Channel_Newbie":     "no",
    "Channel_Explorers":  "no",
    "Channel_Enforcers":  "no",
    "Channel_Traders":    "no",
    "Channel_Jenquai":    "no",
    "Channel_Terran":     "no",
    "Channel_Warriors":   "no",
    "Channel_Progen":     "no",
    "Channel_Defenders":  "no",
    "Channel_Sentinels":  "no",
    "Channel_Market":     "no",
    "Channel_Guild":      "yes",
    "Channel_Group":      "yes",
    "Channel_Private":    "yes",
}


def _apply_to_file(path: str) -> int:
    """Update one file in-place. Returns number of lines changed."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    changes   = 0
    pending   = None   # OptionName seen in previous line, awaiting OptionValue

    new_lines = []
    for line in lines:
        stripped = line.rstrip("\r\n")

        # Detect OptionName=<value> (with or without spaces around =)
        m_name = re.match(r'^OptionName\s*=\s*(.+)$', stripped)
        if m_name:
            pending = m_name.group(1).strip()
            # Always write without spaces
            new_lines.append(f"OptionName={pending}\n")
            continue

        # Detect OptionValue=<value> — only act if we just saw a matching OptionName
        m_val = re.match(r'^(OptionValue\s*=\s*)(.+)$', stripped)
        if m_val and pending is not None:
            desired  = PRIVACY_SETTINGS.get(pending)
            current  = m_val.group(2).strip()
            # Always write without spaces around = to match original game format
            canonical = f"OptionValue={current}\n"
            if desired is not None and current != desired:
                canonical = f"OptionValue={desired}\n"
                changes += 1
            elif m_val.group(1) != "OptionValue=":
                # Spaces were added by a previous run — normalise back
                changes += 1
            new_lines.append(canonical)
            pending = None
            continue

        else:
            pending = None

        new_lines.append(line)

    if changes:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    return changes


def apply_privacy() -> str:
    pattern = os.path.join(OUTPUT_DIR, "player*_options.ini")
    files   = sorted(glob.glob(pattern))
    if not files:
        return f"No player*_options.ini found in:\n{OUTPUT_DIR}"

    changed_files = 0
    total_changes = 0

    for path in files:
        n = _apply_to_file(path)
        if n:
            changed_files += 1
            total_changes += n

    count = len(files)
    if total_changes == 0:
        return f"Privacy settings already applied — {count} file(s) checked, nothing to change."
    return (f"Privacy applied — {total_changes} change(s) across "
            f"{changed_files}/{count} file(s).")


if __name__ == "__main__":
    print(apply_privacy())
