# Window Management Technical Specs

## Wine Prefix Structure
Each slot has its own Wine prefix for independent registry (resolution) settings.

```
~/.wine-enb        — base prefix, slot 1, game installed here
~/.wine-enb-2      — slot 2 prefix
~/.wine-enb-3      — slot 3 prefix
~/.wine-enb-4      — slot 4 prefix
~/.wine-enb-5      — slot 5 prefix
~/.wine-enb-6      — slot 6 prefix
```

Each secondary prefix symlinks Program Files from base:
- drive_c/Program Files → ~/.wine-enb/drive_c/Program Files
- drive_c/Program Files (x86) → same
- dosdevices → same
- system.reg, user.reg, userdef.reg — COPIED (independent registry)

## Resolution Registry Keys
```
HKLM\SOFTWARE\WOW6432Node\Westwood Studios\Earth and Beyond\Render
  RenderDeviceWidth   REG_DWORD  (hex: 0x280=640, 0x780=1920)
  RenderDeviceHeight  REG_DWORD  (hex: 0x21c=540, 0x438=1080)
  RenderDeviceWindowed REG_DWORD 0x1 (always windowed)
```

## Wine Input Fixes (applied per prefix)
```
HKCU\Software\Wine\DirectInput
  MouseWarpOverride = force

HKCU\Software\Wine\X11 Driver
  UseTakeFocus = N
```

## Launch Command (direct Wine, bypasses hardcoded WINEPREFIX in launcher scripts)
```bash
WINEPREFIX=~/.wine-enb-N /usr/bin/wine start \
    /d "C:\\Program Files (x86)\\Net-7\\bin" \
    "net7proxy.exe" \
    /LADDRESS:0 \
    /ADDRESS:"<server_ip>" \
    /CLIENT:"C:\\Program Files\\EA GAMES\\Earth & Beyond\\release\\client.exe" \
    /DML /EXREORDER /POPT
```

## Window Positioning
- xdotool windowmove <id> x y — works ✓
- xdotool windowsize <id> w h — does NOT work on Wine windows ✗
- wmctrl -ir <hex_id> -e 0,x,y,w,h — move works, resize does NOT ✗
- winresize.exe — SetWindowPos works for position, render res stays fixed

## winresize.exe Usage
Must run under SAME prefix as target window:
```bash
WINEPREFIX=~/.wine-enb-N wine ~/.local/share/enbmb/winresize.exe "Window Title" x y w h
```

FindWindow is scoped to Wine prefix — cannot target windows in other prefixes.

## Window Titles
- At launch: "Earth & Beyond"
- After tool assigns role: role abbreviation (PW, TE, etc.)
- After char name entered: character name
- Title is set via: xdotool set_window --name <title> <id>

## EULA Sequence
1. Window appears titled "Earth & Beyond"
2. Wait 4 seconds
3. Send Enter key (xdotool key --window <id> Return)
4. EULA dismissed, login screen appears ~5 seconds later

## Server IP
- Hostname: sunrise.net-7.org
- Current IP: 216.219.87.147
- Resolve via: dig +short sunrise.net-7.org

## Sounds
- Login music disabled: sounds.ini line 79
  [fe_music.mp3] SoundVolume=0.0000
- File: ~/.wine-enb/drive_c/Program Files/EA GAMES/Earth & Beyond/Data/client/ini/sounds.ini
- Shared across all prefixes via symlink
