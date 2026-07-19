# Hotkeys and Macros Specification

## Global Hotkeys (via pynput, work system-wide)

All hotkeys are configurable in Settings → Hotkeys.

### Window Cycling
| Action | Default | Description |
|--------|---------|-------------|
| Cycle Next | ` (backtick) | Swap next secondary slot to main monitor |
| Cycle Prev | Alt+` | Swap previous secondary slot to main monitor |
| Return to Driver | (unset) | Restore slot 1 to main monitor |
| Direct Slot 1 | Shift+F1 | Directly swap slot 1 to main |
| Direct Slot 2 | Shift+F2 | Directly swap slot 2 to main |
| Direct Slot 3 | Shift+F3 | Directly swap slot 3 to main |
| Direct Slot 4 | Shift+F4 | Directly swap slot 4 to main |
| Direct Slot 5 | Shift+F5 | Directly swap slot 5 to main |
| Direct Slot 6 | Shift+F6 | Directly swap slot 6 to main |

### Macros
| Action | Default | Description |
|--------|---------|-------------|
| Combat Loop | Alt+F | Start/stop combat assist cycle |
| Abort | Escape | Stop all running loops and macros |
| Invite | Alt+I | Send /invite to all names in active invite list |
| Reform | Alt+R | Set formation on driver, all others join |
| Heal Cycle | Alt+H | One-pass heal rotation across all secondary slots |
| Debuff Cycle | Alt+D | One-pass debuff rotation across all secondary slots |
| Buff Loop | (unset) | One-pass buff cycle across all secondary slots |
| Energy Loop | (unset) | Energy/reactor management pass across all secondary slots |
| Daimyo Loop / Step | (unset) | Start Daimyo Mode 1 loop, or fire one Mode 2 step |
| Daimyo Step (alt) | Alt+A | Same as Daimyo Loop / Step — second bindable hotkey |
| Assign Driver | Alt+G | Make whoever is on main monitor the driver for all loops |

### Tool Window
| Action | Default | Description |
|--------|---------|-------------|
| Manager to Front | Ctrl+Alt+M | Raise the multibox manager window |

---

## Window Cycle Behavior

When cycling (backtick):
1. Current main-monitor slot swaps to the vacated secondary grid position
2. Next secondary slot moves to the main monitor full size
3. Cycled window receives focus
4. Pressing cycle again advances to the next slot in sequence
5. Return-to-driver restores slot 1 to the main monitor

---

## Invite Macro Sequence

1. Focus driver window
2. Slide mouse downward on driver window (camera rotation — positions camera before typing)
3. For each name in the active invite list: open chat (Return), type `/invite <name>`, send (Return)
4. For each secondary slot: focus in place, click the accept button at the configured coordinate, slide mouse downward (camera rotation)
5. Return focus to driver

Camera slide amount defaults to 500px over 300ms, scaled by window height. Configurable via `invite_accept.slide_down_px` / `invite_accept.slide_down_ms` in settings.json (not exposed in Settings UI).

---

## Reform Macro Sequence

1. Focus slot 1 (driver)
2. Click formation button 1 at configured coordinates
3. Wait configured delay
4. Click formation button 2 at configured coordinates
5. For each secondary slot: focus window, send formation join key (default: `t`)

---

## Combat Loop Sequence

Loops run until stopped or Escape is pressed. Each pass:
1. For each secondary slot (in order):
   a. Focus window in place (no cycling — window stays in grid position)
   b. Click assist coordinate for that slot's monitor size
   c. Send role's configured key sequence (e.g. `["1", "2", "3", "f"]`)
2. Repeat continuously until aborted

---

## Daimyo Modes

**Mode 1 — continuous loop**: runs on the driver slot only. Activates the Daimyo device (PS) or FotW device on each configured buff target in sequence, waiting the configured interval between each activation. Loops until stopped.

**Mode 2 — single step**: each hotkey press makes one pass across all assigned secondary slots. For each slot, advances one step through its target rotation and fires only if that slot's interval has elapsed since the last fire.

Toggle between modes with the Mode button in the UI or the Daimyo mode toggle hotkey.

---

## Role Key Sequences (examples)

Key sequences are configured per role profile in Settings → Role Profiles.

- PW: `["1", "2", "3", "f"]` — abilities + fire
- TE: `["1", "2", "f"]` — abilities + fire
- TT: `["h"]` — hull patch
- JD: `["1", "2"]` — abilities
- JS: `["1"]` — primary ability

---

## Timing Values (all configurable in Settings)

- Action delay: 50ms between macro steps
- Loop key delay: 40ms between keystrokes in a macro sequence
- Char type delay: 10ms between keystrokes when typing login credentials
- Invite accept settle: 600ms after focus before clicking accept
- Reform settle: 1000ms after formation click before sending join key
- Launch gap: 3000ms between slot launches
