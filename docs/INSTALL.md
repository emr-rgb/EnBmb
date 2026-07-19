# EnB Multibox Manager — Installation Guide

> **Tested only on Arch / CachyOS, X11.** `install.sh` detects pacman, apt, dnf, and
> zypper and installs the equivalent packages for each — but only the pacman path has
> actually been run. On other distros, package names are best-effort; if something
> fails (especially wine/wine-staging, see below), install it manually.

## Requirements

- **OS**: Arch Linux or an Arch-based distro (Manjaro, EndeavourOS, CachyOS, etc.) — required for `install.sh`
- **Monitors**: Two monitors recommended. Slot 1 runs full-screen on your primary monitor; slots 2–6 tile on the secondary.
- **Earth & Beyond**: Already installed in a Wine prefix (default: `~/.wine-enb`). The easiest way to get EnB running on Linux is the [ciphersimian Linux installer](https://github.com/ciphersimian/enb-linux-installer). Alternatively, install manually via the [Net-7 launcher](https://www.net-7.org). Run the launcher at least once before proceeding.
- **Wine**: wine-staging recommended (installed automatically by the install script if missing)

---

## Step 1 — Install enbmb

Clone or download the repo, then run the installer:

```bash
git clone https://github.com/emr-rgb/EnBmb enbmb
cd enbmb
bash install.sh
```

The installer will:
- Detect your package manager (pacman, apt, dnf, or zypper)
- Check for and offer to install missing system packages
- Check for and offer to install `pynput` (`pip`)
- Ask whether to install for your user only (recommended) or system-wide
- Copy files, create the `enbmb` launcher, and add an app menu entry plus a Desktop icon

After install, you can launch enbmb from your app launcher (search **EnB**), the icon on your Desktop, or by typing `enbmb` in a terminal. Don't want the Desktop icon? Delete it — it's not load-bearing.

### Non-Arch distros (best-effort, untested)

`install.sh` will detect apt/dnf/zypper and try to install the right package names, but
this path hasn't been run on a real system — only pacman has. If the automatic install
fails, install the equivalent packages manually (or skip `install.sh` and run
`python main.py` directly from the repo):

| Need | Debian/Ubuntu (apt) | Fedora (dnf) | openSUSE (zypper) |
|---|---|---|---|
| Python 3 | `python3`, `python3-pip` | `python3`, `python3-pip` | `python3`, `python3-pip` |
| Python Xlib | `python3-xlib` | `python3-xlib` | `python3-xlib` |
| psutil | `python3-psutil` | `python3-psutil` | `python3-psutil` |
| Tkinter | `python3-tk` | `python3-tkinter` | `python3-tk` (or `python3<ver>-tk`) |
| xdotool, wmctrl | `xdotool`, `wmctrl` | `xdotool`, `wmctrl` | `xdotool`, `wmctrl` |
| wine | `wine` | `wine` | `wine` |
| pynput | `pip install --user pynput` (all distros) | | |

**About wine:** any working wine install is enough for `install.sh` to proceed, but
`wine-staging` is recommended (plain wine has input-timing issues on non-primary
monitors — see Limitations in the README). `wine-staging` is only in Arch's default
repos. On Debian/Ubuntu/Fedora/openSUSE you'll likely need to add a third-party repo
for it — see [WineHQ's download page](https://wiki.winehq.org/Download) or, on
openSUSE, the `Emulators:Wine` OBS repo. Whether EnB and enbmb work correctly on
whatever wine version your distro ships by default is untested.

---

## Step 2 — Set up Wine prefixes

enbmb runs each of the 6 game clients in its own isolated Wine environment. The setup script creates these automatically:

```bash
bash ~/.local/share/enbmb/setup_prefixes.sh
```

The script will:
- Auto-detect your EnB installation (searches `~/.wine-enb` and other common locations; asks if not found)
- Auto-detect your monitor layout via `xrandr`
- Create Wine prefixes for slots 2–6 (slot 1 reuses your existing install)
- Apply per-prefix registry settings (resolution, mouse input fixes)
- Create per-slot launch scripts in `~/.local/bin/`

To recreate a single prefix (e.g. after a Wine update):

```bash
bash ~/.local/share/enbmb/setup_prefixes.sh --force 3
```

To recreate all prefixes:

```bash
bash ~/.local/share/enbmb/setup_prefixes.sh --force
```

### Monitor layout note

The script detects your primary and secondary monitors automatically. The detected layout is printed at the start of the run — verify it looks correct before the script continues. If it's wrong, you can override it:

```bash
PRIMARY_W=1920 PRIMARY_H=1080 PRIMARY_X=0 PRIMARY_Y=0 \
SECONDARY_W=1920 SECONDARY_H=1080 SECONDARY_X=1920 SECONDARY_Y=0 \
bash setup_prefixes.sh
```

> **Warning — primary monitor may not stick**: On some systems the primary monitor designation resets after login, causing the game to open on the wrong monitor. If this happens, you need a login script to force it. Add the following to your session startup (e.g. `~/.xprofile` or your display manager's autostart):
>
> ```bash
> xrandr --output <your-primary-output> --primary
> ```
>
> Replace `<your-primary-output>` with your monitor's output name (find it with `xrandr --query`, e.g. `DP-1` or `HDMI-A-1`).

---

## Step 3 — Configure slots in enbmb

1. Launch enbmb
2. Open **Settings**
3. Launch commands default to `enb-slot1` … `enb-slot6` automatically — no manual entry needed unless you used custom script names in Step 2
4. Set credentials for each slot (username and password for each character)
5. Set the character slot position (which position on the char-select screen, 1–5)

---

## Step 4 — First launch

1. Click **Launch All** — all 6 clients will start, dismiss their EULA dialogs, and position themselves automatically
2. Click **Auto-Login** — enbmb will log in all slots sequentially and land each on the correct character
3. Use hotkeys or the cycle button to bring any slot to your main monitor

---

## Updating

To update enbmb, pull the latest code and re-run the installer:

```bash
cd enbmb
git pull
bash install.sh
```

The installer will not overwrite your existing `config/settings.json` on reinstall, so your settings are preserved.

---

## Uninstalling

```bash
rm -rf ~/.local/share/enbmb
rm -f ~/.local/bin/enbmb
rm -f ~/.local/share/applications/enbmb.desktop
rm -f ~/.local/share/icons/hicolor/32x32/apps/enbmb.png
```

Wine prefixes (`~/.wine-enb`, `~/.wine-enb-2` through `~/.wine-enb-6`) are not touched — they contain your game installation and character data.
