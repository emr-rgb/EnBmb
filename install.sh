#!/bin/bash
# ============================================================
#  EnB Multibox Manager — install.sh
#
#  Installs enbmb. Detects pacman/apt/dnf/zypper and installs
#  system dependencies, copies files, creates a launcher script
#  and desktop entry.
#
#  Tested only on Arch/CachyOS (X11). On other distros, package
#  names are best-effort — see docs/INSTALL.md if something
#  fails, especially for wine/wine-staging.
#
#  Usage:
#    bash install.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colours ───────────────────────────────────────────────────

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
BOLD='\033[1m'; RESET='\033[0m'

info()  { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()  { echo -e "  ${YELLOW}!${RESET} $*"; }
err()   { echo -e "  ${RED}✗${RESET} $*" >&2; }
header(){ echo -e "\n${BOLD}$*${RESET}"; }

# ── Dependency check ──────────────────────────────────────────

header "Checking dependencies…"

if command -v pacman &>/dev/null; then
    PM=pacman
elif command -v apt-get &>/dev/null; then
    PM=apt
elif command -v dnf &>/dev/null; then
    PM=dnf
elif command -v zypper &>/dev/null; then
    PM=zypper
else
    PM=unknown
fi

case "$PM" in
    pacman) info "Package manager: pacman (Arch-based)" ;;
    apt)    info "Package manager: apt (Debian/Ubuntu-based)" ;;
    dnf)    info "Package manager: dnf (Fedora-based)" ;;
    zypper) info "Package manager: zypper (openSUSE-based)" ;;
    *)      warn "Unrecognized package manager" ;;
esac

if [ "$PM" != "pacman" ]; then
    warn "enbmb is tested on Arch/CachyOS only. Package names below are best-effort"
    warn "for your distro — see docs/INSTALL.md if anything fails."
fi

declare -A PKG_NAME
case "$PM" in
    pacman)
        PKG_NAME[psutil]=python-psutil
        PKG_NAME[xlib]=python-xlib
        PKG_NAME[tk]=tk
        PKG_NAME[xdotool]=xdotool
        PKG_NAME[wmctrl]=wmctrl
        PKG_NAME[wine]=wine-staging
        ;;
    apt)
        PKG_NAME[psutil]=python3-psutil
        PKG_NAME[xlib]=python3-xlib
        PKG_NAME[tk]=python3-tk
        PKG_NAME[xdotool]=xdotool
        PKG_NAME[wmctrl]=wmctrl
        PKG_NAME[wine]=wine
        ;;
    dnf)
        PKG_NAME[psutil]=python3-psutil
        PKG_NAME[xlib]=python3-xlib
        PKG_NAME[tk]=python3-tkinter
        PKG_NAME[xdotool]=xdotool
        PKG_NAME[wmctrl]=wmctrl
        PKG_NAME[wine]=wine
        ;;
    zypper)
        PKG_NAME[psutil]=python3-psutil
        PKG_NAME[xlib]=python3-xlib
        PKG_NAME[tk]=python3-tk
        PKG_NAME[xdotool]=xdotool
        PKG_NAME[wmctrl]=wmctrl
        PKG_NAME[wine]=wine
        ;;
esac

pkg_install() {
    case "$PM" in
        pacman) sudo pacman -S --noconfirm "$@" ;;
        apt)    sudo apt-get install -y "$@" ;;
        dnf)    sudo dnf install -y "$@" ;;
        zypper) sudo zypper install -y "$@" ;;
    esac
}

MISSING_LABELS=()
MISSING_PKGS=()

check_module() {
    # $1 = python module name, $2 = key into PKG_NAME, $3 = label
    if python3 -c "import $1" &>/dev/null; then
        info "$3"
    else
        warn "$3 — not installed"
        MISSING_LABELS+=("$3")
        [ "$PM" != "unknown" ] && MISSING_PKGS+=("${PKG_NAME[$2]}")
    fi
}

check_binary() {
    # $1 = binary name, $2 = key into PKG_NAME, $3 = label
    if command -v "$1" &>/dev/null; then
        info "$3"
    else
        warn "$3 — not installed"
        MISSING_LABELS+=("$3")
        [ "$PM" != "unknown" ] && MISSING_PKGS+=("${PKG_NAME[$2]}")
    fi
}

if command -v python3 &>/dev/null; then
    info "python3"
else
    err "python3 not found — install it via your distro's package manager and re-run."
    exit 1
fi

check_module Xlib     xlib    "Python Xlib"
check_module psutil   psutil  "psutil"
check_module tkinter  tk      "Tkinter"
check_binary  xdotool xdotool "xdotool"
check_binary  wmctrl  wmctrl  "wmctrl"

