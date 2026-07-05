#!/usr/bin/env python3
"""Claude Usage Monitor — renderer kiosk nativo per framebuffer.

Disegna la vista kiosk (stessa grafica di index.html sotto i 420px) dritto
sul framebuffer, senza X né browser: pensato per Pi Zero W con pannelli SPI.
Legge i dati dalla stessa API della pagina web: GET /api/usage su localhost.

Uso:
  kiosk-fb.py --fb /dev/fb1                  # sul Pi, dentro claude-kiosk.service
  kiosk-fb.py --out preview.png --size 480x320   # sviluppo: un frame su PNG
"""

import argparse
import datetime
import json
import os
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

POLL_INTERVAL = 15.0    # secondi tra due letture dell'API
REDRAW_INTERVAL = 1.0   # ridisegno (i countdown scattano al secondo)
ROTATE_INTERVAL = 10.0  # rotazione carosello sessioni, come l'HTML

PREF_ORDER = ["five_hour", "seven_day"]
WINDOW_LABELS = {"five_hour": "SESSIONE · 5H", "seven_day": "SETTIMANA · 7G"}

# Tabelle di lookup per la conversione RGB -> RGB565 little-endian:
# byte alto = RRRRRGGG, byte basso = GGGBBBBB
_T_R_HI = bytes((v & 0xF8) for v in range(256))
_T_G_HI = bytes((v >> 5) for v in range(256))
_T_G_LO = bytes(((v & 0x1C) << 3) for v in range(256))
_T_B_LO = bytes((v >> 3) for v in range(256))

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.path.join(BASE_DIR, "fonts")
SANS_TTF = os.path.join(FONT_DIR, "Manrope[wght].ttf")
MONO_TTF = os.path.join(FONT_DIR, "JetBrainsMono[wght].ttf")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_fonts = {}


def load_font(size, weight=600, mono=False):
    key = (size, weight, mono)
    if key not in _fonts:
        try:
            f = ImageFont.truetype(MONO_TTF if mono else SANS_TTF, size)
            try:
                f.set_variation_by_axes([weight])
            except OSError:
                pass  # FreeType senza supporto variabile: peso di default
        except OSError:
            try:
                f = ImageFont.truetype(_DEJAVU, size)
            except OSError:
                f = ImageFont.load_default()
        _fonts[key] = f
    return _fonts[key]


# Palette: copia delle CSS vars di index.html
PAL = {
    "bg": (13, 10, 18),        # --ink-950
    "grid": (19, 15, 26),      # trama griglia (2.5% bianco su bg)
    "panel": (29, 23, 41),     # --ink-800
    "panel_hi": (23, 18, 33),  # --ink-850
    "track": (47, 37, 66),     # --ink-600
    "border": (38, 32, 52),    # --border-subtle su bg
    "fg1": (242, 239, 247),    # --fg-1
    "fg2": (185, 176, 204),    # --fg-2
    "fg3": (132, 122, 156),    # --fg-3
    "violet": (126, 95, 165),  # --violet-500
    "mint": (91, 208, 184),    # --mint-400
    "warning": (232, 176, 75),
    "danger": (229, 88, 107),
}


def bar_color(pct):
    if pct >= 90:
        return PAL["danger"]
    if pct >= 70:
        return PAL["warning"]
    return PAL["violet"]


