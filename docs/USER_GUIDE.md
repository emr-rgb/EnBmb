# EnB Multibox Manager — User Guide

Complete reference for every part of the UI. Read this when setting up for the first time or when you need to know exactly what a control does.

---

## First-time setup walkthrough

A minimal path from a fresh install to your first Auto Login, in order:

1. **Create character profiles** — Settings → Characters tab → New. Fill in character name, account, password, class, role profile, and char-select position (1–5) for each character you'll multibox.
2. **Assign characters to slots** — on each slot card, ⋮ → Character → pick the profile. This sets the slot's login credentials and char-select position.
3. **Set role profiles** — if a slot's role differs from its character's default, ⋮ → Role Profile to pick a different one. Role profiles (Settings → Roles tab) define the key sequences each loop sends.
4. **Set launch commands** — Settings → General tab → Slot launch commands.
   - **Linux**: `enb-slot1`…`enb-slot6`, created by `setup_prefixes.sh`. These are the defaults and don't need to be set manually unless you used custom names.
   - **Windows**: on first launch enbmb searches for `LaunchNet7.exe` and prompts to configure all 6 slots automatically. If you need to change it later, open Settings → General and update the path (same command for all 6 slots — all share one native install).
5. **Calibrate coordinates** — Settings → Login tab (login button, char-select positions, quit-to-desktop), Loops tab (assist coord), Invite tab, Reform tab. Use the **Set** button workflow on a running game window for each.
6. **Test one slot first** — Launch Client Here on slot 1, run Auto Login on just that slot, and verify it lands in-game correctly before running Launch All across all 6.
7. **Enable checkboxes as needed** — Autologin on Launch All (full unattended launch), Auto-relaunch on crash, and Zone freeze detection (requires Auto-relaunch to also be on).

See the per-tab reference below for details on each setting.

---

## Window layout

The main window has two panels:

- **Left panel** — profile selector, slot cards, invite bar, action buttons, status bar
- **Right panel** — layout canvas, preset bar, monitor selectors, canvas controls and action buttons

**Compact mode** hides the slot cards and invite bar and shrinks the window to fit in the empty grid cell on your secondary monitor. The canvas and action buttons remain accessible.

---

## Left panel

### Profile selector

A **group profile** stores the slot-to-character assignments for a session configuration.

- **Dropdown** — select the active profile (loading it applies its slot assignments)
- **+** — create a new blank profile
- **✕** — delete the current profile (no undo)

Below the profile selector:
- **⟳ Detect** — scan for running EnB windows and assign them to slots (matched by character name first, then by order)
- **Apply Layout** — move and resize all assigned client windows to their grid positions

### Slot cards

Six slot cards, numbered 1–6. Each card shows the slot number, assigned character name, role abbreviation, and current state.

**Character and role assignment** is done via the **three-dot menu (⋮)** or right-click on the card:

