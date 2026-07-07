# Display SPI ST7796S sul Pi (guida driver)

I pannelli TFT SPI (ST7796S 480×320, sia gli shield 3.5" sia i moduli 4.0"
cablati a mano) **non sono monitor HDMI**: la GPU non li vede. Serve un driver
del kernel che crei un **framebuffer** (`/dev/fb1`) su cui il renderer del
kiosk possa scrivere i pixel.

> Il kiosk (`./install-kiosk.sh`, motore *native*) parte **dopo** che questa
> guida ha prodotto un `/dev/fb1` funzionante. Il renderer nativo
> (`pi/kiosk-fb.py`) scrive raw in **RGB565** direttamente sul framebuffer.

---

## 0. Concetti e best practice (leggere una volta)

Prima di seguire una ricetta, conviene capire il modello — è ciò che rende il
debug rapido invece che a tentativi.

- **Framebuffer `/dev/fbN`.** Un device su cui scrivere byte = pixel a schermo.
  Il pannello SPI diventa tipicamente `/dev/fb1` (`fb0` resta l'eventuale
  uscita HDMI/emulata). Il formato quasi sempre è **RGB565, 16 bit/pixel**,
  little-endian; verifica con
  `cat /sys/class/graphics/fb1/{virtual_size,bits_per_pixel,stride}`.

- **Due famiglie di driver.** Scegliere quella giusta è il 90% del lavoro:

  | | `fbtft` (legacy) | `panel-mipi-dbi` (DRM, moderno) |
  |---|---|---|
  | Tipo | framebuffer classico | DRM + emulazione fbdev |
  | Scrittura raw su `/dev/fb1` | va **subito** al pannello | va al pannello **solo dopo un "modeset"** |
  | Init del pannello | nel driver/overlay | in un file firmware `panel.bin` |
  | Stato su Bookworm/Trixie | overlay spesso assenti per l'ST7796S | **disponibile e consigliato** |

- **La trappola del modeset (solo `panel-mipi-dbi`).** Il pannello viene
  inizializzato e acceso **solo quando la pipeline DRM fa un modeset**. Senza,
  `/dev/fb1` esiste ma è "scollegato": scrivi pixel e non succede nulla →
  **schermo bianco**. In un sistema headless (nessun compositore/console sul
  pannello) il modeset non avviene da solo: va forzato una volta con `fbset`
  (vedi il servizio `panel-enable` più sotto).

- **Retroilluminazione (LED).** È separata dai dati. Se lo schermo è nero ma
  "vivo", spesso è solo il backlight spento (`bl_power` a `4`). Con
  `panel-mipi-dbi` la si dichiara con `backlight-gpio=<pin>` e la accende il
  driver al modeset.

- **Ordine dei colori e inversione.** `MADCTL` (comando `0x36`) governa
  orientamento e ordine **RGB/BGR**; `INVON`/`INVOFF` (`0x21`/`0x20`)
  l'inversione. Sintomi:
  - colori tipo **negativo fotografico** (rosso↔ciano, verde↔magenta) →
    inversione sbagliata: cambia `0x21`↔`0x20`.
  - **rosso e blu scambiati** (verde ok) → bit BGR in `MADCTL`.
  - **ruotato/specchiato** → altri bit di `MADCTL`.

- **Velocità SPI.** Con jumper volanti tieniti conservativo (16–32 MHz). Troppo
  alta → dati corrotti (rumore/garbage). Gli overlay inviano l'**init** a
  ~10 MHz e i **pixel** alla velocità impostata.

---

## Variante A — shield 3.5" ST7796S (fbtft / LCD-show)

Per gli shield che si innestano sull'header a 40 pin (LAFVIN/MHS 3.5"),
tipicamente su Raspberry Pi OS più vecchi.

**Collegamento:** lo shield si innesta direttamente sui 40 pin (occupa SPI0:
MOSI/SCLK/CE0/CE1 più alcuni GPIO per DC/RST/backlight). Nessun cablaggio a
mano: allinea il pin 1 e premi.

**Abilita SPI e installa il driver:**

```sh
sudo raspi-config nonint do_spi 0
git clone https://github.com/goodtft/LCD-show
cd LCD-show
sudo ./MHS35-show        # riavvia da solo; modifica /boot/config.txt e X
```

Approccio più pulito, se il produttore fornisce un `.dtbo`:

```sh
sudo cp mhs35.dtbo /boot/overlays/
echo "dtoverlay=mhs35:rotate=90" | sudo tee -a /boot/config.txt
sudo reboot
```

> Su kernel recenti (6.x, Bookworm/Trixie) molti overlay fbtft per l'ST7796S
> non esistono più: in quel caso usa la **Variante B**.

---

## Variante B — modulo 4.0" ST7796S cablato (panel-mipi-dbi) — **consigliata**

Ricetta **verificata** per il modulo rosso generico "4.0 TFT SPI 480×320" (chip
ST7796S + touch XPT2046), formato shield Arduino → **si cabla a mano** al Pi.
Vale in generale per pannelli ST7796S SPI su Raspberry Pi OS Bookworm/Trixie.

