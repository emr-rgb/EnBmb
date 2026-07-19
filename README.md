# EnB Multibox Manager

A multi-client manager for Earth & Beyond (Net-7 emulator). Runs up to 6 game clients simultaneously on **Linux or Windows**, automates login and character selection, manages window layout across two monitors, and provides macro loops for multiboxing.

**Linux: requires X11. Wayland is not supported.** Windows has no equivalent restriction.

---

## Features

- **Launch All** — starts all clients in sequence, dismisses EULA dialogs, auto-detects windows
- **Auto-login** — types credentials and selects characters for all slots, fully unattended
- **Window layout** — visual canvas with drag-to-position, preset layouts, Auto and Custom modes
- **Cycling** — instantly swap any secondary slot to the main monitor and back via hotkey
- **Combat loops** — automated combat, buff (with optional interleaving), debuff, heal, and energy macro loops
- **Per-character loop overrides** — override any loop's key sequence for a specific character, layered on top of its role profile
- **Daimyo / FotW** — formation device rotation (PS) and Focus of the Warder rotation (any class)
- **Invite / Reform** — automated group invite and formation reform sequences
- **Raid Mode** — 2× or 3× timing multiplier for heavy-load raid situations, with independently tunable activation-settle delays per mode
- **Auto-relaunch** — detects client crashes and relaunches the affected slot automatically, then re-logs in
- **Zone freeze detection** — per-slot chat.log watch that relaunches a slot if it doesn't confirm arrival after zoning
- **State monitor** — tracks each slot's state (OFFLINE → LOGIN SCREEN → CHAR SELECT → IN GAME) in real time
- **Layout presets** — save and load named window arrangements, with live canvas preview before applying; optional 4:3 aspect-ratio lock
- **Hotkeys** — global system-wide hotkeys for all major actions, fully configurable
- **Compact view** — minimal UI that fits in the empty grid cell on your secondary monitor
- **Indicator overlay** — small on-screen label showing the currently active slot
- **Game utilities** — mute sounds, dark mode (Dazzle.ini), privacy mode, settings backup/restore

---

## Requirements

### Linux

> **Tested only on Arch / CachyOS, X11.** `install.sh` detects pacman/apt/dnf/zypper and
> installs the right package names for each, but only the pacman path has actually been
> run — other distros are best-effort. wine version differences (especially the lack of
> `wine-staging` in non-Arch default repos) are untested; see [docs/INSTALL.md](docs/INSTALL.md).

- Any Linux distro with pacman, apt, dnf, or zypper — Arch/CachyOS is the only one actually tested
- X11 session — **not Wayland**
- Two monitors (1920×1080 recommended)
- Earth & Beyond installed via the [Net-7 launcher](https://www.net-7.org) or the [ciphersimian Linux installer](https://github.com/ciphersimian/enb-linux-installer)
- wine-staging (recommended) or wine

### Windows

- Windows 10 or 11
- Two monitors (1920×1080 recommended)
- Python 3 with pip
- Earth & Beyond installed via the [Net-7 launcher](https://www.net-7.org) — one native install, shared by all 6 slots (no per-slot copies needed)
- Admin rights — enbmb self-elevates via UAC on launch so child game clients don't each prompt separately

Single-monitor setups are possible with all 6 slots in a grid, but are not the primary supported configuration on either platform.

---

## Installation

### Linux

```bash
git clone https://github.com/emr-rgb/EnBmb
cd EnBmb
bash install.sh
```

Then run the prefix setup to create the 6 isolated Wine environments:

```bash
bash ~/.local/share/enbmb/setup_prefixes.sh
```

Full instructions: [docs/INSTALL.md](docs/INSTALL.md)

### Windows

```powershell
git clone https://github.com/emr-rgb/EnBmb
```

Then double-click **`install.bat`** inside the cloned folder. It checks for Python, installs dependencies, and launches enbmb. No prefix setup needed — Windows runs one native install shared by all 6 slots. Full instructions: [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md)

---

## Quick Start

1. Open **Settings** → set launch commands and credentials per slot
   - **Linux**: `enb-slot1` through `enb-slot6` (created by `setup_prefixes.sh`)
   - **Windows**: the same `LaunchNet7.exe` path for all 6 slots
2. Calibrate click coordinates in Settings → **Login** (use the **Set** buttons, click in-game)
3. Click **Launch All** — clients start and position themselves
4. Click **Auto Login** — all slots log in and enter the game
5. Use the cycle hotkey (default: backtick) to bring any slot to the main monitor

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for the complete UI reference.

---

## Typical Session

| Step | Action |
|------|--------|
| Start | Launch All (launches, positions, and optionally auto-logs in all slots) |
| Play | Cycle hotkey to swap slots; macro hotkeys for combat/buff/heal |
| Group up | Invite Party → Reform to get everyone in formation |
| End session | Quit to Desktop (graceful) or Kill All (force) |

---

## Limitations

**Both platforms:**
- **6 slots maximum**
- **Sequential macro input** — macros focus each slot window briefly; parallel input to inactive/unfocused game windows does not work

**Linux:**
- **X11 only** — Wayland / XWayland is not supported
- **Arch Linux** — only the pacman path through `install.sh` is actually tested; apt/dnf/zypper support is best-effort and untested
- **wine-staging recommended** — plain wine has input timing issues on non-primary monitors

**Windows:**
- **Requires admin elevation** — enbmb self-elevates via UAC; running it without admin rights causes per-client UAC prompts instead of one
- **One shared install, not 6 isolated copies** — Mute Sounds, Dark Mode, Privacy, and Save/Load Game Settings all apply to every client at once, since there's only one set of game config files on disk

---

## Known Issues

- Slot 1 may appear at secondary size after Detect if the previous session ended mid-cycle. Cycling once restores it.
- Compact view title bar may show depending on your window manager (Linux) — cosmetic only.

---

## Warnings

- **Do not click other windows during Auto-Login.** enbmb sends real keypresses to the focused window (X11 on Linux, native Win32 input on Windows); clicking elsewhere mid-sequence redirects input.
- **Global hotkeys capture system-wide.** Don't bind keys your desktop environment already uses.
- **Auto-relaunch re-enters credentials automatically.** Disable it if you don't want unsupervised logins.
- **Kill All force-kills game client processes.** Unsaved progress will be lost. Use Quit to Desktop for a clean exit.
