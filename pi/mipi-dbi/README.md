# pi/mipi-dbi — driver pannello SPI ST7796S (panel-mipi-dbi)

File di supporto per pilotare un pannello **ST7796S SPI** su Raspberry Pi OS
Bookworm/Trixie tramite il driver DRM **`panel-mipi-dbi`**, così che
`/dev/fb1` esista e il renderer nativo del kiosk (`../kiosk-fb.py`) possa
disegnarci.

La guida passo-passo (cablaggio, `config.txt`, verifica, troubleshooting) è in
**[../../docs/display-st7796s.md](../../docs/display-st7796s.md)** → *Variante B*.

## File

| File | A cosa serve | Quando |
|---|---|---|
| `st7796s.txt` | sequenza di init del pannello (testo) | setup hardware, una volta |
| `gen-panel-bin.py` | converte `st7796s.txt` → `panel.bin` | setup hardware, una volta |
| `panel-enable.sh` | forza il modeset al boot (via `fbset`) | a ogni avvio |
| `panel-enable.service` | esempio di unit che lancia `panel-enable.sh` | a ogni avvio |

## Setup hardware (una volta)

```sh
python3 gen-panel-bin.py st7796s.txt panel.bin
sudo cp panel.bin /lib/firmware/panel.bin
# + righe dtoverlay in /boot/firmware/config.txt (vedi la guida)
sudo reboot
```

## Accensione al boot

Il pannello si accende solo dopo un **modeset**: senza, `/dev/fb1` esiste ma lo
schermo resta bianco. `install-kiosk.sh` **installa da solo** `panel-enable.sh`
e il relativo servizio quando rileva un pannello DRM. Per farlo a mano vedi la
guida o l'esempio `panel-enable.service`.
