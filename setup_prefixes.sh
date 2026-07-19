#!/bin/bash
# ============================================================
#  EnB Multibox Manager — setup_prefixes.sh
#
#  Sets up Wine prefixes for each slot (1-7).
#  Slots 1-6 are managed by enbmb. Slot 7 is the independent client prefix.
#  Each prefix gets its own registry with the correct
#  resolution and Wine input fixes.
#
#  Game files are symlinked from the base prefix so no
#  extra disk space is used.
#
#  Run this ONCE after initial EnB installation.
#  Safe to re-run — skips existing prefixes unless --force.
#
#  Usage:
#    bash setup_prefixes.sh              # create prefixes (slots 1-7)
#    bash setup_prefixes.sh --force      # recreate all
#    bash setup_prefixes.sh --force 3    # recreate slot 3 only
#    bash setup_prefixes.sh --force 7    # recreate independent client prefix
# ============================================================

set -e

FORCE=0
FORCE_SLOT=""
if [ "${1:-}" = "--force" ]; then
    FORCE=1
    FORCE_SLOT="${2:-}"
fi

# ── Locate enbmb install dir (where this script lives) ───────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WINRESIZE="$SCRIPT_DIR/winresize.exe"

if [ ! -f "$WINRESIZE" ]; then
    echo "[ERROR] winresize.exe not found in $SCRIPT_DIR"
    echo "        Make sure you're running this from the enbmb directory."
    exit 1
fi

# ── Auto-detect base Wine prefix ─────────────────────────────

GAME_PATH="Program Files/EA GAMES/Earth & Beyond"

detect_base_prefix() {
    local candidates=(
        "$HOME/.wine-enb"
        "$HOME/.wine"
        "$HOME/.local/share/wineprefixes/enb"
    )
    for candidate in "${candidates[@]}"; do
        if [ -d "$candidate/drive_c/$GAME_PATH" ]; then
            echo "$candidate"
            return
        fi
    done
    echo ""
}

BASE_PREFIX="${ENB_PREFIX:-$(detect_base_prefix)}"

if [ -z "$BASE_PREFIX" ]; then
    echo ""
    echo "EnB installation not found in common locations."
    echo "Common locations checked:"
    echo "  ~/.wine-enb"
    echo "  ~/.wine"
    echo "  ~/.local/share/wineprefixes/enb"
    echo ""
    read -rp "Enter the path to your Wine prefix where EnB is installed: " BASE_PREFIX
    BASE_PREFIX="${BASE_PREFIX/#\~/$HOME}"
fi

if [ ! -d "$BASE_PREFIX/drive_c/$GAME_PATH" ]; then
    echo "[ERROR] Earth & Beyond not found in: $BASE_PREFIX/drive_c/$GAME_PATH"
    echo "        Install the game first via the Net-7 launcher, then re-run this script."
    exit 1
fi

NET7_PATH="Program Files (x86)/Net-7"
EBCONFIG_PATH="$GAME_PATH/EBCONFIG"
NET7_LAUNCHER="$BASE_PREFIX/drive_c/$NET7_PATH/bin/LaunchNet7.exe_wine_launcher.sh"
NET7_PROXY="$BASE_PREFIX/drive_c/$NET7_PATH/bin/net7proxy.exe_wine_launcher.sh"

if [ ! -f "$NET7_LAUNCHER" ]; then
    echo "[ERROR] Net7 launcher not found: $NET7_LAUNCHER"
    echo "        Run the Net-7 launcher once before running this script."
    exit 1
fi

# ── Launcher output dir ───────────────────────────────────────

LAUNCHER_DIR="$HOME/.local/bin"
mkdir -p "$LAUNCHER_DIR"

# ── Auto-detect monitor layout via xrandr ────────────────────
#
# Finds the primary monitor and the first secondary monitor.
# Slot 1 goes on the primary; slots 2-6 fill the secondary in a 3x2 grid.
#
# If monitor detection fails or you have an unusual layout, you can
# override by setting these environment variables before running:
#   PRIMARY_W, PRIMARY_H, PRIMARY_X, PRIMARY_Y
#   SECONDARY_W, SECONDARY_H, SECONDARY_X, SECONDARY_Y

