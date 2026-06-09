"""Party mode: rapidly cycle the colour ceiling light through the hue wheel.

Runs as a background thread so the web UI can toggle it on/off. Only the
colour-capable device is driven (the CCT bulb has no hue). A music-sync hook
is sketched at the bottom — see `_next_colour` for where beat/intensity input
would steer hue and brightness instead of the free-running cycle.
"""

import random
import threading
import time

import lamp

# LAN pacing: each set_value is a round-trip to the lamp. ~0.25 s keeps the
# colour changes lively without flooding the device (it starts dropping/lagging
# below ~0.2 s on the v3.3 local protocol).
INTERVAL = 0.25
HUE_STEP = 18          # degrees per tick → full wheel in 20 ticks (~5 s)
# Strobe is harsher: shorter ticks and sudden jumps to random saturated hues
# with brightness flicking between near-off and full for a punchy effect.
STROBE_INTERVAL = 0.12

_running = threading.Event()
_thread = None
_mode = "smooth"


def _hsv_hex(h: int, s: int, v: int) -> str:
    """Tuya colour_data_v2 hex: H 0–360, S/V 0–1000."""
    return "%04x%04x%04x" % (int(h) % 360, max(0, min(1000, int(s))), max(0, min(1000, int(v))))


def _smooth_step(state: dict) -> tuple[int, int, int]:
    """Free-running hue cycle at full saturation/brightness.

    Music-sync hook: replace the free-running hue here with values derived from
    live audio — e.g. map the dominant frequency band to hue and the beat
    envelope to v (brightness). Keep the same (h, s, v) return shape so the
    drive loop below is unchanged.
    """
    state["hue"] = (state.get("hue", 0) + HUE_STEP) % 360
    return state["hue"], 1000, 1000


def _strobe_step(state: dict) -> tuple[int, int, int]:
    """Sudden jumps to random saturated hues, brightness flicking off↔full."""
    state["flash"] = not state.get("flash", False)
    if state["flash"]:
        return random.randint(0, 359), 1000, 1000
    return state.get("hue", 0), 1000, 30


def _loop(device: str, mode: str):
    step_fn = _strobe_step if mode == "strobe" else _smooth_step
    interval = STROBE_INTERVAL if mode == "strobe" else INTERVAL
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
        state = {}
        while _running.is_set():
            h, s, v = step_fn(state)
            state["hue"] = h
            try:
                dev.set_value(24, _hsv_hex(h, s, v))
            except Exception:
                pass
            time.sleep(interval)
    finally:
        _running.clear()


def start(device: str = "ceiling", mode: str = "smooth") -> bool:
    """Begin cycling in the given mode ("smooth" or "strobe").

    Returns False if already running in the same mode. If a different mode is
    requested while running, the current loop is stopped and the new one starts.
    """
    global _thread, _mode
    if _running.is_set():
        if mode == _mode:
            return False
        stop()
        if _thread is not None:
            _thread.join(timeout=1)
    _mode = mode
    _running.set()
    _thread = threading.Thread(target=_loop, args=(device, mode), daemon=True)
    _thread.start()
    return True


def stop():
    _running.clear()


def is_active() -> bool:
    return _running.is_set()


def active_mode() -> str | None:
    return _mode if _running.is_set() else None
