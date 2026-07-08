#!/bin/sh
# panel-enable.sh — accende la pipeline di un pannello SPI DRM (panel-mipi-dbi).
#
# Con panel-mipi-dbi il pannello viene inizializzato e acceso SOLO dopo un
# "modeset". In un sistema headless il modeset non avviene da solo: senza,
# /dev/fb1 esiste ma le scritture raw (kiosk-fb.py) non arrivano al pannello
# e lo schermo resta bianco. Questo script forza un modeset con `fbset`.
#
# Uso:  panel-enable.sh [/dev/fbN]
#   - con argomento: usa quel framebuffer
#   - senza:         rileva il primo fb il cui name contiene "panel"/"mipi"
#
# Pensato per girare da panel-enable.service (oneshot, al boot, prima del kiosk).
set -eu

FB="${1:-}"

# Attende che il framebuffer del pannello compaia (probe SPI tardivo al boot).
i=0
while [ "$i" -lt 30 ]; do
    if [ -n "$FB" ] && [ -e "$FB" ]; then
        break
    fi
    if [ -z "$FB" ]; then
        for f in /sys/class/graphics/fb*/name; do
            [ -e "$f" ] || continue
            case "$(cat "$f")" in
                *panel*|*mipi*) FB="/dev/$(basename "$(dirname "$f")")"; break ;;
            esac
        done
        [ -n "$FB" ] && [ -e "$FB" ] && break
    fi
    i=$((i + 1))
    sleep 1
done

if [ -z "$FB" ] || [ ! -e "$FB" ]; then
    echo "panel-enable: nessun framebuffer pannello trovato" >&2
    exit 0
fi

base="/sys/class/graphics/$(basename "$FB")"
# Geometria letta da sysfs: niente valori cablati, vale per qualsiasi pannello.
geom=$(tr ',' ' ' < "$base/virtual_size")
# shellcheck disable=SC2086
set -- $geom
W="$1"; H="$2"
BPP=$(cat "$base/bits_per_pixel")

echo "panel-enable: modeset su $FB (${W}x${H} ${BPP}bpp)"
exec fbset -fb "$FB" -g "$W" "$H" "$W" "$H" "$BPP"
