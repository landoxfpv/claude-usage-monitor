#!/bin/bash
# Claude Usage Monitor — kiosk opzionale: mostra la dashboard sul display del Pi.
#
# Uso, dalla cartella del repo sul Pi, DOPO ./install-pi.sh:
#   ./install-kiosk.sh
# Rilanciarlo è il modo per cambiare motore o framebuffer.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/claude-usage-monitor"
PORT="${PORT:-8787}"
SERVICE=claude-kiosk

command -v systemctl >/dev/null || { echo "✗ Serve systemd (Raspberry Pi OS)"; exit 1; }
curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1 \
  || { echo "✗ Il server non risponde su localhost:$PORT — esegui prima ./install-pi.sh"; exit 1; }

MODEL=$(tr -d '\0' </proc/device-tree/model 2>/dev/null || echo "modello sconosciuto")
ARCH=$(uname -m)
shopt -s nullglob
FBS=(/dev/fb*)
shopt -u nullglob

DEFAULT_ENGINE=chromium
[ "$ARCH" = "armv6l" ] && DEFAULT_ENGINE=native   # Pi Zero W / Pi 1: niente browser
DEFAULT_FB=/dev/fb0
[ -e /dev/fb1 ] && DEFAULT_FB=/dev/fb1            # fb1 = tipico pannello SPI

echo "Rilevato: $MODEL ($ARCH)"
echo "Framebuffer presenti: ${FBS[*]:-nessuno}"
echo
echo "Motori disponibili:"
echo "  chromium  pagina web a schermo intero (Pi 3/4/5, Zero 2 W)"
echo "  native    renderer leggero senza browser (Pi Zero W, pannelli SPI)"
read -rp "Motore [$DEFAULT_ENGINE]: " ENGINE
ENGINE=${ENGINE:-$DEFAULT_ENGINE}

case "$ENGINE" in
  native)
    if [ ${#FBS[@]} -eq 0 ]; then
      echo "✗ Nessun framebuffer: se hai un display SPI va prima configurato il driver."
      echo "  Guida (esempio ST7796S): docs/display-st7796s.md"
      exit 1
    fi
    read -rp "Framebuffer [$DEFAULT_FB]: " FBDEV
    FBDEV=${FBDEV:-$DEFAULT_FB}
    [ -e "$FBDEV" ] || { echo "✗ $FBDEV non esiste"; exit 1; }
    echo "· Installo python3-pil…"
    sudo apt-get install -y python3-pil >/dev/null
    mkdir -p "$DEST/fonts"
    cp "$REPO_DIR/pi/kiosk-fb.py" "$DEST/"
    cp "$REPO_DIR"/pi/fonts/* "$DEST/fonts/"
    UNIT="[Unit]
Description=Claude Usage Monitor Kiosk (renderer nativo)
After=claude-usage.service
Wants=claude-usage.service

[Service]
User=$USER
SupplementaryGroups=video
ExecStart=$(command -v python3) $DEST/kiosk-fb.py --fb $FBDEV --url http://localhost:$PORT/api/usage
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target"
    ;;
  chromium)
    echo "· Installo cage e chromium…"
    sudo apt-get install -y cage >/dev/null
    CHROMIUM=$(command -v chromium-browser || command -v chromium || true)
    if [ -z "$CHROMIUM" ]; then
      sudo apt-get install -y chromium-browser >/dev/null 2>&1 \
        || sudo apt-get install -y chromium >/dev/null
      CHROMIUM=$(command -v chromium-browser || command -v chromium)
    fi
    UNIT="[Unit]
Description=Claude Usage Monitor Kiosk (Chromium)
After=claude-usage.service systemd-user-sessions.service getty@tty1.service
Wants=claude-usage.service
Conflicts=getty@tty1.service

[Service]
User=$USER
PAMName=login
TTYPath=/dev/tty1
StandardInput=tty-fail
UtmpIdentifier=tty1
UtmpMode=user
ExecStart=$(command -v cage) -- $CHROMIUM --kiosk --noerrdialogs --disable-infobars --ozone-platform=wayland http://localhost:$PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target"
    ;;
  *)
    echo "✗ Motore sconosciuto: $ENGINE (usa: chromium oppure native)"; exit 1 ;;
esac

echo "$UNIT" | sudo tee /etc/systemd/system/$SERVICE.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now $SERVICE
sleep 2
if systemctl is-active --quiet $SERVICE; then
  echo "✓ Kiosk attivo sul display del Pi (motore: $ENGINE, partirà anche al boot)"
  echo "  Per rimuoverlo: sudo systemctl disable --now $SERVICE"
else
  echo "✗ Il kiosk non è partito: guarda i log con: journalctl -u $SERVICE -e"
  exit 1
fi
