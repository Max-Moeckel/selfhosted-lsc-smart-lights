"""Central live-status poller + Server-Sent Events broadcaster.

One background thread queries every device over the LAN and caches the latest
snapshot; SSE clients receive the current snapshot on connect and every change
pushed thereafter. This replaces per-browser polling — the slow LAN query (the
ceiling light needs an updatedps round-trip) happens once, centrally, and all
open tabs update near-instantly instead of each polling on its own timer.

A command handler can call poke() to make the poller re-query immediately, so a
button press reconciles within a LAN round-trip instead of a full poll interval.
"""

import json
import threading

import lamp
import party

POLL_INTERVAL = 5.0        # seconds between LAN sweeps when nothing pokes
DEVICE_TIMEOUT = 8.0       # cap on how long one sweep waits for a device

_cond = threading.Condition()
_payload = None            # latest snapshot as a JSON string (None until first sweep)
_version = 0               # bumped on every change; clients wait for a newer version
_wake = threading.Event()  # set by poke() to cut a poll interval short


def _build() -> dict:
    """Query all devices (in parallel) and return {"status": {...}, "party": {...}}."""
    cfg = lamp.load_config()
    status = {}

    def query(name, dcfg):
        dev = lamp.make_device(dcfg)
        st = lamp.parse_status(lamp.get_dps(dev))
        st["profile"] = lamp.match_profile(st)
        status[name] = st  # distinct keys, GIL-safe across threads

    threads = [threading.Thread(target=query, args=(n, d), daemon=True)
               for n, d in cfg.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=DEVICE_TIMEOUT)

    return {
        "status": status,
        "party": {"active": party.is_active(), "mode": party.active_mode(),
                  "bpm": party.current_bpm()},
    }


def _publish(snap: dict) -> None:
    global _payload, _version
    payload = json.dumps(snap, separators=(",", ":"), sort_keys=True)
    with _cond:
        if payload == _payload:
            return                       # unchanged → don't wake clients
        _payload = payload
        _version += 1
        _cond.notify_all()


def _loop() -> None:
    while True:
        try:
            _publish(_build())
        except Exception:
            pass                         # a transient LAN hiccup shouldn't kill the poller
        _wake.wait(POLL_INTERVAL)
        _wake.clear()


def poke() -> None:
    """Ask the poller to re-query now (e.g. right after a command changed a lamp)."""
    _wake.set()


def start() -> None:
    threading.Thread(target=_loop, daemon=True).start()


def event_stream():
    """Generator for an SSE response: yields each snapshot as it changes.

    Sends the current snapshot immediately on connect, then blocks until the
    version advances. A comment line every 15 s keeps idle connections alive
    through proxies and lets EventSource notice a dropped link and reconnect.
    """
    last = 0
    while True:
        with _cond:
            changed = _cond.wait_for(lambda: _version != last, timeout=15)
            payload = _payload if changed else None
            if changed:
                last = _version
        if payload is not None:
            yield f"data: {payload}\n\n"
        else:
            yield ": ping\n\n"
