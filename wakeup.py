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
}

_running = threading.Event()
# Colour-mode HSV (DPS 24) gives 0–1000 brightness resolution. We pace the ramp
# so brightness changes by ~1 unit per tick → imperceptible. MIN_INTERVAL keeps
# short test ramps from flooding the device with LAN calls.
MIN_INTERVAL = 0.3
BRIGHT_STEPS = 1000


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
    _running.set()
    try:
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
        last_hex = None
        start = time.time()
        while True:
            frac = min(1.0, (time.time() - start) / total)
            # smoothstep: eases in at the start and out at the end (no abrupt finish)
            ease = frac * frac * (3 - 2 * frac)
            # one continuous HSV curve: deep red → warm orange, desaturating toward
            # warm white, brightness rising the whole way (single mode, no switch)
            h = round(35 * frac)              # 0° red → 35° warm orange
            s = round(1000 - 700 * frac)      # 1000 saturated → 300 pale/warm
            v = round(10 + 990 * ease)
            hexval = _hsv_hex(h, s, v)
            if hexval != last_hex:
                try:
                    dev.set_value(24, hexval)
                except Exception:
                    pass
                last_hex = hexval
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
                args=(cfg["device"], cfg["duration_min"]),
                daemon=True,
            ).start()
        time.sleep(20)


def start():
    threading.Thread(target=_loop, daemon=True).start()
