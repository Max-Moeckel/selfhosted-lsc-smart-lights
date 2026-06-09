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
STEP_SECONDS = 15


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
        total = max(1, duration_min) * 60
        try:
            dev.turn_on()
            dev.set_mode("white")
        except Exception:
            pass
        start = time.time()
        while True:
            frac = min(1.0, (time.time() - start) / total)
            bright = max(1, round(frac * 100))
            temp = round(frac * end_temp)
            try:
                dev.set_value(23, temp * 10)
                dev.set_value(22, max(10, round(bright / 100 * 990 + 10)))
            except Exception:
                pass
            if frac >= 1.0:
                break
            time.sleep(STEP_SECONDS)
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
