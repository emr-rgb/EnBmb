#!/usr/bin/env bash
# check_zone_test.sh — short, filtered summary of zone-test activity from
# monitor.log + chat.log, instead of dumping the full verbose logs into
# an editor/agent context (monitor.log lines carry a full per-slot process
# list that's mostly noise for "did the freeze fire" questions).
#
# Usage: check_zone_test.sh HH:MM [YYYY-MM-DD]
#   HH:MM   - approx time the zone happened (24h, e.g. 08:58)
#   DATE    - defaults to today (YYYY-MM-DD)

set -euo pipefail

START="${1:?Usage: $0 HH:MM [YYYY-MM-DD]}"
DATE="${2:-$(date +%Y-%m-%d)}"
HOUR="${START%%:*}"
HOUR_NOPAD="${HOUR#0}"

MONITOR_LOG="${ENBMB_DIR:-$(dirname "$(realpath "$0")")/../}/logs/monitor.log"
CHAT_LOG="${WINE_ENB_PREFIX:-$HOME/.wine-enb}/drive_c/Program Files/EA GAMES/Earth & Beyond/release/chat.log"

echo "=== Zone test check — $DATE from $START onward ==="
echo
echo "--- chat.log: most recent arrivals / wormholes (chat.log has no dates," \
     "so we just take the tail — your test will be the newest entries) ---"
grep -E "We have entered|Wormhole ability enabled" "$CHAT_LOG" | tail -n 15

echo
echo "--- monitor.log transitions from $START on $DATE (process lists stripped) ---"
awk -F'[][]' -v d="$DATE" -v s="$START" '
    $2 ~ ("^" d " ") {
        ts = substr($2, length(d) + 2, 5)
        if (ts >= s) print
    }
' "$MONITOR_LOG" \
    | sed -E 's/ procs=\[[^]]*\]//' \
    | grep -E "ZONE FREEZE|ZONING|→ |START" \
    || echo "(no matching transitions found)"