### B.1 Cablaggio (display → Pi)

Cerca le sigle serigrafate sul retro del modulo. Per il monitor il **touch non
serve**: bastano i primi 9 fili.

| Pin display | Funzione | Pin fisico Pi | GPIO (BCM) |
|---|---|---|---|
| VCC | Alimentazione | **2** (5V) o **1** (3.3V) | — |
| GND | Massa | **6** | — |
| CS | Chip select | **24** | GPIO8 / CE0 |
| RESET | Reset | **22** | GPIO25 |
| DC / RS | Data/Command | **18** | GPIO24 |
| SDI (MOSI) | SPI dati in | **19** | GPIO10 |
| SCK | SPI clock | **23** | GPIO11 |
| LED | Retroilluminazione | **12** | GPIO18 |
| SDO (MISO) | SPI dati out | **21** | GPIO9 |

VCC accetta 3.3–5 V; nel dubbio parti da **3.3 V** (pin 1). I pin GPIO qui sopra
devono combaciare con i parametri dell'overlay al passo B.3.

### B.2 Abilita SPI

L'overlay `mipi-dbi-spi` abilita SPI0 e occupa CS0 da solo, quindi **non**
serve `dtparam=spi=on` (creerebbe conflitto su CS0).

### B.3 Overlay in `config.txt`

Su Bookworm/Trixie il file è `/boot/firmware/config.txt` (prima era
`/boot/config.txt`). Fai un backup e aggiungi in coda, sotto `[all]`:

```ini
# --- Display SPI ST7796S 4.0" 480x320 ---
# CS=CE0(GPIO8)  DC=GPIO24  RESET=GPIO25  LED=GPIO18  MOSI=GPIO10  SCK=GPIO11
dtoverlay=mipi-dbi-spi,spi0-0,speed=32000000
dtparam=width=480,height=320
dtparam=reset-gpio=25,dc-gpio=24
dtparam=backlight-gpio=18
```

```sh
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.bak
```

### B.4 Firmware di init `panel.bin`

`panel-mipi-dbi` carica la sequenza di inizializzazione da
`/lib/firmware/panel.bin`. La sequenza per l'ST7796S (landscape 480×320,
RGB565, BGR, **inversione OFF**):

```
command 0x11        # SLPOUT (esci dallo sleep)
delay 120
command 0x3A 0x55   # COLMOD: 16 bit/pixel (RGB565)
command 0x36 0x28   # MADCTL: MV|BGR -> landscape 480x320, ordine BGR
command 0x20        # INVOFF: inversione display OFF
command 0x29        # DISPON: display acceso
delay 20
```

