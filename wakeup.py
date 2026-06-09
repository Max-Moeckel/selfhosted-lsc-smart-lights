"""Wake-up light: simulate a sunrise (ramp brightness + colour temp) at a set time."""

import datetime
import json
import os
import threading
import time
from pathlib import Path

import lamp

WAKEUP_PATH = Path(os.environ.get("LSC_WAKEUP", Path(__file__).parent / "config" / "wakeup.json"))

DEFAULT = {
    "enabled": False,
    "time": "07:00",        # when the sunrise STARTS
    "duration_min": 30,     # ramp length, 10–60
    "device": "ceiling",
    "days": [0, 1, 2, 3, 4],  # 0=Mon … 6=Sun
    "end_temp": 50,         # colour temp reached at the end (0=warm … 100=cool)
}

_running = threading.Event()
# Brightness raw range is 10–1000 (990 steps). We pace the ramp so each tick
# nudges brightness by ~1 raw unit → imperceptible. MIN_INTERVAL keeps short
# test ramps from flooding the device with LAN calls.
MIN_INTERVAL = 0.5
BRIGHT_STEPS = 990

# Sunrise colour gradient (dim red → red → orange → amber), positions 0..1.
SUNRISE_PALETTE = [
    (0.0,  (30, 0, 0)),
    (0.35, (140, 25, 0)),
    (0.65, (220, 80, 12)),
    (1.0,  (255, 150, 45)),
]
COLOUR_PHASE = 0.7  # first 70% of the ramp is the colour gradient, then white


def _palette(t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    for (p0, c0), (p1, c1) in zip(SUNRISE_PALETTE, SUNRISE_PALETTE[1:]):
        if t <= p1:
            f = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return SUNRISE_PALETTE[-1][1]


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
    merged["end_temp"] = max(0, min(100, int(merged["end_temp"])))
    WAKEUP_PATH.write_text(json.dumps(merged, indent=2))
    return merged


def run_sunrise(device: str, duration_min: int, end_temp: int):
    """Blocking ramp; run in a thread. Ignores transient device errors."""
    if _running.is_set():
        return
    _running.set()
    try:
        cfg = lamp.load_config()
        if device not in cfg:
            return
        dev = lamp.make_device(cfg[device])
        total = max(10, round(duration_min * 60))
        try:
            dev.turn_on()
        except Exception:
            pass
        # colour gradient only on colour-capable devices (DPS 24); else warm-white ramp
        try:
            dps = dev.status().get("dps", {})
            supports_colour = "24" in dps
        except Exception:
            supports_colour = False

        step = max(MIN_INTERVAL, total / BRIGHT_STEPS)
        white_set = False
        last_braw = last_traw = None
        last_colour = None
        start = time.time()
        while True:
            frac = min(1.0, (time.time() - start) / total)
            if supports_colour and frac < COLOUR_PHASE:
                rgb = _palette(frac / COLOUR_PHASE)
                if rgb != last_colour:
                    try:
                        dev.set_colour(*rgb)
                    except Exception:
                        pass
                    last_colour = rgb
            else:
                if not white_set:
                    try:
                        dev.set_mode("white")
                    except Exception:
                        pass
                    white_set = True
                if supports_colour:
                    local = (frac - COLOUR_PHASE) / (1 - COLOUR_PHASE)
                    braw = max(10, round((0.7 + 0.3 * local) * 990 + 10))
                    traw = round(local * end_temp * 10)
                else:
                    braw = max(10, round(frac * 990 + 10))
                    traw = round(frac * end_temp * 10)
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
            if frac >= 1.0:
                break
            time.sleep(step)
    finally:
        _running.clear()


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
                args=(cfg["device"], cfg["duration_min"], cfg["end_temp"]),
                daemon=True,
            ).start()
        time.sleep(20)


def start():
    threading.Thread(target=_loop, daemon=True).start()