- **Character** — assign a character profile (loads credentials and char-select position)
- **Role Profile** — which loop macro profile this slot uses
- **Loop Overrides…** — (only shown when a character is assigned) per-character key overrides layered on top of the role profile. Each loop section (combat, buff, debuff, heal) has its own checkbox — check a section to override it for this character only; unchecked sections fall through to the shared role profile. Buff also has its own "Override Targeted Devices" checkbox (device key, cast time, F1–F6 targets, re-assist — same fields as the role profile's Buff tab); Heal has its own "Override target driver key" checkbox (the TT-only F-key pressed before healing). This is the general mechanism for sharing one role profile across several characters of the same class while tweaking per-character specifics (e.g. different targeted-device F-key assignments) without duplicating the whole profile.
- **Set Role** — manually set the role abbreviation (PW, PS, PP, TE, TT, TS, JE, JD, JS)
- **Set Login Credentials** — set username and password directly without a character profile

Additional options when a window is assigned:
- **Focus Window** — bring the slot's window to the foreground
- **Quit to Desktop** — gracefully exit just this slot (Escape → quit menu click)
- **Kill Client** — force-kill this slot's process
- **Relaunch Client** — kill and relaunch just this slot, then auto-login
- **Clear Slot (keep process)** — remove enbmb's tracking of the window without killing it
- **Always on Top** — pin this slot's window above others
- **Rename Window Title** — change the window title (used for identification)

When the slot is empty:
- **Assign Window** — manually pick from a list of detected EnB windows
- **Launch Client Here** — run the slot's launch command and assign the resulting window

### Invite bar

- **Dropdown** — select an invite list. The built-in "(Slots — auto)" option builds the list from assigned character names in slot order.
- **+** — create a named invite list
- **Edit** — modify the selected invite list

### Action buttons

A ⚙ icon in the **ACTIONS** header opens a visibility editor to show or hide individual buttons per view mode (normal and compact).

| Button | Hotkey | What it does |
|--------|--------|--------------|
| Stop All Scripts | Escape | Stop all running loops and autologin. Does not kill clients. |
| Restart Manager | — | Save settings and restart the application. |
| Combat Loop | Alt+F | Assist (click party target) → fire sequence for each secondary slot. One pass — press again for the next round. |
| Debuff Loop | Alt+D | One-pass debuff rotation across all secondary slots. |
| Buff Loop | — | One-pass buff cycle across all secondary slots. |
| Heal Loop | Alt+H | TT: target driver → patch hull. TE: send repair keys. One pass — press again to repeat. |
| Energy Loop | — | Energy/reactor management keys + one-pass PV9 (if configured). |
| Daimyo | Alt+A | Mode 1: continuous Daimyo/FotW rotation on driver. Mode 2: one manual step across all slots. |
| Mode 1 / Mode 2 | — | Toggle Daimyo between continuous (Mode 1) and manual-step (Mode 2). |
| Invite Party | Alt+I | Send `/invite` to each name in the active invite list, then click accept on each slot. |
| Reform | Alt+R | Driver clicks the formation buttons; all secondary slots press the join key. |
| Compact | — | Toggle compact view. |

**Raid Mode** (View menu → Raid Mode): multiplies all timing delays by 2× or 3×. Toggle cycles Off → 2× → 3× → Off. Use during large raids when rapid keypress frequency causes issues.

### How loops and macros behave

- **Combat, Debuff, Buff, and Heal loops are mutually exclusive** — only one of these four can run at a time. Starting a second one while another is active does nothing except show "*type* loop already running" in the status bar. Stop the running loop first (Escape, or the same button again) before starting a different one.
- **Energy Loop** also can't start while a Combat/Debuff/Buff/Heal loop is running.
- **Daimyo** (Mode 1 continuous or Mode 2 step) runs independently — it can be active at the same time as a Combat/Buff/etc. loop.
- **Invite and Reform are one-shot actions**, not loops. Pressing the hotkey/button starts a sequence that runs to completion; pressing it again while it's still in progress is ignored ("Invite/Reform already running") rather than starting a second overlapping pass.
- **Escape (Stop All Scripts)** sets an abort flag checked between steps of every loop and macro — it stops at the next checkpoint, not instantly. A macro mid-click finishes that click before stopping.
- **Press, don't hold**: hotkeys are meant to be pressed once and released. For loops and Invite/Reform, holding the key (key-repeat) is harmless — the guards above ignore the repeats. For cycling and other one-off binds, holding the key can advance further than you intend.

### Status bar

Single line at the bottom of the left panel showing the most recent operation or any error.

---

## Right panel

### Preset bar

- **Dropdown** — select a built-in or user-saved layout preset
- **Apply** — load the preset's window geometry and apply it to all slots
- **Save As…** — save the current canvas layout as a named preset
- **Delete** — remove the selected user preset (built-in presets are protected)

**Built-in presets** cover common dual-monitor and single-monitor arrangements (1+5, 1+4, 2×2, 6 equal, etc.). Selecting and applying a preset will auto-detect windows if needed, set the secondary slot count, and move all windows into position.

**User presets** save the exact current geometry. Saving with an existing name prompts for overwrite confirmation.

### Monitor selectors and layout controls

- **Primary / Secondary monitor dropdowns** — which detected monitor index each role occupies
- **Secondary slots slider** (0–5) — how many secondary clients are tiled on the secondary monitor. Adjusting this in Auto mode recalculates geometry immediately.
- **Mode label** — shows **AUTO** (green) or **CUSTOM** (orange)
- **Reset to Auto** — exit Custom mode and recalculate layout from slider/monitor settings
- **Apply Layout** — move and resize all assigned windows to their current canvas positions

### Layout canvas

A scaled-down visual of both monitors and where each slot sits. Slots are colored by race (Progen red, Terran blue, Jenquai green) and show character name + role.

**Auto mode**: geometry is driven by the slider and monitor selectors. Dragging any slot or applying a preset switches to Custom mode.

**Custom mode**: geometry is locked to what's on the canvas. Drag slot boxes to move them; drag the bottom-right handle to resize. The **MGR** box represents the manager window itself — drag it to reposition the manager.

**Snapping**: when enabled, slots snap to monitor edges and to other slot edges while dragging.

- **Snap checkbox** — enable/disable snapping
- **Threshold spinbox** — snap distance in pixels (default 20)

Right-clicking a slot box on the canvas opens the same context menu as the slot card.

### Canvas action buttons

**Left column:**

| Button | What it does |
|--------|--------------|
| Launch All | Run each slot's launch command in sequence, dismiss EULA dialogs, then auto-detect all windows. If "Autologin on Launch All" is checked, also runs the full login sequence. |
| Auto Login | Log in all assigned slots sequentially: focus → type credentials → click login → select character → click accept. Slots already showing "IN GAME" in the state monitor are skipped. |
| Top All | Toggle always-on-top on all assigned slot windows. |
| Quit to Desktop | Send Escape → Quit to Desktop click to every assigned slot gracefully. |
| Kill All | Force-kill all EnB client processes immediately. No graceful shutdown — unsaved progress is lost. |
| Launch Independent Client | Launch an additional untracked client in a normal, movable window (not positioned or resized). Not assigned to any slot; enbmb won't manage or relaunch it. **Linux**: uses `~/.local/bin/enb-extra` (its own Wine prefix, `~/.wine-enb-7`, created by `setup_prefixes.sh`). **Windows**: launches the same command as slot 1 (`slot_commands[0]`, i.e. `LaunchNet7.exe`) — there's no separate prefix, just an extra untracked instance of the shared install. |

**Right column:**

| Button | What it does |
|--------|--------------|
| Updates | Open the Net-7 launcher to check for game updates. |
| Mute Sounds | Zero login music, voice, and footstep volumes in `sounds.ini`. Affects all 6 clients on both platforms — Windows has one shared native install; Linux secondary prefixes symlink their `Data/` directory from the base prefix (`~/.wine-enb`), so one file covers all slots. |
| Dark Mode | Reduce star halo/dazzle brightness in `Dazzle.ini` (same shared-file behavior as Mute Sounds). |
| Privacy | Disable broadcast, local, and race chat channels; suppress login announcements. Guild, group, and private chat are unaffected. |
| Save Settings | Back up `shortcut.ini` and player options files to `config/game_settings_backup/`. |
| Load Settings | Restore shortcut and player options files from the last backup. |

**Checkboxes:**

- **Autologin on Launch All** — when checked, Launch All automatically runs the full login sequence after all windows appear. Uncheck to launch clients without auto-logging in.
- **Auto-relaunch on crash** — when checked, if a slot's client exits unexpectedly from IN GAME state, enbmb automatically relaunches it and logs back in. See [Auto-relaunch](#auto-relaunch) below.
- **Zone freeze detection** — when checked (and Auto-relaunch is also on), a timer arms the moment a slot starts zoning; if that slot's arrival isn't confirmed within the configured timeout (default 20s), it's treated as frozen and relaunched.
  - **Linux**: each slot has its own Wine prefix and its own real `chat.log`, watched independently — solo zoning or different sectors won't trigger false relaunches for other slots. (Per `docs/LESSONS.md`'s "chat.log sharing across Wine prefixes" fix, validated 2026-06-07.)
  - **Windows**: all 6 slots share one native game install, so there's only one `chat.log` for everyone. Any new line in it — from any slot — counts as an arrival signal for every slot currently being watched. This is intentional (phrase-matching specific "you have entered" text is unreliable; any activity at all is treated as proof of life), but it means a genuinely frozen slot's timer can get reset by unrelated chat activity from a different slot. In practice this makes Windows zone freeze detection slightly less sensitive than Linux's, not more error-prone — it still won't falsely flag a slot as frozen, it just may take longer to catch a real freeze if other slots are active.

