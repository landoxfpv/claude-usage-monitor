#!/usr/bin/env python3
"""Genera /lib/firmware/panel.bin per il driver panel-mipi-dbi.

Il driver panel-mipi-dbi carica la sequenza di init del pannello da un file
firmware binario. Questo script converte una sequenza in formato testo
(vedi st7796s.txt) nel binario atteso, senza dipendenze esterne.

Formato del .bin:
  - magic  : b"MIPI DBI" + 7 byte 0x00           (15 byte)
  - versione: 0x01                                (1 byte)
  - comando: <cmd> <n_param> <param...>
  - delay  : 0x00 0x01 <ms>                       (ms singolo byte, <=255)

Formato del testo in ingresso (una direttiva per riga, '#' = commento):
  command 0x11
  delay 120
  command 0x3A 0x55

Uso:
  python3 gen-panel-bin.py st7796s.txt panel.bin
  sudo cp panel.bin /lib/firmware/panel.bin
"""
import sys


def build(lines):
    out = bytearray(b"MIPI DBI" + b"\x00" * 7 + b"\x01")
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] == "command":
            vals = [int(x, 0) for x in parts[1:]]
            out += bytes([vals[0], len(vals) - 1]) + bytes(vals[1:])
        elif parts[0] == "delay":
            ms = int(parts[1], 0)
            if not 0 <= ms <= 255:
                raise SystemExit(f"delay fuori range (0-255 ms): {ms}")
            out += bytes([0x00, 0x01, ms])
        else:
            raise SystemExit(f"riga non valida: {line}")
    return bytes(out)


def main(argv):
    src = argv[1] if len(argv) > 1 else "st7796s.txt"
    dst = argv[2] if len(argv) > 2 else "panel.bin"
    with open(src) as f:
        data = build(f)
    with open(dst, "wb") as f:
        f.write(data)
    print(f"{dst}: {len(data)} byte")


if __name__ == "__main__":
    main(sys.argv)
