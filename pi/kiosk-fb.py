#!/usr/bin/env python3
"""Claude Usage Monitor — renderer kiosk nativo per framebuffer.

Disegna la vista kiosk (stessa grafica di index.html sotto i 420px)dritto
sul framebuffer, senza X né browser: pensato per Pi Zero W con pannelli SPI.
Legge i dati dalla stessa API della pagina web: GET /api/usage su localhost.

Uso:
  kiosk-fb.py --fb /dev/fb1                  # sul Pi, dentro claude-kiosk.service
  kiosk-fb.py --out preview.png --size 480x320   # sviluppo: un frame su PNG
"""

import argparse
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
    m = rem // 60
    if d:
        return f"{d}g {h:02d}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def format_duration(ms):
    s = int(ms // 1000)
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _session_view(entry):
    p = entry.get("payload") or {}
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


def parse_state(snap, now):
    if not isinstance(snap, dict):
        return {"status": "no-server"}
    payload = snap.get("payload")
    if not payload:
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
            "pct": float(win.get("used_percentage") or 0.0),
            "resets_at": win.get("resets_at"),
        })
    return {
        "status": "ok",
        "updated_at": snap.get("received_at"),
        "model": (payload.get("model") or {}).get("display_name"),
        "windows": windows,
        "sessions": [_session_view(e) for e in (snap.get("sessions") or [])],
    }
