#!/usr/bin/env python3
"""
Remove star brightness effects from Dazzle.ini.

For STAR, BLUESTAR, YELLOWSTAR sections:
  - Sets HaloScaleX, HaloScaleY, DazzleScaleX, DazzleScaleY to 0
  - Removes LensflareName lines

Safe to run multiple times (idempotent).
Creates Dazzle.ini.bak on first run.
"""

import re
import os
import shutil
import sys

if sys.platform == "win32":
    from enb_path import get_enb_install_path
    DAZZLE_INI = os.path.join(get_enb_install_path(), "Data", "client", "ini", "Dazzle.ini")
else:
    DAZZLE_INI = os.path.expanduser(
        "~/.wine-enb/drive_c/Program Files/EA GAMES/Earth & Beyond/"
        "Data/client/ini/Dazzle.ini"
    )

STAR_SECTIONS = {"star", "bluestar", "yellowstar"}

ZERO_KEYS = {"haloscalex", "haloscaley", "dazzlescalex", "dazzlescaley"}


def apply(path: str) -> int:
    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"Backup created: {bak}")

    with open(path, encoding="latin-1") as f:
        lines = f.readlines()

    in_star = False
    changed = 0
    out = []
    for line in lines:
        m = re.match(r"^\[([^\]]+)\]", line)
        if m:
            in_star = m.group(1).strip().lower() in STAR_SECTIONS

        if in_star:
            # Remove LensflareName lines entirely
            if re.match(r"^LensflareName\s*=", line, re.IGNORECASE):
                changed += 1
                continue  # skip the line

            # Zero the scale keys
            km = re.match(r"^(\w+)\s*=", line)
            if km and km.group(1).lower() in ZERO_KEYS:
                new_line = re.sub(r"=\s*[\d.]+", "=0", line)
                if new_line != line:
                    changed += 1
                out.append(new_line)
                continue

        out.append(line)

    with open(path, "w", encoding="latin-1") as f:
        f.writelines(out)

    return changed


if __name__ == "__main__":
    if not os.path.exists(DAZZLE_INI):
        print(f"ERROR: Dazzle.ini not found at:\n  {DAZZLE_INI}", file=sys.stderr)
        sys.exit(1)
    n = apply(DAZZLE_INI)
    print(f"Done — {n} change(s) applied to {os.path.basename(DAZZLE_INI)}")
