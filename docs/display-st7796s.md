# Display SPI ST7796S (es. LAFVIN 3.5" 480×320) sul Pi

I pannelli TFT 3.5" a shield (si innestano sui 40 pin GPIO) non sono monitor
HDMI: serve un driver kernel che crei un framebuffer (`/dev/fb1`) prima che
qualsiasi cosa possa disegnarci. Questa guida copre i pannelli col controller
**ST7796S**, come il LAFVIN 3.5"; per altri pannelli cambia solo il driver,
i passi sono gli stessi.

> Il kiosk (`./install-kiosk.sh`, motore *native*) parte **dopo** che questa
> guida ha prodotto un `/dev/fb1` funzionante.

## 1. Collegamento

Lo shield si innesta direttamente sull'header a 40 pin (occupa i pin SPI0:
MOSI/SCLK/CE0/CE1 più alcuni GPIO per DC/RST/retroilluminazione). Nessun
cablaggio manuale: allinea il pin 1 e premi.

## 2. Abilita SPI

    sudo raspi-config nonint do_spi 0

## 3. Driver

### Strada A — script del produttore (LCD-show)

La più comune per questi shield (venduti anche come "MHS-3.5inch"):

    git clone https://github.com/goodtft/LCD-show
    cd LCD-show
    sudo ./MHS35-show    # riavvia da solo

Attenzione: lo script modifica `/boot/config.txt` e la configurazione X.
Su un Pi dedicato al monitor va bene; fai un backup della SD se ci tieni.

### Strada B — solo dtoverlay (senza toccare il resto del sistema)

Se il produttore fornisce un file `.dtbo` (overlay device-tree), copialo e
attivalo a mano — è l'approccio più pulito:

    sudo cp mhs35.dtbo /boot/overlays/
    echo "dtoverlay=mhs35:rotate=90" | sudo tee -a /boot/config.txt
    sudo reboot

## 4. Verifica

Dopo il riavvio deve esistere il framebuffer del pannello:

    ls /dev/fb*          # atteso: /dev/fb0 e /dev/fb1
    cat /sys/class/graphics/fb1/virtual_size   # atteso: 480,320

Test visivo (neve casuale sullo schermo):

    sudo sh -c 'cat /dev/urandom > /dev/fb1' ; true

Se vedi la neve, il display funziona: ora `./install-kiosk.sh` col motore
*native* e framebuffer `/dev/fb1`.

## Problemi comuni

- **Schermo bianco**: driver sbagliato o velocità SPI troppo alta — prova
  `:speed=16000000` tra i parametri dell'overlay.
- **Colori invertiti**: aggiungi `:bgr` ai parametri dell'overlay.
- **Ruotato male**: cambia `rotate=0|90|180|270`.
- **Tornare indietro**: rimuovi la riga `dtoverlay=...` da `/boot/config.txt`
  (o, con LCD-show, `sudo ./LCD-hdmi`) e riavvia.

## Verificato su

*(da completare al primo test su hardware reale — modello Pi, OS, kernel,
strada seguita)*