detect_monitors() {
    local primary_line secondary_line
    primary_line=$(xrandr --query 2>/dev/null | grep " primary " | head -1)
    secondary_line=$(xrandr --query 2>/dev/null | grep " connected " | grep -v " primary " | head -1)

    if [ -z "$primary_line" ]; then
        # No primary flag set — fall back to the first connected monitor
        primary_line=$(xrandr --query 2>/dev/null | grep " connected " | head -1)
        secondary_line=$(xrandr --query 2>/dev/null | grep " connected " | sed -n '2p')
    fi

    # Parse "1920x1080+0+0" geometry from xrandr output
    parse_geometry() {
        echo "$1" | grep -oP '\d+x\d+\+\d+\+\d+' | head -1
    }

    PRIMARY_GEO=$(parse_geometry "$primary_line")
    SECONDARY_GEO=$(parse_geometry "$secondary_line")

    if [ -z "$PRIMARY_GEO" ]; then
        echo "[WARN] Could not detect monitor geometry — using defaults (1920x1080 dual)"
        PRIMARY_W=1920; PRIMARY_H=1080; PRIMARY_X=0;    PRIMARY_Y=0
        SECONDARY_W=1920; SECONDARY_H=1080; SECONDARY_X=1920; SECONDARY_Y=0
        return
    fi

    PRIMARY_W=$(echo "$PRIMARY_GEO" | cut -dx -f1)
    PRIMARY_H=$(echo "$PRIMARY_GEO" | cut -dx -f2 | cut -d+ -f1)
    PRIMARY_X=$(echo "$PRIMARY_GEO" | cut -d+ -f2)
    PRIMARY_Y=$(echo "$PRIMARY_GEO" | cut -d+ -f3)

    if [ -n "$SECONDARY_GEO" ]; then
        SECONDARY_W=$(echo "$SECONDARY_GEO" | cut -dx -f1)
        SECONDARY_H=$(echo "$SECONDARY_GEO" | cut -dx -f2 | cut -d+ -f1)
        SECONDARY_X=$(echo "$SECONDARY_GEO" | cut -d+ -f2)
        SECONDARY_Y=$(echo "$SECONDARY_GEO" | cut -d+ -f3)
    else
        # Single monitor — fit all 6 slots on it
        SECONDARY_W=$PRIMARY_W
        SECONDARY_H=$PRIMARY_H
        SECONDARY_X=$PRIMARY_X
        SECONDARY_Y=$PRIMARY_Y
    fi
}

# Allow env var overrides; otherwise auto-detect
if [ -z "${PRIMARY_W:-}" ]; then
    detect_monitors
fi

# Secondary slot size: 1/3 width, 1/2 height of secondary monitor
SLOT_W=$(( SECONDARY_W / 3 ))
SLOT_H=$(( SECONDARY_H / 2 ))

# Grid positions: 3 columns × 2 rows on secondary monitor
# Layout (column-fill, matches layout_engine.py fill_vertical=True):
#   [2][4][6]
#   [3][5][ ]
declare -A SLOT_X=(
    [1]=$PRIMARY_X
    [2]=$(( SECONDARY_X ))
    [3]=$(( SECONDARY_X ))
    [4]=$(( SECONDARY_X + SLOT_W ))
    [5]=$(( SECONDARY_X + SLOT_W ))
    [6]=$(( SECONDARY_X + SLOT_W * 2 ))
)
declare -A SLOT_Y=(
    [1]=$PRIMARY_Y
    [2]=$SECONDARY_Y
    [3]=$(( SECONDARY_Y + SLOT_H ))
    [4]=$SECONDARY_Y
    [5]=$(( SECONDARY_Y + SLOT_H ))
    [6]=$SECONDARY_Y
)

# ── Helpers ───────────────────────────────────────────────────

log()  { echo "[setup] $*"; }
err()  { echo "[ERROR] $*" >&2; exit 1; }
info() { echo "[setup]   $*"; }

to_hex() { printf "0x%x" "$1"; }

set_reg_dword() {
    local prefix="$1" key="$2" name="$3" val="$4"
    WINEPREFIX="$prefix" wine reg add "$key" /v "$name" /t REG_DWORD /d "$val" /f \
        >/dev/null 2>&1 || true
}

set_reg_sz() {
    local prefix="$1" key="$2" name="$3" val="$4"
    WINEPREFIX="$prefix" wine reg add "$key" /v "$name" /t REG_SZ /d "$val" /f \
        >/dev/null 2>&1 || true
}

# ── Function: configure one prefix ───────────────────────────

