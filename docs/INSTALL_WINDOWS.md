# EnB Multibox Manager — Windows Installation Guide

> Counterpart to [docs/INSTALL.md](INSTALL.md) (Linux).

## Requirements

- **OS**: Windows 10 or 11
- **Monitors**: Two monitors recommended. Slot 1 runs full-screen on your primary monitor; slots 2–6 tile on the secondary.
- **Python 3** (with pip) — install from [python.org](https://www.python.org/), check "Add python.exe to PATH" during install
- **Earth & Beyond**: installed via the [Net-7 launcher](https://www.net-7.org). Run it at least once before proceeding. Unlike Linux, this is a single native install used by all 6 slots — no per-slot copies.

---

## Step 1 — Get enbmb

Clone or download the repo to a local folder:

```powershell
git clone https://github.com/emr-rgb/EnBmb
cd EnBmb
```

---

## Step 2 — Run the installer

Double-click **`install.bat`**, or from a terminal:

```powershell
install.bat
```

The installer will:
- Check that Python 3 is installed (and tell you where to get it if not)
- Install required Python packages (`pywin32`, `psutil`, `pynput`)
- Launch enbmb — a UAC prompt is expected on first launch (enbmb needs admin so the game clients don't each pop their own UAC prompt)
- Create a **Desktop shortcut** and **Start Menu entry** ("EnB Multibox Manager") so you don't need to run `install.bat` again

After setup, use the Desktop shortcut or Start Menu entry to launch enbmb. Don't want the shortcuts? Delete either one — enbmb won't recreate one you've removed.

---

## Step 3 — Configure slots in enbmb

On first launch, enbmb will search for `LaunchNet7.exe` automatically and offer to configure all 6 slots in one step. Confirm (or browse to the file if it's in a non-default location) and you're done.

If you need to change the path later: **Settings** → **General** tab → update the launch command for each slot. Every Windows slot uses the same path — all 6 clients share one native install, unlike Linux's per-slot scripts.

After that:
1. Set credentials for each slot (username and password for each character), or assign a Character profile
2. Set the character slot position (which position on the char-select screen, 1–5)

---

## Step 4 — Calibrate coordinates

Same workflow as Linux — see [docs/USER_GUIDE.md](USER_GUIDE.md#calibrating-click-coordinates).

---

## Step 5 — Test your setup

1. **Launch Client Here** on slot 1, run **Auto Login** on just that slot, and verify it lands in-game correctly
2. Once slot 1 works, click **Launch All** to bring up all 6

---

## Updating

```powershell
git pull
```

No installer to re-run — pull the latest code and relaunch. Your `config/settings.json` is untouched by `git pull` as long as you haven't committed local changes over it.

---

## Uninstalling

Delete the enbmb folder, plus the two shortcuts created on first launch:
`Desktop\EnB Multibox Manager.lnk` and the matching one under
`Start Menu\Programs`. Nothing else was installed system-wide — no registry
keys, no services. Your Earth & Beyond install and character data are untouched.

---

## Windows-specific notes

- **UAC elevation required** — enbmb prompts once on launch; this is expected, not a bug.
- **One shared install, not 6 isolated ones** — Mute Sounds, Dark Mode, Privacy, and Save/Load Game Settings all affect every client at once, since there's only one `sounds.ini` / `Dazzle.ini` / `shortcut.ini` on disk to begin with (no Wine prefixes to keep in sync).
- **No Wine, no prefixes, no `setup_prefixes.sh`** — none of the Linux Wine-prefix setup in `docs/INSTALL.md` applies. Skip `install.sh` and `setup_prefixes.sh` entirely; they don't exist for Windows and aren't needed.
