---
name: lamp-check
description: Read and control the real LSC smart lamps directly over LAN via the lsc.py CLI (status, raw DPS, on/off, brightness, temp). Use as the independent ground-truth oracle when verifying or iterating on the web UI / Flask API — to confirm what the physical lamps are actually doing, NOT via the app's own /api endpoints (those are the system under test).
---

# lamp-check — talk to the real lamps via CLI

The `lsc.py` CLI speaks directly to the lamps over the LAN (TinyTuya), bypassing
the Flask web app entirely. Use it as the **ground truth** when you've changed the
UI or the `/api` routes and need to know what the hardware is *actually* doing.
Never trust the app's own `/api/status` for verification — that's the code under test.

## Run

Always from the repo root, using the project venv:

```bash
.venv/bin/python lsc.py <command>
```

Devices: **`ceiling`** (LSC Smart Ceiling Light, CCT) — this is the default and
the one that matters for the verify loop. `bulb` (LSC A65 CCT bulb) exists too but
is usually off/offline; ignore it unless explicitly asked.

## Commands

| Command | What it does |
|---|---|
| `lsc.py status` | One-line state per device: `ON/OFF  bright=NN%  temp=NN%` |
| `lsc.py <dev> dps` | Raw TinyTuya DPS dict — the unfiltered truth |
| `lsc.py <dev> on` / `off` | Power |
| `lsc.py <dev> bright <0-100>` | Brightness % |
| `lsc.py <dev> temp <0-100>` | Colour temp (0 = warm, 100 = cool) |

DPS map (for reading raw output): `20`=power, `21`=mode (`white`/`colour`),
`22`=brightness (raw 10–1000), `23`=colour temp (raw 0–1000), `24`=colour (HSV hex).

## Known quirks — read before trusting output

- **`ceiling` when OFF returns only `{41: True}`** (a countdown/flag DP). So
  `lsc.py status` shows `ceiling  ?  bright=?  temp=?` and `dps` shows just `41`.
  A sparse reply still means the device is **reachable/online**; full state
  (DPS 20/22/23) only appears once it's on. Turn it `on` first if you need values.
- **`bulb` is frequently `OFFLINE`** (powered down at the wall). `OFFLINE` =
  no LAN response within the 3 s timeout, not necessarily a real fault.
- Each command opens its own short-lived connection (3 s timeout, 1 retry), so a
  call may take a couple of seconds or transiently fail — re-run before concluding.

## Typical verify-loop usage

`ceiling` is the device under observation. After changing the UI/API and
triggering an action, confirm the hardware agrees:

```bash
.venv/bin/python lsc.py ceiling dps      # raw truth for the ceiling lamp
.venv/bin/python lsc.py status           # one-line glance (both lamps)
```

To set up a known state before a test, drive `ceiling` directly here (e.g.
`lsc.py ceiling on`, `lsc.py ceiling bright 50`), then exercise the web app and
compare what the UI reports against this CLI.