configure_prefix() {
    local slot="$1"
    local prefix

    if [ "$slot" -eq 1 ]; then
        prefix="$BASE_PREFIX"
    else
        prefix="$HOME/.wine-enb-$slot"
    fi

    local w h x y
    if [ "$slot" -eq 1 ] || [ "$slot" -eq 7 ]; then
        w=$PRIMARY_W; h=$PRIMARY_H
    else
        w=$SLOT_W; h=$SLOT_H
    fi
    x=${SLOT_X[$slot]:-}
    y=${SLOT_Y[$slot]:-}

    log "=== Slot $slot ($prefix) ==="
    if [ "$slot" -eq 7 ]; then
        info "Resolution: ${w}x${h}  (independent client — normal window, not auto-positioned)"
    else
        info "Resolution: ${w}x${h}  Position: ${x},${y}"
    fi

    # ── Create prefix structure if needed ──────────────────

    if [ "$slot" -ne 1 ]; then
        if [ -d "$prefix" ] && [ "$FORCE" -eq 0 ]; then
            info "Already exists — skipping (use --force to recreate)"
            create_launcher "$slot" "$prefix" "$w" "$h" "$x" "$y"
            return
        fi

        if [ -d "$prefix" ]; then
            info "Removing existing prefix..."
            rm -f "$prefix/system.reg" "$prefix/user.reg" \
                  "$prefix/userdef.reg" "$prefix/.update-timestamp" 2>/dev/null || true
            rm -rf "$prefix/drive_c/users" "$prefix/drive_c/ProgramData" \
                   "$prefix/drive_c/windows" 2>/dev/null || true
            rm -rf "$prefix/drive_c/Program Files" 2>/dev/null || true
            rm -f "$prefix/drive_c/Program Files (x86)" \
                  "$prefix/dosdevices" 2>/dev/null || true
        fi

        info "Creating prefix structure..."
        mkdir -p "$prefix/drive_c"
        mkdir -p "$prefix/drive_c/users/$USER/AppData/Local"
        mkdir -p "$prefix/drive_c/users/$USER/AppData/Roaming"
        mkdir -p "$prefix/drive_c/users/$USER/Documents"
        mkdir -p "$prefix/drive_c/ProgramData"
        mkdir -p "$prefix/drive_c/windows/system32"

        # Symlink game data — no disk duplication.
        # Program Files (x86) — Net-7 proxy, safe to share
        ln -sfn "$BASE_PREFIX/drive_c/Program Files (x86)" \
                "$prefix/drive_c/Program Files (x86)"
        ln -sfn "$BASE_PREFIX/dosdevices" \
                "$prefix/dosdevices"
        ln -sfn "$BASE_PREFIX/.update-timestamp" \
                "$prefix/.update-timestamp"

        # Deep symlinks into Program Files, isolating EBCONFIG per prefix.
        # Each slot needs its own EBCONFIG/results.ini so the game reads
        # the correct resolution at startup.
        local base_pf="$BASE_PREFIX/drive_c/Program Files"
        local pref_pf="$prefix/drive_c/Program Files"
        mkdir -p "$pref_pf"

        while IFS= read -r name; do
            [ "$name" = "EA GAMES" ] && continue
            ln -sfn "$base_pf/$name" "$pref_pf/$name" 2>/dev/null || true
        done < <(ls -1A "$base_pf" 2>/dev/null)

        mkdir -p "$pref_pf/EA GAMES"
        while IFS= read -r name; do
            [ "$name" = "Earth & Beyond" ] && continue
            ln -sfn "$base_pf/EA GAMES/$name" "$pref_pf/EA GAMES/$name" 2>/dev/null || true
        done < <(ls -1A "$base_pf/EA GAMES" 2>/dev/null)

        local base_enb="$base_pf/EA GAMES/Earth & Beyond"
        local pref_enb="$pref_pf/EA GAMES/Earth & Beyond"
        mkdir -p "$pref_enb"
        while IFS= read -r name; do
            [ "$name" = "EBCONFIG" ] && continue
            [ "$name" = "release" ] && continue
            ln -sfn "$base_enb/$name" "$pref_enb/$name" 2>/dev/null || true
        done < <(ls -1A "$base_enb" 2>/dev/null)

        info "Creating per-prefix EBCONFIG..."
        mkdir -p "$pref_enb/EBCONFIG"
        if [ -d "$base_enb/EBCONFIG" ]; then
            while IFS= read -r name; do
                cp -n "$base_enb/EBCONFIG/$name" "$pref_enb/EBCONFIG/$name" 2>/dev/null || true
            done < <(ls -1A "$base_enb/EBCONFIG" 2>/dev/null)
        fi

        # Deep-symlink "release" contents except chat.log — each prefix gets its
        # own real chat.log file. A shared symlinked log caused structural byte-
        # level data loss under concurrent writes from 6 Wine processes (see
        # docs/LESSONS.md "chat.log sharing across Wine prefixes..."). If an old
        # symlinked setup is being re-run, replace the symlink with a real file
        # (one-time migration); leave an existing real file alone.
        info "Isolating per-prefix chat.log..."
        local base_rel="$base_enb/release"
        local pref_rel="$pref_enb/release"
        mkdir -p "$pref_rel"
        if [ -d "$base_rel" ]; then
            while IFS= read -r name; do
                [ "$name" = "chat.log" ] && continue
                ln -sfn "$base_rel/$name" "$pref_rel/$name" 2>/dev/null || true
            done < <(ls -1A "$base_rel" 2>/dev/null)
        fi
        if [ -L "$pref_rel/chat.log" ] || [ ! -e "$pref_rel/chat.log" ]; then
            rm -f "$pref_rel/chat.log"
            : > "$pref_rel/chat.log"
        fi

        info "Copying registry..."
        cp "$BASE_PREFIX/system.reg"  "$prefix/system.reg"
        cp "$BASE_PREFIX/user.reg"    "$prefix/user.reg"
        cp "$BASE_PREFIX/userdef.reg" "$prefix/userdef.reg"
    fi

    # ── Set resolution in registry ──────────────────────────
    # All slots render at the primary monitor resolution internally.
    # Secondary slots get their frame shrunk by winresize.exe after launch;
    # cycling back to the main monitor expands the frame to full size.

    info "Setting render resolution in registry: ${PRIMARY_W}x${PRIMARY_H}..."
    local render_key="HKLM\SOFTWARE\WOW6432Node\Westwood Studios\Earth and Beyond\Render"

    set_reg_dword "$prefix" "$render_key" "RenderDeviceWidth"    "$(to_hex $PRIMARY_W)"
    set_reg_dword "$prefix" "$render_key" "RenderDeviceHeight"   "$(to_hex $PRIMARY_H)"
    set_reg_dword "$prefix" "$render_key" "RenderDeviceWindowed" "0x1"
    set_reg_dword "$prefix" "$render_key" "RenderDeviceDepth"    "0x20"

    # ── Apply Wine input fixes ──────────────────────────────

    info "Applying Wine input fixes..."
    set_reg_sz "$prefix" \
        "HKCU\Software\Wine\DirectInput" \
        "MouseWarpOverride" "force"
    set_reg_sz "$prefix" \
        "HKCU\Software\Wine\X11 Driver" \
        "UseTakeFocus" "N"

    # ── Update results.ini ──────────────────────────────────

    local results
    if [ "$slot" -eq 1 ]; then
        results="$BASE_PREFIX/drive_c/$EBCONFIG_PATH/results.ini"
    else
        results="$prefix/drive_c/$EBCONFIG_PATH/results.ini"
    fi
    if [ -f "$results" ]; then
        sed -i "s/^Width=.*/Width=$PRIMARY_W/"   "$results"
        sed -i "s/^Height=.*/Height=$PRIMARY_H/" "$results"
        sed -i "s/^Windowed=.*/Windowed=yes/" "$results"
        info "Updated results.ini: ${PRIMARY_W}x${PRIMARY_H} (per-prefix)"
    fi

    create_launcher "$slot" "$prefix" "$w" "$h" "$x" "$y"
    info "Done ✓"
}