---

## Settings window

Open via the ⚙ gear button in the profile bar. All changes save immediately.

---

### Hotkeys tab

Click the field next to any action, press the key or combination to bind it. Escape cancels. ✕ clears the binding.

Hotkeys are registered system-wide via pynput — they fire regardless of which window is focused. Don't bind keys your desktop environment already uses.

**Window cycling:**

| Action | Default |
|--------|---------|
| Cycle Next Window | `` ` `` (backtick) |
| Cycle Previous Window | Alt+`` ` `` |
| Return to Driver (Slot 1) | — |
| Direct focus Slot 1–6 | Shift+F1 through Shift+F6 |
| Assign Driver | Alt+G |

**Macros:**

| Action | Default |
|--------|---------|
| Start Combat Loop | Alt+F |
| Stop / Abort | Escape |
| Invite Party | Alt+I |
| Reform | Alt+R |
| Heal Cycle | Alt+H |
| Debuff Cycle | Alt+D |
| Buff Loop | — |
| Energy Loop | — |
| Daimyo Loop / Step | — |
| Daimyo Step (alt) | Alt+A |

**Tool window:**

| Action | Default |
|--------|---------|
| Bring Manager to Front | Ctrl+Alt+M |

**Reset Hotkeys to Default** button restores all bindings to the defaults above.

