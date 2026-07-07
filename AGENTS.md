# AGENTS.md — Runbook for AI agents

You are an agent (e.g. Claude Code) and the user asked you to install or
manage **Claude Usage Monitor**: a LAN dashboard for Claude subscription
usage, with a server on a Raspberry Pi and a forwarder hooked into Claude
Code's statusline. This file tells you how to do it on their behalf, what to
verify, and where to stop.

## Architecture in 10 seconds

- `mac/statusline-forward.sh` → configured as the Claude Code statusline on
  the user's computer: forwards the statusline JSON (which includes
  `rate_limits`, i.e. the /usage data) via POST to the Pi, then delegates
  rendering to the pre-existing statusline (`STATUSLINE_CMD`) or prints a
  minimal built-in line.
- `pi/server.py` → on the Pi (stdlib Python, port 8787): receives payloads,
  keeps them per `session_id` (30 min TTL), serves `pi/index.html`.
- Client config in `~/.claude/usage-monitor.env`: `PI_URL` and `STATUSLINE_CMD`.
- No OAuth tokens, no undocumented APIs: only the official statusline
  mechanism. Do not "improve" this by switching approach.

## Prerequisites to verify before starting

1. Claude Code ≥ 2.1.80 on the computer (`claude --version`); below that the
   statusline payload has no `rate_limits` → tell the user and stop.
2. `python3` available on both the computer and the Pi.
3. The Pi is reachable: ask the user for hostname or IP if unknown
   (`raspberrypi.local` is the default). If the Pi is not flashed/powered yet,
   walk the user through `docs/tutorial.html` (STEP 01): the microSD is
   prepared with Raspberry Pi Imager, WiFi and SSH are set there. You cannot
   do that part for them.
4. If the Pi was re-flashed since the last connection, `ssh` fails with
   `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED`. Expected after a
   re-flash, not a security incident: run `ssh-keygen -R <pi-host-or-ip>`
   on the computer, reconnect, accept the new key.

## Installation (use the installers, do not hand-roll)

### Pi side (over SSH)

```sh
ssh <user>@<pi-host> 'git clone https://github.com/landoxfpv/claude-usage-monitor 2>/dev/null; cd claude-usage-monitor && git pull --ff-only 2>/dev/null; ./install-pi.sh'
```

If `git` is missing on the Pi: `sudo apt update && sudo apt install -y git`.
Fallback when apt is not viable:
`scp -r pi/ install-pi.sh <user>@<pi-host>:~/claude-usage-monitor/` and run
the installer there.

**Never run the installers as root or via sudo** — they refuse and exit.
With sudo, `$HOME` becomes `/root`: files land in `/root/claude-usage-monitor`
and the service runs as `root`, diverging from this runbook. For
non-interactive SSH sessions, pre-authenticate sudo first, then run the
script as the normal user (it finds the cached credentials):

```sh
ssh <user>@<pi-host> 'echo <password> | sudo -S -v && cd claude-usage-monitor && ./install-pi.sh'
```

Verify: `curl -s http://<pi-host>:8787/health` → must return `{"ok":true}`.

### Computer side

```sh
./install-client.sh <pi-host-or-ip>
```

The installer patches `~/.claude/settings.json` and **automatically
preserves** any pre-existing statusline as `STATUSLINE_CMD`. Do not edit
`settings.json` by hand and never overwrite an existing statusline outside
this mechanism. It is idempotent: re-running it is safe.

## Optional: dedicated display on the Pi (kiosk)

Only if the user says a screen is attached to the Pi itself (HDMI or a
GPIO/SPI panel), and only **after** `install-pi.sh` has succeeded:

```sh
ssh <user>@<pi-host> 'cd claude-usage-monitor && ./install-kiosk.sh'
```

It is interactive: it detects the Pi and proposes a default engine (Enter
accepts it), so run it in a session that can prompt, or relay the prompts to
the user.

- **Engines**: `chromium` (full-screen page via the `cage` Wayland
  compositor; default on Pi 3/4/5 and Zero 2 W) or `native` (a small Python
  process drawing straight to the framebuffer, no browser; default on
  `armv6l`, i.e. the original Pi Zero W). `/dev/fb1` is preferred over
  `/dev/fb0` when present (typical of SPI panels).
- **GPIO/SPI panels** (e.g. 3.5" ST7796S shields) need a kernel driver
  first, producing a working `/dev/fb1` — walk the user through
  `docs/display-st7796s.md` before running the native engine on such a
  panel.
- **Verify**: `systemctl is-active claude-kiosk` → must return `active`; on
  failure check `journalctl -u claude-kiosk -e`.
- **Remove**: `sudo systemctl disable --now claude-kiosk`.

## End-to-end verification (mandatory before declaring success)

1. `curl -s http://<pi>:8787/health` → `{"ok":true}`.
2. Already-open Claude Code sessions do not reload the statusline config: a
   new session is needed (ask the user to send a message in a new one).
3. Within ~30s: `curl -s http://<pi>:8787/api/usage` → the JSON must contain a
   populated `payload.rate_limits` and a non-empty `sessions` array.
4. If the payload arrives but `rate_limits` is missing → Claude Code too old.
5. Report the final page URL to the user and what they will see.

## Quick troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `/health` not responding | service down or wrong host | `ssh` → `systemctl status claude-usage`, `journalctl -u claude-usage -e` |
| Page stuck on waiting state | forwarder not configured or wrong PI_URL | re-run `install-client.sh`, check `~/.claude/usage-monitor.env` |
| Payload without `rate_limits` | Claude Code < 2.1.80 | update Claude Code |
| User's statusline disappeared | STATUSLINE_CMD missing from env | recover the command and add it to `~/.claude/usage-monitor.env` |
| Data not moving | Claude Code idle (normal behavior) | explain to the user, it is not a bug |

## Boundaries you must respect

- Do not expose the server outside the LAN (it has no authentication) and do
  not suggest port-forwarding.
- Do not extract or reuse Claude OAuth tokens to "enrich" the data.
- The payload contains the user's paths and repo names: do not send it
  anywhere else.
- Uninstall: remove the `statusLine` block from `~/.claude/settings.json` (or
  restore `STATUSLINE_CMD`), and on the Pi
  `sudo systemctl disable --now claude-usage`.