# ── Function: create per-slot launcher script ─────────────────

create_launcher() {
    local slot="$1" prefix="$2" w="$3" h="$4" x="$5" y="$6"
    local launcher_name="enb-slot$slot"
    [ "$slot" -eq 7 ] && launcher_name="enb-extra"
    local launcher="$LAUNCHER_DIR/$launcher_name"

    # Wine's C: resolves to the BASE prefix's drive_c for every slot (dosdevices
    # is symlinked whole — see docs/LESSONS.md), so /CLIENT: must use the
    # always-correct Z:->/ host-root mapping instead of a C:-rooted DOS path.
    local prefix_win
    prefix_win=$(printf '%s' "$prefix" | sed 's#^/##; s#/#\\\\#g')
    local client_path="Z:\\\\${prefix_win}\\\\drive_c\\\\Program Files\\\\EA GAMES\\\\Earth & Beyond\\\\release\\\\client.exe"

    # The independent client (slot 7) is intentionally NOT positioned/resized —
    # it's meant to be a normal window the user drags wherever they want, not
    # a managed/borderless slot. Skip the winresize.exe step entirely for it.
    local resize_cmd="WINEPREFIX=\"\$PREFIX\" wine \"\$WINRESIZE\" \"Earth & Beyond\" \$GAME_X \$GAME_Y \$GAME_W \$GAME_H 2>/dev/null || true"
    [ "$slot" -eq 7 ] && resize_cmd="true  # independent client: no forced position/size"

    local header_comment="# EnB Slot $slot launcher — ${w}x${h} at position ${x},${y}"
    [ "$slot" -eq 7 ] && header_comment="# EnB independent client launcher — ${w}x${h}, normal window, not auto-positioned"

    cat > "$launcher" << LAUNCHEOF
#!/bin/bash
$header_comment
# Auto-generated by setup_prefixes.sh — re-run to regenerate

PREFIX="$prefix"
GAME_W=$w
GAME_H=$h
GAME_X=$x
GAME_Y=$y
WINRESIZE="$WINRESIZE"

# Get server IP via DNS (fallback to known IP if DNS unavailable)
SERVER_IP=\$(dig +short sunrise.net-7.org 2>/dev/null | tail -1)
[ -z "\$SERVER_IP" ] && SERVER_IP=\$(getent hosts sunrise.net-7.org 2>/dev/null | awk '{print \$1}' | tail -1)
[ -z "\$SERVER_IP" ] && SERVER_IP="216.219.87.147"

EXISTING_IDS=\$(xdotool search --name "Earth" 2>/dev/null || true)

WINEFSYNC=1 WINEDEBUG=-all WINEPREFIX="\$PREFIX" /usr/bin/wine start \\
    /d "C:\\\\Program Files (x86)\\\\Net-7\\\\bin" \\
    "net7proxy.exe" \\
    /LADDRESS:0 \\
    /ADDRESS:"\$SERVER_IP" \\
    /CLIENT:"${client_path}" \\
    /DML /EXREORDER /POPT &
LAUNCH_PID=\$!

(
    NEW_WID=""
    for attempt in \$(seq 1 30); do
        sleep 1
        ALL_IDS=\$(xdotool search --name "Earth" 2>/dev/null || true)
        for id in \$ALL_IDS; do
            if ! echo "\$EXISTING_IDS" | grep -qw "\$id"; then
                NEW_WID="\$id"
                break 2
            fi
        done
    done

    if [ -n "\$NEW_WID" ]; then
        sleep 0.1
        xdotool key --window "\$NEW_WID" space 2>/dev/null || true
        sleep 7
        $resize_cmd
    fi
) &

wait \$LAUNCH_PID
LAUNCHEOF

    chmod +x "$launcher"
    info "Created launcher: $launcher"
}