---

### General tab

| Setting | Default | Description |
|---------|---------|-------------|
| Action delay (ms) | 50 | Pause between steps in macros and loops. |
| Char type delay (ms) | 10 | Delay between keystrokes when typing credentials. |
| Launch delay (ms) | 3000 | Wait after dismissing a slot's EULA before launching the next slot. |
| Default formation key | t | Key secondary slots press to join a formation. |
| Slot launch commands | enb-slot1 … enb-slot6 (Linux) / `LaunchNet7.exe` path ×6 (Windows) | Command used to launch each slot. Linux: defaults to `enb-slot1`…`enb-slot6` (created by `setup_prefixes.sh`) — no manual entry needed unless you used custom names. Windows: auto-configured on first launch via the LaunchNet7.exe setup dialog; same path repeated for all 6 slots. |

---

### Login tab

All click positions are set as **percentages** relative to each window's top-left corner — one calibration works for any window size.

Click **Set** next to any coordinate field, then click the target position inside a running game window. The percentage is calculated and saved automatically.

**Login coordinates:**
- **Accept / Login button** (x%, y%) — where to click the login button

**Character select positions (1–5):**
- Five coordinate pairs (x%, y%) — the click position of each character name button on the char-select screen, numbered by their visual slot position in the game's list

Each character profile stores *which* position (1–5) its character occupies. The coordinates here define *where* those positions are on screen.

**Char select timing:**

| Setting | Default | Description |
|---------|---------|-------------|
| Settle delay (ms) | 6000 | Wait after clicking login before the char-select screen is ready. |
| Button ready delay (ms) | 1200 | Wait after clicking the character name before clicking Accept. |
| Accept delay (ms) | 1200 | Additional wait after clicking Accept. |

**Quit to Desktop coordinates:**
- **In-game** (x%, y%) — position of the Quit to Desktop button in the in-game escape menu
- **Pre-game** (x%, y%) — exit button position on login/char-select screens. Leave at 0,0 to fall back to Alt+F4 for pre-game screens.

