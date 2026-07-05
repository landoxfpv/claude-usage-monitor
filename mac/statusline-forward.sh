#!/bin/bash
# Claude Usage Monitor — forwarder statusline (lato computer con Claude Code)
#
# Claude Code invoca questo script come statusline, passando su stdin un JSON
# che include i dati di /usage (rate_limits). Lo script:
#   1. inoltra il JSON al Raspberry Pi (fire-and-forget, throttled)
#   2. stampa la statusline: quella dell'utente se configurata (STATUSLINE_CMD),
#      altrimenti una riga minimale con modello e percentuali di usage
#
# Config opzionale in ~/.claude/usage-monitor.env:
#   PI_URL=http://<ip-del-pi>:8787/api/usage
#   STATUSLINE_CMD='node /path/alla/tua/statusline.js'   # se ne avevi già una

[ -f "$HOME/.claude/usage-monitor.env" ] && source "$HOME/.claude/usage-monitor.env"
PI_URL="${PI_URL:-http://raspberrypi.local:8787/api/usage}"

input=$(cat)

# Throttle: la statusline può aggiornarsi ogni ~300ms; inoltra al massimo ogni 15s.
STAMP="${TMPDIR:-/tmp}/claude-usage-forward.stamp"
now=$(date +%s)
last=$(cat "$STAMP" 2>/dev/null || echo 0)
if [ $((now - last)) -ge 15 ]; then
  echo "$now" > "$STAMP"
  ( printf '%s' "$input" \
      | curl -s -m 2 -X POST -H 'Content-Type: application/json' \
             --data-binary @- "$PI_URL" >/dev/null 2>&1 & ) 2>/dev/null
fi

# Statusline: delega a quella dell'utente, o stampa la riga minimale integrata.
if [ -n "$STATUSLINE_CMD" ]; then
  printf '%s' "$input" | eval "$STATUSLINE_CMD"
else
  printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("Claude"); sys.exit(0)
parts = [(d.get("model") or {}).get("display_name") or "Claude"]
rl = d.get("rate_limits") or {}
for key, label in (("five_hour", "5h"), ("seven_day", "7g")):
    p = (rl.get(key) or {}).get("used_percentage")
    if isinstance(p, (int, float)):
        parts.append("%s %d%%" % (label, round(p)))
cwd = d.get("workspace", {}).get("current_dir") or d.get("cwd")
if cwd:
    parts.append(cwd.rstrip("/").split("/")[-1])
print(" │ ".join(parts))
'
fi