# ── Summary header ────────────────────────────────────────────

log "EnB Multibox Manager — Wine prefix setup"
log ""
log "Base prefix : $BASE_PREFIX"
log "enbmb dir   : $SCRIPT_DIR"
log "Launchers   : $LAUNCHER_DIR"
log ""
log "Primary monitor  : ${PRIMARY_W}x${PRIMARY_H} at +${PRIMARY_X}+${PRIMARY_Y}"
log "Secondary monitor: ${SECONDARY_W}x${SECONDARY_H} at +${SECONDARY_X}+${SECONDARY_Y}"
log "Secondary slot size: ${SLOT_W}x${SLOT_H}"
log ""

# ── Run ───────────────────────────────────────────────────────

if [ -n "$FORCE_SLOT" ]; then
    configure_prefix "$FORCE_SLOT"
else
    for slot in 1 2 3 4 5 6 7; do
        configure_prefix "$slot"
        log ""
    done
fi

# ── Update launcher ───────────────────────────────────────────

UPDATE_LAUNCHER="$LAUNCHER_DIR/enb-update"
cat > "$UPDATE_LAUNCHER" << UPDATEEOF
#!/bin/bash
# EnB Update launcher — run before playing to check for game updates
WINEPREFIX="$BASE_PREFIX" bash "$NET7_LAUNCHER"
UPDATEEOF
chmod +x "$UPDATE_LAUNCHER"
log "Created update launcher: $UPDATE_LAUNCHER"
log ""

# ── Done ──────────────────────────────────────────────────────

log "============================================"
log "Setup complete!"
log ""
log "Per-slot launchers created in $LAUNCHER_DIR:"
for slot in 1 2 3 4 5 6; do
    w=$SLOT_W; h=$SLOT_H
    [ "$slot" -eq 1 ] && w=$PRIMARY_W && h=$PRIMARY_H
    x=${SLOT_X[$slot]}; y=${SLOT_Y[$slot]}
    log "  enb-slot$slot  ${w}x${h} at ${x},${y}"
done
log "  enb-extra   ${PRIMARY_W}x${PRIMARY_H}  (independent client — normal window, movable)"
log ""
log "Test with:  enb-slot1"
log ""
log "In enbmb settings, set each slot's launch command"
log "to enb-slot1 through enb-slot6."
log "============================================"