---

### Monitors tab

Shows detected monitors: index, name, resolution, and screen position.

- **Refresh Monitor Detection** — re-scan if a monitor was connected after launch
- **Main window monitor index** — which monitor slot 1 (the driver) occupies
- **Secondary windows monitor index** — which monitor slots 2–6 occupy

Monitor indices start at 0. To check your monitor names and positions: Linux, run `xrandr --query`; Windows, open Settings → System → Display (or `Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID` in PowerShell for raw details).

---

### Layout tab

| Setting | Default | Description |
|---------|---------|-------------|
| Window gap (px) | 0 | Pixel gap between tiled secondary windows. 0 = edge-to-edge. |
| Default secondary slot count | 5 | How many secondary slots appear in the grid at startup. |
| Taskbar height (px) | 0 | Height of your desktop panel. Set this if your panel is always visible so windows don't sit under it. |
| Taskbar on monitor | 0 | Which monitor index has the panel. |

**Lock windows to 4:3 aspect ratio** (checkbox) — forces every grid cell to a 4:3 aspect ratio regardless of monitor shape, useful if EnB renders incorrectly at non-4:3 window sizes. Affects all built-in layouts and presets.

Windows are automatically made borderless (no title bar) when assigned to a slot — required for accurate click coordinates and clean tiling.

---

### Invite tab

Where to click the group invite accept button that appears on each secondary slot.

One shared coordinate (x%, y%) applies to all slots — calibrate from any game window in place (the percentage adapts to any window size).

**Camera rotation**: the invite sequence slides the mouse downward before sending invites on the driver, and again after clicking accept on each secondary. This rotates the camera to a consistent position. The slide amount (default 500px over 300ms, scaled by window height) is not in the Settings UI — edit `invite_accept.slide_down_px` and `invite_accept.slide_down_ms` in `config/settings.json` directly if you need to adjust it.

---

### Reform tab

| Setting | Default | Description |
|---------|---------|-------------|
| Formation button (click 1) | x%, y% | Driver clicks here to open the formation menu. |
| Delay between clicks (ms) | 200 | Wait between click 1 and click 2. |
| Formation type (click 2) | x%, y% | Driver clicks here to select the formation type. |
| Settle delay (ms) | 1000 | Wait after click 2 before secondary slots press the join key. |
| Formation join key | t | Key each secondary slot presses to join. |
| Key delay (ms) | 300 | Wait after focusing each slot before pressing the join key. |

---

### Loops tab

Controls how macro keys are sent during Combat, Debuff, Buff, and Heal loops.

| Setting | Default | Description |
|---------|---------|-------------|
| Key press delay (ms) | 40 | Pause between each key press within a slot's key sequence. |
| Key hold time (ms) | 30 | How long each key is held before releasing. |
| Modifier delay (ms) | 50 | Delay between pressing Alt and the main key (for combos like Alt+6). |
| Activation settle (ms) | 300 | Delay after switching window focus to a different slot, before sending input. Prevents formation drops caused by sending input too soon after a focus switch (most noticeable with Autofollow). Re-activating the same window uses a short fixed delay instead. |
| Activation settle 2x raid (ms) | 400 | Same, but used when raid mode is set to 2x. |
| Activation settle 3x raid (ms) | 500 | Same, but used when raid mode is set to 3x. |
| Fire key | f | Pressed after the assist click in combat loops. |

**Assist coord** (x%, y%) — where to click to assist the target. One shared position applied to all slots. Calibrate by hovering over your assist button in any game window and clicking Set.

> The three Activation settle values are independent — each applies only when that raid
> mode is active. They are **not** scaled by raid mode the way Key press delay/Key hold
> time/Modifier delay are; set each one to the value you want for that mode directly.

**Interleave buff loops** (checkbox) — when on, every buffer hits each target before moving to the next, so all targets get their first buff sooner (faster overall with multiple buffers). When off, each buffer finishes all of its targets before the next buffer starts.

---

### Indicator tab