def _panel(d, x, y, w, h, win, s, now):
    pad = round(14 * s)
    d.rounded_rectangle([x, y, x + w, y + h], radius=round(14 * s),
                        fill=PAL["panel"], outline=PAL["border"])
    d.text((x + pad, y + pad), win["label"],
           font=load_font(round(10 * s), 600, mono=True), fill=PAL["fg3"])
    d.text((x + pad, y + pad + round(12 * s)), f"{win['pct']:.0f}%",
           font=load_font(round(46 * s), 800), fill=PAL["fg1"])
    bar_y = y + h - pad - round(22 * s)
    bar_w = w - 2 * pad
    bh = round(6 * s)
    d.rounded_rectangle([x + pad, bar_y, x + pad + bar_w, bar_y + bh],
                        radius=bh // 2, fill=PAL["track"])
    fill_w = round(bar_w * min(win["pct"], 100.0) / 100)
    if fill_w > bh:
        d.rounded_rectangle([x + pad, bar_y, x + pad + fill_w, bar_y + bh],
                            radius=bh // 2, fill=bar_color(win["pct"]))
    d.text((x + pad, bar_y + round(11 * s)), "RESET",
           font=load_font(round(8 * s), 600, mono=True), fill=PAL["fg3"])
    d.text((x + w - pad, bar_y + round(9 * s)),
           format_countdown(win["resets_at"], now),
           font=load_font(round(11 * s), 700), fill=PAL["fg2"], anchor="ra")


def _session_card(d, x, y, w, h, sessions, idx, s):
    pad = round(14 * s)
    d.rounded_rectangle([x, y, x + w, y + h], radius=round(14 * s),
                        fill=PAL["panel_hi"], outline=PAL["border"])
    if not sessions:
        d.text((x + w / 2, y + h / 2), "nessuna sessione attiva",
               font=load_font(round(10 * s), 500), fill=PAL["fg3"], anchor="mm")
        return
    sess = sessions[idx % len(sessions)]
    d.text((x + pad, y + pad), sess["name"],
           font=load_font(round(13 * s), 700), fill=PAL["fg1"])
    d.text((x + pad, y + pad + round(19 * s)), sess["meta"],
           font=load_font(round(10 * s), 500), fill=PAL["fg3"])
    if len(sessions) > 1:
        d.text((x + w - pad, y + pad), f"{idx % len(sessions) + 1}/{len(sessions)}",
               font=load_font(round(9 * s), 600, mono=True),
               fill=PAL["fg3"], anchor="ra")


def render_frame(state, size, carousel_index, now):
    w, h = size
    s = min(w / 480, h / 320)
    img = Image.new("RGB", size, PAL["bg"])
    d = ImageDraw.Draw(img)
    step = max(8, round(24 * s))
    for gx in range(0, w, step):
        d.line([(gx, 0), (gx, h)], fill=PAL["grid"])
    for gy in range(0, h, step):
        d.line([(0, gy), (w, gy)], fill=PAL["grid"])

    m = round(10 * s)
    d.text((m, m), "MORE DIGITAL LAB · USAGE MONITOR",
           font=load_font(round(10 * s), 600, mono=True), fill=PAL["fg3"])

    if state["status"] != "ok":
        no_server = state["status"] == "no-server"
        title = "In attesa del server…" if no_server else "In attesa del primo dato"
        sub = ("il servizio claude-usage non risponde" if no_server
               else "apri una sessione Claude Code sul computer")
        d.text((w / 2, h / 2 - round(10 * s)), title,
               font=load_font(round(20 * s), 800), fill=PAL["fg1"], anchor="mm")
        d.text((w / 2, h / 2 + round(16 * s)), sub,
               font=load_font(round(11 * s), 500), fill=PAL["fg3"], anchor="mm")
        return img

    fresh = state.get("updated_at") and now - state["updated_at"] < 300
    r = round(4 * s)
    d.ellipse([w - m - 2 * r, m + r, w - m, m + 3 * r],
              fill=PAL["mint"] if fresh else PAL["fg3"])
    if state.get("model"):
        d.text((w - m - 3 * r - round(4 * s), m), state["model"],
               font=load_font(round(10 * s), 600), fill=PAL["fg2"], anchor="ra")

    top = round(34 * s)
    card_h = round(58 * s)
    gap = round(10 * s)
    panel_h = h - top - card_h - gap - m
    windows = state["windows"] or [{"key": "?", "label": "NESSUNA FINESTRA",
                                    "pct": 0.0, "resets_at": None}]
    n = len(windows)
    pw = (w - 2 * m - gap * (n - 1)) // n
    for i, win in enumerate(windows):
        _panel(d, m + i * (pw + gap), top, pw, panel_h, win, s, now)
    _session_card(d, m, top + panel_h + gap, w - 2 * m, card_h,
                  state["sessions"], carousel_index, s)
    return img


def fetch_usage(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def format_countdown(resets_at, now):
    if not resets_at:
        return "—"
    s = int(resets_at - now)
    if s <= 0:
        return "ora"
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m, sec = divmod(rem, 60)
    if d:
        return f"{d}g {h:02d}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {sec:02d}s"


def format_duration(ms):
    s = int(ms // 1000)
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _session_view(entry):
    p = entry.get("payload")
    p = p if isinstance(p, dict) else {}
    ws = p.get("workspace") or {}
    cost = p.get("cost") or {}
    name = (os.path.basename((ws.get("current_dir") or "").rstrip("/"))
            or (p.get("session_id") or "sessione")[:8])
    parts = []
    model = (p.get("model") or {}).get("display_name")
    if model:
        parts.append(model)
    usd = cost.get("total_cost_usd")
    if usd is not None:
        parts.append(f"${usd:.2f}")
    added, removed = cost.get("total_lines_added"), cost.get("total_lines_removed")
    if added is not None or removed is not None:
        parts.append(f"+{added or 0}/-{removed or 0}")
    ms = cost.get("total_duration_ms")
    if ms:
        parts.append(format_duration(ms))
    return {"name": name, "meta": " · ".join(parts)}


def _reset_epoch(value):
    """Normalizza resets_at in epoch-secondi float, o None. Rispecchia
    resetEpochMs() di index.html: numero (ms se > 1e12, altrimenti secondi)
    oppure stringa ISO 8601 (anche con suffisso 'Z')."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value / 1000.0 if value > 1e12 else float(value)
    if isinstance(value, str):
        v = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            return datetime.datetime.fromisoformat(v).timestamp()
        except ValueError:
            return None
    return None


def _pct(win):
    """Percentuale d'uso con gli stessi alias di pct() in index.html."""
    for key in ("used_percentage", "utilization", "used_pct", "percent"):
        v = win.get(key)
        if v is not None:
            return float(v)
    return 0.0


def parse_state(snap, now):
    if not isinstance(snap, dict):
        return {"status": "no-server"}
    payload = snap.get("payload")
    if not isinstance(payload, dict):
        return {"status": "no-data"}
    rl = payload.get("rate_limits") or {}
    keys = ([k for k in PREF_ORDER if k in rl]
            + sorted(k for k in rl if k not in PREF_ORDER))
    windows = []
    for k in keys[:2]:
        win = rl.get(k) or {}
        windows.append({
            "key": k,
            "label": WINDOW_LABELS.get(k, k.replace("_", " ").upper()),
            "pct": _pct(win),
            "resets_at": _reset_epoch(win.get("resets_at")),
        })
    return {
        "status": "ok",
        "updated_at": snap.get("received_at"),
        "model": (payload.get("model") or {}).get("display_name"),
        "windows": windows,
        "sessions": [_session_view(e) for e in (snap.get("sessions") or [])],
    }


def frame_to_bytes(img, bpp):
    if bpp == 16:
        # RGB565 little-endian, vettorizzato: niente loop per-pixel
        # (il Pi Zero W non reggerebbe 153k iterazioni Python al secondo)
        data = img.tobytes()
        r, g, b = data[0::3], data[1::3], data[2::3]
        n = len(r)
        hi = (int.from_bytes(r.translate(_T_R_HI), "big")
              | int.from_bytes(g.translate(_T_G_HI), "big"))
        lo = (int.from_bytes(g.translate(_T_G_LO), "big")
              | int.from_bytes(b.translate(_T_B_LO), "big"))
        out = bytearray(2 * n)
        out[0::2] = lo.to_bytes(n, "big")
        out[1::2] = hi.to_bytes(n, "big")
        return bytes(out)
    if bpp == 24:
        return img.tobytes("raw", "BGR")
    return img.tobytes("raw", "BGRX")          # 32bpp XRGB, byte meno significativo per primo


def pad_rows(data, width, bpp, stride):
    row = width * bpp // 8
    if stride <= row:
        return data
    pad = b"\x00" * (stride - row)
    return b"".join(data[i:i + row] + pad for i in range(0, len(data), row))


class FramebufferOutput:
    def __init__(self, fbdev, sysfs="/sys/class/graphics"):
        self.fbdev = fbdev
        base = os.path.join(sysfs, os.path.basename(fbdev))
        with open(os.path.join(base, "virtual_size")) as f:
            w, h = f.read().strip().split(",")
        self.size = (int(w), int(h))
        with open(os.path.join(base, "bits_per_pixel")) as f:
            self.bpp = int(f.read().strip())
        try:
            with open(os.path.join(base, "stride")) as f:
                self.stride = int(f.read().strip())
        except OSError:
            self.stride = self.size[0] * self.bpp // 8

    def write(self, img):
        data = pad_rows(frame_to_bytes(img, self.bpp),
                        self.size[0], self.bpp, self.stride)
        with open(self.fbdev, "wb") as f:
            f.write(data)


def run(args):
    out = FramebufferOutput(args.fb)
    state = {"status": "no-server"}
    last_poll = 0.0
    last_rotate = time.time()
    carousel = 0
    while True:
        now = time.time()
        if now - last_poll >= POLL_INTERVAL:
            state = parse_state(fetch_usage(args.url), now)
            last_poll = now
        if now - last_rotate >= ROTATE_INTERVAL:
            carousel += 1
            last_rotate = now
        out.write(render_frame(state, out.size, carousel, now))
        time.sleep(REDRAW_INTERVAL)


def main():
    ap = argparse.ArgumentParser(description="Renderer kiosk nativo (framebuffer)")
    ap.add_argument("--fb", default="/dev/fb0", help="device framebuffer")
    ap.add_argument("--url", default="http://localhost:8787/api/usage")
    ap.add_argument("--out", help="renderizza un solo frame su PNG ed esci (sviluppo)")
    ap.add_argument("--size", default="480x320", help="risoluzione con --out, es. 480x320")
    args = ap.parse_args()
    if args.out:
        w, h = (int(v) for v in args.size.lower().split("x"))
        now = time.time()
        state = parse_state(fetch_usage(args.url), now)
        render_frame(state, (w, h), 0, now).save(args.out)
        print(f"frame salvato in {args.out} (stato: {state['status']})")
        return
    run(args)


if __name__ == "__main__":
    main()
