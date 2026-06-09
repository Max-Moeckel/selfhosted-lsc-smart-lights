"""Wake-up light: simulate a sunrise (ramp brightness + colour temp) at a set time."""

import datetime
import json
import os
import threading
import time
from pathlib import Path

import lamp
import party

WAKEUP_PATH = Path(os.environ.get("LSC_WAKEUP", Path(__file__).parent / "config" / "wakeup.json"))

DEFAULT = {
    "enabled": False,
    "time": "07:00",        # when the sunrise STARTS
    "duration_min": 30,     # ramp length, 10–60
    "device": "ceiling",
    "days": [0, 1, 2, 3, 4],  # 0=Mon … 6=Sun
}

_running = threading.Event()
_abort = threading.Event()
# Colour-mode HSV (DPS 24) gives 0–1000 brightness resolution. We pace the ramp
# so brightness changes by ~1 unit per tick → imperceptible. MIN_INTERVAL keeps
# short test ramps from flooding the device with LAN calls.
MIN_INTERVAL = 0.3
BRIGHT_STEPS = 1000
# Fraction of the ramp spent in colour mode (red → near-white) before handing
# off to white-CCT mode. White-CCT is physically brighter than colour mode at
# the same numeric level, so the switch must happen while still dim — at this
# low brightness the mode luminance gap is imperceptible, then the long white
# phase does all the real brightening up to Arbeiten max.
SWITCH = 0.15
# Lowest *visible* level (out of 1000). These bulbs emit no perceptible light
# below ~3-4%, so starting the ramp at the raw minimum (~1%) looks like the lamp
# never turned on — especially when it was switched fully off beforehand. We floor
# the ramp here so the sunrise visibly begins, then climbs along the gamma curve.
FLOOR = 40


def _hsv_hex(h: int, s: int, v: int) -> str:
    """Tuya colour_data_v2 hex: H 0–360, S/V 0–1000."""
    return "%04x%04x%04x" % (int(h) % 360, max(0, min(1000, int(s))), max(0, min(1000, int(v))))


def load() -> dict:
    if not WAKEUP_PATH.exists():
        return dict(DEFAULT)
    try:
        data = json.loads(WAKEUP_PATH.read_bytes().decode("utf-8", "replace"))
    except (ValueError, OSError):
        return dict(DEFAULT)
    return {**DEFAULT, **data}


def save(cfg: dict) -> dict:
    merged = {**DEFAULT, **load(), **cfg}
    merged["duration_min"] = max(1, min(60, int(merged["duration_min"])))
    WAKEUP_PATH.write_text(json.dumps(merged, indent=2))
    return merged


def run_sunrise(device: str, duration_min: float):
    """Blocking HSV sunrise ramp for the colour ceiling light; run in a thread."""
    if _running.is_set():
        return
    _abort.clear()
    _running.set()
    try:
        # Sunrise takes priority: stop party mode (the only concurrently running
        # mode) and wait for its thread to release the lamp before we ramp, so
        # the two don't fight over DPS 24 / the colour↔white mode switch.
        party.stop()
        for _ in range(20):
            if not party.is_active():
                break
            time.sleep(0.1)
        cfg = lamp.load_config()
        if device not in cfg:
            return
        dev = lamp.make_device(cfg[device])
        total = max(10, round(duration_min * 60))
        try:
            dev.turn_on()
            dev.set_value(21, "colour")
        except Exception:
            pass
        step = max(MIN_INTERVAL, total / BRIGHT_STEPS)
        white_set = False
        last_hex = last_braw = last_traw = None
        start = time.time()
        while True:
            frac = min(1.0, (time.time() - start) / total)
            # gamma curve: stays very dim for most of the ramp, brightens late —
            # like a real sunrise, and avoids the "starts too bright" feel
            bright = frac ** 3
            if frac < SWITCH:
                # colour phase: red → warm orange, desaturating almost to white,
                # brightness following the global curve
                la = frac / SWITCH
                h = round(35 * la)
                s = round(1000 - 900 * la)        # → ~100, nearly white at the handoff
                v = round(FLOOR + (1000 - FLOOR) * bright)
                hexval = _hsv_hex(h, s, v)
                if hexval != last_hex:
                    try:
                        dev.set_value(24, hexval)
                    except Exception:
                        pass
                    last_hex = hexval
            else:
                # white CCT phase: brightness keeps the same curve up to full, colour
                # temp ramps warm → cool, ending exactly like the "Arbeiten" profile
                if not white_set:
                    try:
                        dev.set_value(21, "white")
                    except Exception:
                        pass
                    white_set = True
                lb = (frac - SWITCH) / (1 - SWITCH)
                braw = round(FLOOR + (1000 - FLOOR) * bright)
                traw = round(lb * 1000)
                if traw != last_traw:
                    try:
                        dev.set_value(23, traw)
                    except Exception:
                        pass
                    last_traw = traw
                if braw != last_braw:
                    try:
                        dev.set_value(22, braw)
                    except Exception:
                        pass
                    last_braw = braw
            if frac >= 1.0 or _abort.is_set():
                break
            time.sleep(step)
    finally:
        _running.clear()


def cancel():
    """Abort an in-progress sunrise (e.g. when the user picks a mode)."""
    _abort.set()


def is_active() -> bool:
    return _running.is_set()


def _loop():
    last_fired = None
    while True:
        cfg = load()
        now = datetime.datetime.now()
        if (
            cfg.get("enabled")
            and now.weekday() in cfg.get("days", [])
            and now.strftime("%H:%M") == cfg.get("time")
            and last_fired != now.date()
        ):
            last_fired = now.date()
            threading.Thread(
                target=run_sunrise,
                args=(cfg["device"], cfg["duration_min"]),
                daemon=True,
            ).start()
        time.sleep(20)


def start():
    threading.Thread(target=_loop, daemon=True).start()
