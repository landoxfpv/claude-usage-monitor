#!/usr/bin/env python3
"""Claude Usage Monitor — server per Raspberry Pi (solo stdlib, Python 3.7+).

Riceve via POST il JSON della statusline di Claude Code (inoltrato dal Mac),
tiene in memoria l'ultimo payload e serve una pagina web in LAN che lo mostra.

Endpoints:
  GET  /            pagina web (index.html nella stessa cartella)
  GET  /api/usage   ultimo payload ricevuto + timestamp
  POST /api/usage   riceve un nuovo payload

Persistenza: l'ultimo dato viene scritto su data.json al massimo una volta
ogni 60s (per non consumare la SD del Pi) e ricaricato all'avvio.
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
PORT = int(os.environ.get("PORT", "8787"))
PERSIST_INTERVAL = 60  # secondi minimi tra due scritture su disco

SESSION_TTL = 1800  # dopo 30 min di silenzio una sessione esce dalla lista

_lock = threading.Lock()
# session_id -> {"received_at": epoch, "payload": {...}}
_sessions = {}
_last_persist = 0.0


def _load_state():
    global _sessions
    try:
        with open(DATA_FILE, "r") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return
    if isinstance(saved, dict) and isinstance(saved.get("sessions"), dict):
        _sessions = saved["sessions"]
    elif isinstance(saved, dict) and saved.get("payload"):
        # formato precedente (payload singolo): converti
        sid = saved["payload"].get("session_id", "unknown")
        _sessions = {sid: {"received_at": saved.get("received_at"), "payload": saved["payload"]}}


def _prune(now):
    """Scarta le sessioni silenziose da oltre SESSION_TTL, ma tieni sempre la
    più recente: da fermo il monitor deve mostrare l'ultimo dato noto."""
    if len(_sessions) <= 1:
        return
    newest = max(_sessions, key=lambda k: _sessions[k]["received_at"] or 0)
    for sid in list(_sessions):
        if sid != newest and now - (_sessions[sid]["received_at"] or 0) > SESSION_TTL:
            del _sessions[sid]


def _snapshot(now):
    """Stato per il client: sessioni ordinate dalla più recente, più i campi
    top-level received_at/payload (compatibilità col formato precedente)."""
    ordered = sorted(_sessions.values(), key=lambda s: s["received_at"] or 0, reverse=True)
    latest = ordered[0] if ordered else {"received_at": None, "payload": None}
    return {"received_at": latest["received_at"], "payload": latest["payload"],
            "sessions": ordered}


def _persist_state():
    global _last_persist
    now = time.time()
    if now - _last_persist < PERSIST_INTERVAL:
        return
    _last_persist = now
    tmp = DATA_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump({"sessions": _sessions}, f)
        os.replace(tmp, DATA_FILE)
    except OSError:
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "ClaudeUsageMonitor/1.0"

    def _send(self, code, body, content_type="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            try:
                with open(INDEX_FILE, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, '{"error":"index.html mancante"}')
        elif path == "/api/usage":
            with _lock:
                body = json.dumps(_snapshot(time.time()))
            self._send(200, body)
        elif path == "/health":
            self._send(200, '{"ok":true}')
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        if self.path.split("?")[0] != "/api/usage":
            self._send(404, '{"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError("bad length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(400, '{"error":"json non valido"}')
            return
        sid = payload.get("session_id", "unknown") if isinstance(payload, dict) else "unknown"
        now = time.time()
        with _lock:
            _sessions[sid] = {"received_at": now, "payload": payload}
            _prune(now)
            _persist_state()
        self._send(200, '{"ok":true}')

    def log_message(self, fmt, *args):
        # Silenzia il log delle GET (la pagina fa polling ogni 30s)
        if args and isinstance(args[0], str) and args[0].startswith("GET"):
            return
        BaseHTTPRequestHandler.log_message(self, fmt, *args)


def main():
    _load_state()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Claude Usage Monitor in ascolto su http://0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