Puoi generare il `.bin` con lo strumento ufficiale
([notro/panel-mipi-dbi](https://github.com/notro/panel-mipi-dbi), `mipi-dbi-cmd`)
oppure, senza dipendenze, con questo generatore (formato: magic `MIPI DBI` +
7 null + versione 1; ogni comando = `cmd, n_param, param…`; ogni delay =
`0x00, 0x01, ms`):

```sh
cat > /tmp/st7796.txt <<'INIT'
command 0x11
delay 120
command 0x3A 0x55
command 0x36 0x28
command 0x20
command 0x29
delay 20
INIT

python3 - <<'PY'
magic = b"MIPI DBI" + b"\x00"*7
out = bytearray(magic) + b"\x01"
for raw in open("/tmp/st7796.txt"):
    line = raw.split("#", 1)[0].strip()
    if not line:
        continue
    p = line.split()
    if p[0] == "command":
        v = [int(x, 0) for x in p[1:]]
        out += bytes([v[0], len(v) - 1]) + bytes(v[1:])
    elif p[0] == "delay":
        out += bytes([0x00, 0x01, int(p[1], 0)])
open("/tmp/panel.bin", "wb").write(out)
print("panel.bin:", len(out), "byte")
PY

sudo cp /tmp/panel.bin /lib/firmware/panel.bin
sudo reboot
```

### B.5 Accendere la pipeline al boot (il passo che manca a tutti)

Dopo il reboot `/dev/fb1` esiste ma la pipeline è **disabilitata**
(`cat /sys/class/drm/card0-SPI-1/enabled` → `disabled`) → schermo bianco. Va
forzato **un** modeset con `fbset`. Per renderlo automatico e persistente crea
un servizio, ordinato **prima** del kiosk:

```sh
sudo tee /etc/systemd/system/panel-enable.service >/dev/null <<'UNIT'
[Unit]
Description=Enable ST7796S SPI panel pipeline (DRM modeset via fbset)
Before=claude-kiosk.service
DefaultDependencies=no
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for i in $(seq 1 30); do [ -e /dev/fb1 ] && break; sleep 1; done; /usr/bin/fbset -fb /dev/fb1 -g 480 320 480 320 16'

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl enable --now panel-enable.service
```

> **Attenzione al ciclo di ordinamento in systemd.** *Non* mettere
> `After=multi-user.target` in un servizio che è anche `WantedBy=multi-user.target`:
> crea una dipendenza circolare e systemd, per romperla, **cancella l'avvio del
> kiosk**. Usa `Before=claude-kiosk.service` come sopra.

Fai in modo che il kiosk parta dopo, con un drop-in:

```sh
sudo mkdir -p /etc/systemd/system/claude-kiosk.service.d
sudo tee /etc/systemd/system/claude-kiosk.service.d/10-after-panel.conf >/dev/null <<'CONF'
[Unit]
After=panel-enable.service
Wants=panel-enable.service
CONF
sudo systemctl daemon-reload
```

---

## Verifica

```sh
ls /dev/fb*                                   # atteso: /dev/fb1 (SPI)
cat /sys/class/graphics/fb1/virtual_size      # atteso: 480,320
cat /sys/class/drm/card0-SPI-1/enabled        # atteso: enabled (dopo panel-enable)
```

**Test neve** (pixel casuali, conferma che i dati arrivano al pannello):

```sh
sudo sh -c 'cat /dev/urandom > /dev/fb1' ; true
```

**Test colori/orientamento** (bande rosso/verde/blu + quadrato bianco in alto a
sinistra — così vedi in un colpo colori giusti e verso):

```sh
python3 - <<'PY'
W,H=480,320
def px(r,g,b):
    v=((r&0xF8)<<8)|((g&0xFC)<<3)|(b>>3); return bytes([v&0xFF,v>>8])
buf=bytearray()
for y in range(H):
    c = px(255,0,0) if y<H//3 else px(0,255,0) if y<2*H//3 else px(0,0,255)
    row=bytearray(c*W)
    if y<40:
        w=px(255,255,255)
        for x in range(40): row[x*2:x*2+2]=w
    buf+=row
open("/dev/fb1","wb").write(buf)
PY
```

Se le bande sono rossa/verde/blu con il quadrato bianco in alto a sinistra, è
tutto a posto: lancia `./install-kiosk.sh` (motore *native*, framebuffer
`/dev/fb1`).

---

## Problemi comuni

- **Schermo bianco, `/dev/fb1` esiste.** Pipeline non abilitata: manca il
  modeset. `cat /sys/class/drm/card0-SPI-1/enabled` → se `disabled`, esegui
  `sudo fbset -fb /dev/fb1 -g 480 320 480 320 16` (e installa `panel-enable`,
  passo B.5). *Vale sia col test manuale sia col kiosk: `kiosk-fb.py` scrive con
  `write()`, che non basta se la pipeline è spenta.*
- **Schermo nero (spento).** Retroilluminazione: `cat /sys/class/backlight/*/bl_power`
  → se `4`, forzala con `echo 0 | sudo tee /sys/class/backlight/*/bl_power`. Se
  resta nero con GPIO18 alto, prova a collegare il pin **LED direttamente a
  3.3V/5V** per isolare l'hardware.
- **Colori a negativo** (rosso→ciano ecc.): cambia in `panel.bin` `0x21`↔`0x20`
  (INVON/INVOFF), rigenera, riavvia.
- **Rosso/blu scambiati** (verde ok): togli/aggiungi il bit BGR in `MADCTL`
  (es. `0x28` ↔ `0x20`).
- **Ruotato/specchiato**: cambia i bit alti di `MADCTL` (`0x28`/`0x48`/`0x88`/`0xE8`).
- **Bianco/garbage anche con pipeline attiva**: velocità SPI troppo alta →
  abbassa `speed=16000000` nell'overlay.
- **Il kiosk non parte al boot** (`systemctl is-active claude-kiosk` → inactive,
  nessun log): probabile ciclo di ordinamento — vedi l'avviso al passo B.5
  (`journalctl -b | grep -i "ordering cycle"`).
- **`kiosk-fb.py` cerca `/dev/fb0`**: l'installer passa `--fb /dev/fb1` quando
  il pannello è presente; se lo lanci a mano, specifica `--fb /dev/fb1`.

## Tornare indietro

Rimuovi le righe aggiunte in `/boot/firmware/config.txt` (o ripristina il
backup), disabilita i servizi e riavvia:

```sh
sudo systemctl disable --now panel-enable.service claude-kiosk.service
sudo cp /boot/firmware/config.txt.bak /boot/firmware/config.txt
sudo reboot
```

## Verificato su

Variante B verificata end-to-end (2026-07):

- **Pi**: Raspberry Pi Zero W Rev 1.1 (`armv6l`)
- **OS**: Raspberry Pi OS / Raspbian GNU/Linux 13 (trixie), kernel
  `6.18.34+rpt-rpi-v6`
- **Pannello**: modulo rosso "4.0 TFT SPI 480×320 V1.1", ST7796S + touch
  XPT2046 (cablato a mano, non a shield)
- **Driver**: `panel-mipi-dbi` (overlay `mipi-dbi-spi`), SPI @ 32 MHz,
  `panel.bin` con MADCTL `0x28` + INVOFF
- **Esito**: `/dev/fb1` a 480×320 RGB565, pipeline abilitata da
  `panel-enable.service` al boot, kiosk *native* attivo dopo `panel-enable`.
