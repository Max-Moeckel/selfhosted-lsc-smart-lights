"""Party mode: rapidly cycle the colour ceiling light through the hue wheel.

Runs as a background thread so the web UI can toggle it on/off. Only the
colour-capable device is driven (the CCT bulb has no hue). The "music" mode is
a server-timed metronome pulsing the lamp on every beat at the current BPM. The
BPM is set either manually or from the browser's live mic tempo detection, which
POSTs the detected BPM; the server keeps that tempo until a new one is reported.
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
# Music: each beat jumps a chunk around the wheel and alternates brightness so
# the hit is clearly visible. The lamp can't strobe per-audio-sample over LAN,
# so we react at beat granularity (max ~ a few Hz).
BEAT_HUE_STEP = 67

_running = threading.Event()
_thread = None
_mode = "smooth"
_bpm = 0                     # >0 = server-timed tempo; 0 = external (mic) beats
_beat = threading.Event()    # set per beat (mic trigger) or to wake the tempo loop
# Live mic-derived colour, reported ~5 Hz by the browser: hue from the spectral
# centroid, V (brightness) from the band intensity. The metronome consumes these
# on each beat; a stale timestamp (>1 s) means no mic, so we fall back to the
# free-advancing rainbow.
_sync_hue = 0
_sync_v = 1000
_sync_ts = 0.0


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


def _emit_beat(dev, state: dict):
    """One visible pulse. With live mic sync, hue follows the spectral centroid and
    the pulse brightness follows the reported band intensity; without it, fall back
    to a free-advancing hue at full brightness. Either way the on/off-beat brightness
    alternates so the hit stays visible."""
    if time.time() - _sync_ts < 1.0:
        h, v_base = _sync_hue, _sync_v
    else:
        state["hue"] = (state.get("hue", 0) + BEAT_HUE_STEP) % 360
        h, v_base = state["hue"], 1000
    state["flash"] = not state.get("flash", False)
    v = v_base if state["flash"] else round(v_base * 0.65)
    try:
        dev.set_value(24, _hsv_hex(h, 1000, v))
    except Exception:
        pass


def _music_loop(device: str):
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
            bpm = _bpm
            if bpm > 0:
                # server-timed metronome; wait acts as an interruptible sleep so a
                # tempo change (set_bpm sets _beat) re-reads bpm on the next loop
                _emit_beat(dev, state)
                _beat.wait(timeout=max(0.05, 60.0 / bpm))
                _beat.clear()
            else:
                # no tempo reported yet (mic still warming up): hold until set_bpm wakes us
                _beat.wait(timeout=0.5)
                _beat.clear()
    finally:
        _running.clear()


def set_bpm(bpm: int):
    """Set the server-timed tempo (0 = follow external mic beats)."""
    global _bpm
    _bpm = max(0, min(300, int(bpm)))
    _beat.set()  # wake the loop so the new tempo takes effect at once


def set_sync(hue: int, v: int):
    """Store the latest mic-derived colour (hue 0–360) and brightness (V 0–1000).
    Reported continuously by the browser; the metronome's _emit_beat reads them."""
    global _sync_hue, _sync_v, _sync_ts
    _sync_hue = int(hue) % 360
    _sync_v = max(0, min(1000, int(v)))
    _sync_ts = time.time()


def current_bpm() -> int:
    return _bpm if _running.is_set() and _mode == "music" else 0


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


def start(device: str = "ceiling", mode: str = "smooth", bpm: int = 0) -> bool:
    """Begin cycling in the given mode ("smooth", "strobe" or "music").

    Returns False if already running in the same mode. If a different mode is
    requested while running, the current loop is stopped and the new one starts.
    For "music", re-calling while already in music mode just updates the tempo
    (no restart), so the browser's mic stream isn't interrupted.
    """
    global _thread, _mode, _bpm
    if _running.is_set():
        if mode == _mode:
            if mode == "music":
                set_bpm(bpm)
            return False
        stop()
        if _thread is not None:
            _thread.join(timeout=1)
    _mode = mode
    _bpm = max(0, min(300, int(bpm))) if mode == "music" else 0
    _beat.clear()
    _running.set()
    if mode == "music":
        _thread = threading.Thread(target=_music_loop, args=(device,), daemon=True)
    else:
        _thread = threading.Thread(target=_loop, args=(device, mode), daemon=True)
    _thread.start()
    return True


def stop():
    _running.clear()
    _beat.set()  # wake the music loop out of its wait so it exits promptly


def is_active() -> bool:
    return _running.is_set()


def active_mode() -> str | None:
    return _mode if _running.is_set() else None
