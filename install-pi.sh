#!/bin/bash
# Claude Usage Monitor — installer per Raspberry Pi (o qualsiasi Linux con systemd).
#
# Uso, dalla cartella del repo clonata sul Pi:
#   ./install-pi.sh
# Variabili opzionali:  PORT=9000 ./install-pi.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/claude-usage-monitor"
PORT="${PORT:-8787}"
SERVICE=claude-usage

[ -f "$REPO_DIR/pi/server.py" ] || { echo "✗ Esegui lo script dalla cartella del repo (manca pi/server.py)"; exit 1; }
command -v python3 >/dev/null || { echo "✗ Serve python3 (sul Raspberry Pi OS è preinstallato)"; exit 1; }

mkdir -p "$DEST"
cp "$REPO_DIR/pi/server.py" "$REPO_DIR/pi/index.html" "$DEST/"
echo "✓ File installati in $DEST"

UNIT="[Unit]
Description=Claude Usage Monitor (More Digital Lab)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$DEST
ExecStart=$(command -v python3) $DEST/server.py
Restart=always
RestartSec=5
Environment=PORT=$PORT

[Install]
WantedBy=multi-user.target"

if command -v systemctl >/dev/null 2>&1; then
  echo "$UNIT" | sudo tee /etc/systemd/system/$SERVICE.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now $SERVICE
  sleep 1
  if systemctl is-active --quiet $SERVICE; then
    echo "✓ Servizio $SERVICE attivo (partirà anche al boot)"
  else
    echo "✗ Il servizio non è partito: guarda i log con: journalctl -u $SERVICE -e"
    exit 1
  fi
else
  echo "· systemd non trovato: avvia a mano con: python3 $DEST/server.py"
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
echo
echo "Monitor pronto. Aprilo da qualsiasi device in LAN:"
echo "  http://$(hostname).local:$PORT${IP:+   (oppure http://$IP:$PORT)}"
echo
echo "Sul computer con Claude Code, ora esegui: ./install-client.sh $(hostname).local"
