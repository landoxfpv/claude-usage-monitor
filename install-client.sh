#!/bin/bash
# Claude Usage Monitor — installer per il computer dove gira Claude Code (macOS/Linux).
#
# Configura la statusline di Claude Code per inoltrare i dati di /usage al Pi.
# Se avevi già una statusline personalizzata, viene preservata automaticamente:
# il forwarder continuerà a delegarle la stampa.
#
# Uso, dalla cartella del repo:
#   ./install-client.sh                          # Pi su raspberrypi.local
#   ./install-client.sh 192.168.1.42             # IP del Pi
#   ./install-client.sh http://pi:9000/api/usage # URL completo
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
DEST_DIR="$CLAUDE_DIR/usage-monitor"
ENV_FILE="$CLAUDE_DIR/usage-monitor.env"
SETTINGS="$CLAUDE_DIR/settings.json"

command -v python3 >/dev/null || { echo "✗ Serve python3"; exit 1; }
[ -f "$REPO_DIR/mac/statusline-forward.sh" ] || { echo "✗ Esegui lo script dalla cartella del repo"; exit 1; }

ARG="${1:-}"
if [ -z "$ARG" ]; then PI_URL="http://raspberrypi.local:8787/api/usage"
elif [[ "$ARG" == http* ]]; then PI_URL="$ARG"
else PI_URL="http://$ARG:8787/api/usage"; fi

mkdir -p "$DEST_DIR"
cp "$REPO_DIR/mac/statusline-forward.sh" "$DEST_DIR/"
chmod +x "$DEST_DIR/statusline-forward.sh"
FORWARDER="$DEST_DIR/statusline-forward.sh"

# Aggiorna settings.json: installa il forwarder come statusline e restituisce
# l'eventuale comando statusline preesistente (per preservarlo).
OLD_CMD=$(FORWARDER="$FORWARDER" SETTINGS="$SETTINGS" python3 <<'PY'
import json, os
settings_path = os.environ["SETTINGS"]
fw = os.environ["FORWARDER"]
try:
    with open(settings_path) as f:
        s = json.load(f)
except (OSError, ValueError):
    s = {}
old = ""
sl = s.get("statusLine")
if isinstance(sl, dict):
    cmd = sl.get("command", "")
    if "statusline-forward.sh" not in cmd:  # non ricatturare noi stessi al secondo run
        old = cmd
s["statusLine"] = {"type": "command", "command": 'bash "%s"' % fw}
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, "w") as f:
    json.dump(s, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(old)
PY
)

# usage-monitor.env: PI_URL sempre aggiornato; STATUSLINE_CMD aggiunta solo se
# è stata catturata una statusline preesistente e non è già configurata.
touch "$ENV_FILE"
if grep -q '^PI_URL=' "$ENV_FILE"; then
  sed -i.bak "s|^PI_URL=.*|PI_URL=$PI_URL|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
else
  echo "PI_URL=$PI_URL" >> "$ENV_FILE"
fi
if [ -n "$OLD_CMD" ] && ! grep -q '^STATUSLINE_CMD=' "$ENV_FILE"; then
  # nota: se il comando contiene apici singoli va sistemato a mano in $ENV_FILE
  printf "STATUSLINE_CMD='%s'\n" "$OLD_CMD" >> "$ENV_FILE"
  echo "✓ Statusline preesistente preservata (STATUSLINE_CMD in $ENV_FILE)"
fi

echo "✓ Forwarder installato: $FORWARDER"
echo "✓ Statusline configurata in $SETTINGS"
echo "✓ Destinazione dati: $PI_URL"
if curl -s -m 3 "${PI_URL%/api/usage}/health" 2>/dev/null | grep -q '"ok"'; then
  echo "✓ Il monitor risponde"
else
  echo "· Il monitor non risponde ancora (ok se il Pi non è configurato: esegui ./install-pi.sh sul Pi)"
fi
echo
echo "Fatto: le sessioni Claude Code aperte da ora inizieranno a inviare i dati."