A small overlay on the main monitor showing which slot is currently active.

| Setting | Default | Description |
|---------|---------|-------------|
| Show indicator | off | Enable/disable the overlay. |
| Content | Slot number | What to display: slot number, role abbreviation, or character name. |
| Position (X, Y) | 20, 280 | Screen coordinates of the overlay. |
| Opacity | 85% | Transparency (10–100%). |
| Text color | #ffffff | Hex color of the text. |
| Font size | 48 pt | Font size. |

Click **Move indicator** to drag the overlay into position interactively.

---

### Roles tab

Role profiles define which keys each slot presses for each loop type. Profiles are stored in `roles/profile_<name>.json`.

**Profile list**: New, Duplicate, Delete. Select a profile to edit it.

**Each role profile has:**

- **Name, Description, Class** (PW/PS/PP/TE/TT/TS/JE/JD/JS or blank)

**Combat tab** — up to 12 keys pressed in order after each assist click.

**Buff tab** — up to 12 simple key presses (no targeting), plus up to 3 **targeted devices**. Each targeted device has:
- Device key (hotbar slot)
- Whether to reassist and fire after each target
- Cast time (seconds)
- Target list: F1–F6 (F1=self, F2=driver, F3–F6=party members 3–6)

**Debuff tab** — up to 12 keys in order.

**Heal tab** — up to 12 keys, plus a **Target driver key** (F-key to press before healing, used by TT to target the driver for hull patch).

**Energy tab** — up to 12 keys, plus optional **Power Vortex EM9** one-pass:
- Enable/disable checkbox
- Reactor key (hotbar slot)
- Buff order (6 F-key positions)

**Daimyo tab** — for PS Sentinel device rotation and Focus of the Warder:

*Daimyo* (PS only):
- Device key
- Interval (seconds) — wait between each target in the rotation
- Buff order (F1=self, F2=driver, F3–F6=party)

*Focus of the Warder* (any class, overrides Daimyo for non-PS):
- Enable checkbox
- Device key
- Cooldown (seconds, default 6 — FotW has a 6s cooldown)
- Buff order (same F-key scheme)

**Mode 1** (continuous) runs the configured rotation on the driver slot in a loop until stopped. **Mode 2** (manual step) fires one pass across all assigned secondary slots per button press or hotkey, skipping any slot whose interval hasn't elapsed.

---

### Characters tab

Character profiles hold per-character login and gameplay data.

**Each character has:**

| Field | Description |
|-------|-------------|
| Character name | In-game name |
| Account | Login username |
| Password | Login password (stored locally in plaintext — never transmitted) |
| Class | EnB class abbreviation |
| Role profile | Which loop profile to use for this character |
| Char-select position | Which slot (1–5) this character occupies on the character selection screen |
| Notes | Free-form text |

Assign a character to a slot via the slot card's ⋮ menu → Character. The slot then uses that character's credentials and char-select position during Auto Login.

---

## Auto-relaunch

When **Auto-relaunch on crash** is enabled, enbmb watches each slot's client state. If a slot goes offline unexpectedly while in game, enbmb:

1. Kills any remaining process for that slot
2. Waits briefly
3. Runs the slot's configured launch command
4. Dismisses the EULA
5. Waits for the login window, then runs the full autologin sequence

**To intentionally close a client**, use Quit to Desktop (graceful menu exit) or the **Kill Client** right-click option — both suppress auto-relaunch.

If multiple slots crash simultaneously (within 2 seconds of each other), enbmb treats it as a global crash: kills all remaining processes and runs Launch All instead of relaunching slots one at a time.

---

## Window cycling

Cycling swaps the currently active secondary slot with the main monitor slot.

- **Cycle Next** (backtick) — bring the next secondary slot to the main monitor
- **Cycle Prev** (Alt+backtick) — bring the previous secondary slot
- **Direct focus** (Shift+F1–F6) — bring a specific slot to the main monitor immediately
- **Assign Driver** (Alt+G) — designate whatever slot is currently on the main monitor as the driver