# Wine: any wine (staging or plain) is acceptable
if command -v wine &>/dev/null; then
    info "wine"
else
    warn "wine — not installed"
    MISSING_LABELS+=("wine")
    if [ "$PM" = "pacman" ]; then
        MISSING_PKGS+=(wine-staging)
    elif [ "$PM" != "unknown" ]; then
        MISSING_PKGS+=("${PKG_NAME[wine]}")
    fi
fi

# pynput is pip-only on every distro
if python3 -c "import pynput" &>/dev/null; then
    info "pynput (pip)"
else
    warn "pynput — not installed"
fi

if [ ${#MISSING_LABELS[@]} -gt 0 ]; then
    if [ "$PM" = "unknown" ]; then
        echo ""
        err "Missing dependencies: ${MISSING_LABELS[*]}"
        err "Unrecognized package manager — install these manually (see docs/INSTALL.md) and re-run."
        exit 1
    fi

    echo ""
    echo -e "  Missing packages: ${BOLD}${MISSING_PKGS[*]}${RESET}"
    read -rp "  Install them now? [Y/n] " yn
    yn="${yn:-Y}"
    if [[ "$yn" =~ ^[Yy] ]]; then
        if ! pkg_install "${MISSING_PKGS[@]}"; then
            err "Some packages failed to install."
            for p in "${MISSING_PKGS[@]}"; do
                if [[ "$p" == wine* ]]; then
                    warn "wine/wine-staging may need a third-party repo on your distro"
                    warn "(e.g. WineHQ: https://wiki.winehq.org/Download, or openSUSE's"
                    warn "Emulators:Wine repo). See docs/INSTALL.md."
                    break
                fi
            done
            warn "Install the remaining packages manually and re-run."
            exit 1
        fi
    else
        err "Missing dependencies — install them manually and re-run."
        exit 1
    fi
fi

if ! python3 -c "import pynput" &>/dev/null; then
    echo ""
    warn "pynput is required but not installed."
    read -rp "  Install with pip? [Y/n] " yn
    yn="${yn:-Y}"
    if [[ "$yn" =~ ^[Yy] ]]; then
        pip install --user pynput
    else
        err "pynput is required — install it manually and re-run."
        exit 1
    fi
fi

# ── Install location ──────────────────────────────────────────

header "Install location"
echo ""
echo "  1) User-only  — ~/.local/share/enbmb   (no sudo needed, recommended)"
echo "  2) System-wide — /opt/enbmb             (requires sudo)"
echo ""
read -rp "  Choice [1]: " choice
choice="${choice:-1}"

if [ "$choice" = "2" ]; then
    INSTALL_DIR="/opt/enbmb"
    BIN_DIR="/usr/local/bin"
    DESKTOP_DIR="/usr/share/applications"
    NEED_SUDO=1
else
    INSTALL_DIR="$HOME/.local/share/enbmb"
    BIN_DIR="$HOME/.local/bin"
    DESKTOP_DIR="$HOME/.local/share/applications"
    NEED_SUDO=0
fi

echo ""
info "Install dir : $INSTALL_DIR"
info "Launcher    : $BIN_DIR/enbmb"
info "Desktop entry: $DESKTOP_DIR/enbmb.desktop"

# ── Copy files ────────────────────────────────────────────────

header "Installing files…"

COPY_CMD="cp -r"
MKDIR_CMD="mkdir -p"
if [ "$NEED_SUDO" = "1" ]; then
    COPY_CMD="sudo cp -r"
    MKDIR_CMD="sudo mkdir -p"
fi

$MKDIR_CMD "$INSTALL_DIR"

# Copy all Python source files
for f in "$SCRIPT_DIR"/*.py; do
    $COPY_CMD "$f" "$INSTALL_DIR/"
done

# Copy winresize binary and source
$COPY_CMD "$SCRIPT_DIR/winresize.exe" "$INSTALL_DIR/"
$COPY_CMD "$SCRIPT_DIR/winresize.c"   "$INSTALL_DIR/"

# Copy setup script
$COPY_CMD "$SCRIPT_DIR/setup_prefixes.sh" "$INSTALL_DIR/"

# Copy root-level docs and assets
$COPY_CMD "$SCRIPT_DIR/README.md"  "$INSTALL_DIR/"
$COPY_CMD "$SCRIPT_DIR/enbmb.ico"  "$INSTALL_DIR/"

# Copy config and role templates (not personal settings)
$MKDIR_CMD "$INSTALL_DIR/config"
if [ ! -f "$INSTALL_DIR/config/settings.json" ]; then
    # Only copy default settings if no existing config (preserve user settings on reinstall)
    $COPY_CMD "$SCRIPT_DIR/config/settings.json" "$INSTALL_DIR/config/" 2>/dev/null || true
fi

$MKDIR_CMD "$INSTALL_DIR/roles"
for f in "$SCRIPT_DIR/roles"/*.json; do
    [ -f "$f" ] || continue
    $COPY_CMD "$f" "$INSTALL_DIR/roles/"
done

$MKDIR_CMD "$INSTALL_DIR/docs"
for f in "$SCRIPT_DIR/docs"/*.md; do
    [ -f "$f" ] || continue
    $COPY_CMD "$f" "$INSTALL_DIR/docs/"
done

$MKDIR_CMD "$INSTALL_DIR/logs"

# Install icon into hicolor theme so desktop environments find it
ICON_SRC="$SCRIPT_DIR/enbmb.png"
if [ -f "$ICON_SRC" ]; then
    if [ "$NEED_SUDO" = "1" ]; then
        sudo mkdir -p /usr/share/icons/hicolor/32x32/apps
        sudo cp "$ICON_SRC" /usr/share/icons/hicolor/32x32/apps/enbmb.png
        sudo gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true
    else
        mkdir -p "$HOME/.local/share/icons/hicolor/32x32/apps"
        cp "$ICON_SRC" "$HOME/.local/share/icons/hicolor/32x32/apps/enbmb.png"
        gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi
    info "Icon installed"
fi

info "Files copied to $INSTALL_DIR"

# ── Launcher script ───────────────────────────────────────────

header "Creating launcher…"

$MKDIR_CMD "$BIN_DIR"

LAUNCHER_CONTENT="#!/bin/bash
cd \"$INSTALL_DIR\"
exec python3 main.py \"\$@\"
"

if [ "$NEED_SUDO" = "1" ]; then
    echo "$LAUNCHER_CONTENT" | sudo tee "$BIN_DIR/enbmb" > /dev/null
    sudo chmod +x "$BIN_DIR/enbmb"
else
    echo "$LAUNCHER_CONTENT" > "$BIN_DIR/enbmb"
    chmod +x "$BIN_DIR/enbmb"
fi

info "Launcher: $BIN_DIR/enbmb"

# Check ~/.local/bin is in PATH (user install only)
if [ "$NEED_SUDO" = "0" ] && [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    warn "~/.local/bin is not in your PATH."
    warn "Add this to your ~/.bashrc or ~/.bash_profile:"
    warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Desktop entry ─────────────────────────────────────────────

header "Creating desktop entry…"

$MKDIR_CMD "$DESKTOP_DIR"

DESKTOP_CONTENT="[Desktop Entry]
Name=EnB Multibox Manager
Comment=Multi-client manager for Earth and Beyond
Exec=$BIN_DIR/enbmb
Icon=enbmb
Type=Application
Categories=Game;
Terminal=false
StartupNotify=false
"

if [ "$NEED_SUDO" = "1" ]; then
    echo "$DESKTOP_CONTENT" | sudo tee "$DESKTOP_DIR/enbmb.desktop" > /dev/null
else
    echo "$DESKTOP_CONTENT" > "$DESKTOP_DIR/enbmb.desktop"
fi

info "Desktop entry: $DESKTOP_DIR/enbmb.desktop"

# Refresh desktop database so it shows up in launchers immediately
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

# Also drop an icon on the literal Desktop folder, not just the app-launcher
# menu — Windows-habit users expect one there. Delete it if you don't want it.
if [ -d "$HOME/Desktop" ]; then
    echo "$DESKTOP_CONTENT" > "$HOME/Desktop/enbmb.desktop"
    chmod +x "$HOME/Desktop/enbmb.desktop"
    # Nautilus/GNOME requires marking it trusted or it shows as a plain text
    # file with a "this might be untrustworthy" prompt on double-click.
    if command -v gio &>/dev/null; then
        gio set "$HOME/Desktop/enbmb.desktop" metadata::trusted true 2>/dev/null || true
    fi
    info "Desktop icon : $HOME/Desktop/enbmb.desktop"
fi

# ── Done ──────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}Installation complete!${RESET}"
echo ""
echo "  Run enbmb from your app launcher (search 'EnB'), the icon on your"
echo "  Desktop, or from the terminal: enbmb"
echo "  (don't want the Desktop icon? just delete it — it's not load-bearing)"
echo ""
echo "  First time? Run the Wine prefix setup:"
echo "    bash $INSTALL_DIR/setup_prefixes.sh"
echo ""
echo "  See $INSTALL_DIR/docs/INSTALL.md for full setup instructions."
echo ""
