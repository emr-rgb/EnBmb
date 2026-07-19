# Architecture — EnB Multibox Manager

Stable reference. Update only when file layout, target environment, or
core design changes.

## Project goal
Cross-platform multibox manager for Earth & Beyond Emulator.
Primary target: CachyOS/Arch Linux with X11 (LXQt session) + Wine.
Windows native support added in phase1-refactor.
Primary setup: 2 monitors. Scalable up to 6 slots.

## Target environment — Linux
- **OS**: CachyOS (Arch-based)
- **Desktop**: LXQt on X11 — Wayland is NOT supported (input broadcasting requires X11)
- **Wine**: wine-staging
- **Monitors**: 2× 1920×1080
  - Left (primary): slot 1 driver window, full size
  - Right (secondary): slots 2–6 grid
- **Game**: Earth & Beyond Emulator via Net-7

## File locations (on the target machine)
- Project: `~/.local/share/enbmb/`
- Launchers: `~/.local/bin/enb-slot1` through `enb-slot6`
- Wine prefixes: `~/.wine-enb` (base), `~/.wine-enb-2` … `~/.wine-enb-6`
- `winresize.exe`: bundled in the install directory

## Module map
| File | Responsibility |
|---|---|
| `main.py` | Entry point; X11 check; Tk root + theme; loads `EnBMultiboxApp` |
| `constants.py` | Class definitions, theme colors, hotkey defaults |
| `config_manager.py` | JSON load/save for profiles, roles, characters |
| `window_manager.py` | Platform shim: imports `window_manager_linux` or `window_manager_windows` |
| `window_manager_linux.py` | X11 window ops via xdotool/wmctrl/python-xlib (Linux/Wine) |
| `window_manager_windows.py` | Native Windows window ops via win32api/ctypes |
| `slot_manager.py` | Slot state, cycling logic, liveness checking |
| `layout_engine.py` | Tiling math + canvas coordinate scaling |
| `cycle_manager.py` | Window swap between main and secondary monitors |
| `hotkey_manager.py` | Global hotkeys via pynput |
| `enb_monitor.py` | Background daemon: tracks client state via network connections |
| `enb_path.py` | Locates game install path (Wine prefix on Linux, registry on Windows) |
| `gui_main.py` | Main application window |
| `gui_settings.py` | Settings window with click-to-capture hotkeys |
| `dark_mode_dazzle.py` | Zeros star halo/dazzle scales in `Dazzle.ini` |
| `mute_login_sounds.py` | Mutes login/voice/footstep sounds in `sounds.ini` |
| `port_probe.py` | Per-slot TCP port probing used by enb_monitor |
| `omit_indicator_overlay.py` | GTK overlay showing which slot is on main monitor (Linux) |
| `omit_indicator_overlay_windows.py` | Win32 overlay showing which slot is on main monitor (Windows) |
| `privacy_settings.py` | Masks credentials in the UI when not actively editing |
| `setup_prefixes.sh` | Wine prefix setup script |
| `install.sh` | Arch Linux installer |

## EnB classes (9 total)
| Abbrev | Full Name | Race |
|--------|-----------|------|
| PW | Progen Warrior | Progen |
| PS | Progen Sentinel | Progen |
| PP | Progen Privateer | Progen |
| TE | Terran Enforcer | Terran |
| TT | Terran Tradesman | Terran |
| TS | Terran Scout | Terran |
| JE | Jenquai Explorer | Jenquai |
| JD | Jenquai Defender | Jenquai |
| JS | Jenquai Seeker | Jenquai |

## Grid layout
- Slot 1: full primary monitor (1920×1080)
- Slots 2–6 on secondary monitor, grid adapts to secondary count:
  - 2 slots → 2×1 (side by side, top-aligned)
  - 3–4 slots → 2×2
  - 5–6 slots → 3×2 (640×540 each)
- Fill order (vertical, column by column):
  ```
  [2][4][6]
  [3][5][ ]
  ```
- Empty bottom-right cell = manager compact position (7th window)
- Gap between windows: 0px (edge-to-edge)

## Window cycling (hotkey swap)
- **Backtick** (`` ` ``): cycle next — swaps next secondary to primary monitor full size; current main slot takes vacated secondary spot
- **Alt+`**: cycle previous
- **Shift+F1–F6**: direct slot select
- `slot_driver` hotkey: unset by default

## enb_monitor state machine
Tracks each slot's state by probing TCP connections to the Net-7 server:
- `OFFLINE` → `LOGIN SCREEN` → `CHAR SELECT` → `IN GAME` → `ZONING` → `IN GAME`
- `IN GAME` → `OFFLINE`: triggers auto-relaunch if enabled
- `ZONE FREEZE`: no state change for >20s while in `ZONING`; triggers auto-relaunch if enabled
- `FROZEN?`: no state change for >20s while IN GAME (not yet confirmed in the wild)

## Design principle — everything editable
All macro button presses, delays, and coordinates must be configurable
in the UI. No hardcoded values for anything the user interacts with in-game.