The driver slot runs at whatever size and position it's configured to in the layout (typically, but not necessarily, full primary-monitor resolution). Secondary slots are tiled at whatever grid size the layout defines.

> **Note:** Shift+F1 ("Direct focus Slot 1") always brings *slot 1* (the
> window in canvas position 1) to the main monitor — it does **not** follow
> Alt+G. If you've reassigned the driver to a different slot with Alt+G,
> Shift+F1 will still switch back to slot 1, not your reassigned driver. The
> on-screen indicator now reflects this correctly (it shows slot 1 after
> Shift+F1, even if Alt+G previously pointed elsewhere).

---

## Auto Login sequence

When Auto Login runs (or Launch All with Autologin checked):

For each assigned slot in order:
1. Focus the slot's window
2. Tab navigate to the username field, type the username
3. Tab to the password field, type the password
4. Click the login button at the configured coordinate
5. Wait the settle delay for char-select to appear
6. Click the character's position button (1–5)
7. Wait the button-ready delay
8. Click Accept

---

## Calibrating click coordinates

All login, char-select, assist, invite, and reform coordinates use the **Set** button workflow:

1. Have a running game window visible
2. Click **Set** next to the coordinate field
3. A small overlay appears — move your mouse over the exact target pixel in the game window
4. Press **Space** to confirm
5. enbmb calculates the percentage and saves it

For login and char-select: calibrate once — the percentage adapts to any window size automatically.

For assist coords (Loops tab): calibrate from any game window at any slot size.

---

## Layout presets

Built-in presets cover the most common monitor configurations:

**Dual monitor:**
- 1+5, 1+4, 1+3, 1+2, 1+1 — driver full-screen on primary, N equal slots on secondary
- 2×2 — 2 equal on each monitor

**Single monitor:**
- 6 equal, 4 equal, 3 equal, 2 equal
- 1 large+5, 1 large+3 — driver takes top-left 2/3 of monitor; remaining slots fill around it

**Preview**: selecting a preset from the dropdown immediately shows where windows would land on the canvas, without moving anything. The preview clears when you click Apply (or Apply Layout) or select a different preset.

Applying a preset:
1. If fewer windows are assigned than the preset needs, enbmb runs Detect first
2. Sets the secondary slot count to match
3. Minimizes and unassigns any slots above the new count
4. Moves all windows to the new positions

To save your own arrangement, position slots how you want them on the canvas and click **Save As…**.

---

## Independent client

The **Launch Independent Client** button (right panel) launches an additional game client outside the slot system. It is not tracked, not assigned to a slot, and not subject to auto-relaunch. Use this to run a personal character alongside your managed 6-pack — e.g. for banking or trading while your slots are running.

- **Linux**: uses `~/.local/bin/enb-extra`, running in its own Wine prefix (`~/.wine-enb-7`), created automatically by `setup_prefixes.sh`.
- **Windows**: launches the same command as slot 1 (`slot_commands[0]`) — there's no separate prefix to isolate it in, since all clients already share one native install. enbmb excludes its window and process ID from Detect/Apply Layout/the monitor so it's never mistaken for a managed slot.

Unlike the managed slots, this client opens as a **normal window with a titlebar** — no forced position or size. Drag it to whichever monitor you want, or resize it, same as you would with any other window. Close it manually when done — Kill All does not affect it.

---

## Tips

- Calibrate all click coordinates in Settings before your first Auto Login run. Wrong coordinates are the most common cause of failed logins.
- Apply Layout after Detect to ensure all windows are correctly sized and positioned before running loops.
- Compact mode fits exactly in the empty bottom-right cell of a 3×2 grid, keeping the manager accessible without covering any client window.
- The button visibility editor (⚙ in the ACTIONS header) lets you hide buttons you don't use, in both normal and compact view independently.
- Raid Mode (View → Raid Mode) is useful when rapid keypress frequency causes server-side issues in large groups.
- Global hotkeys capture before any application sees them. If a hotkey stops responding, check for conflicts with your desktop environment.
