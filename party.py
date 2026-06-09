"""Party mode: rapidly cycle the colour ceiling light through the hue wheel.

Runs as a background thread so the web UI can toggle it on/off. Only the
colour-capable device is driven (the CCT bulb has no hue). A music-sync hook
is sketched at the bottom — see `_next_colour` for where beat/intensity input
would steer hue and brightness instead of the free-running cycle.
"""

import threading
import time

import lamp

# LAN pacing: each set_value is a round-trip to the lamp. ~0.25 s keeps the
# colour changes lively without flooding the device (it starts dropping/lagging
# below ~0.2 s on the v3.3 local protocol).
INTERVAL = 0.25
HUE_STEP = 18          # degrees per tick → full wheel in 20 ticks (~5 s)

_running = threading.Event()
_thread = None


def _hsv_hex(h: int, s: int, v: int) -> str:
    """Tuya colour_data_v2 hex: H 0–360, S/V 0–1000."""
    return "%04x%04x%04x" % (int(h) % 360, max(0, min(1000, int(s))), max(0, min(1000, int(v))))


def _next_colour(hue: int) -> tuple[int, int, int]:
    """Return the (h, s, v) for this tick.

    Music-sync hook: replace the free-running hue here with values derived from
    live audio — e.g. map the dominant frequency band to hue and the beat
    envelope to v (brightness). Keep the same (h, s, v) return shape so the
    drive loop below is unchanged.
    """
    return hue, 1000, 1000


def _loop(device: str):
    try:
        cfg = lamp.load_config()
        if device not in cfg:
            return
        dev = lamp.make_device(cfg[device])
        try:
            dev.turn_on()
            dev.set_value(21, "colour")
        except Exception:
            pass
        hue = 0
        while _running.is_set():
            h, s, v = _next_colour(hue)
            try:
                dev.set_value(24, _hsv_hex(h, s, v))
            except Exception:
                pass
            hue = (hue + HUE_STEP) % 360
            time.sleep(INTERVAL)
    finally:
        _running.clear()


def start(device: str = "ceiling") -> bool:
    """Begin cycling. Returns False if already running."""
    global _thread
    if _running.is_set():
        return False
    _running.set()
    _thread = threading.Thread(target=_loop, args=(device,), daemon=True)
    _thread.start()
    return True


def stop():
    _running.clear()


def is_active() -> bool:
    return _running.is_set()
