"""Shared local-LAN control logic for LSC smart lights (used by CLI and web app)."""

import json
import os
from pathlib import Path

import tinytuya

CONFIG_PATH = Path(os.environ.get("LSC_CONFIG", Path(__file__).parent / "config" / "devices.json"))


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    raw = CONFIG_PATH.read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return json.loads(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {CONFIG_PATH} as UTF-8/CP1252/Latin-1")


def make_device(cfg: dict) -> tinytuya.BulbDevice:
    dev = tinytuya.BulbDevice(
        dev_id=cfg["id"],
        address=cfg["ip"],
        local_key=cfg["key"],
        version=float(cfg["version"]),
    )
    dev.set_socketTimeout(3)
    dev.set_socketRetryLimit(1)
    return dev


def get_dps(dev: tinytuya.BulbDevice) -> dict | None:
    """Raw DPS dict, or None if the device is offline/unreachable."""
    try:
        data = dev.status()
        if "Error" in data:
            return None
        return data.get("dps", {})
    except Exception:
        return None


def _find(dps: dict, *keys):
    for k in keys:
        if str(k) in dps:
            return dps[str(k)]
    return None


def _colour_hex_to_rgb(hexval: str) -> str | None:
    """Tuya colour_data_v2 (HHHHSSSSVVVV hex) → #rrggbb."""
    if not hexval or len(hexval) < 12:
        return None
    try:
        h = int(hexval[0:4], 16)
        s = int(hexval[4:8], 16) / 1000
        v = int(hexval[8:12], 16) / 1000
    except ValueError:
        return None
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h / 360, s, v)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def parse_status(dps: dict | None) -> dict:
    """Normalise raw DPS into {online, on, bright, temp, mode, supports_colour, colour}."""
    if dps is None:
        return {"online": False, "on": None, "bright": None, "temp": None,
                "mode": None, "supports_colour": False, "colour": None}
    on = _find(dps, 20)
    bright_raw = _find(dps, 22)
    temp_raw = _find(dps, 23)
    colour_raw = _find(dps, 24)
    return {
        "online": True,
        "on": bool(on) if on is not None else None,
        "bright": round((bright_raw - 10) / 990 * 100) if bright_raw is not None else None,
        "temp": round(temp_raw / 10) if temp_raw is not None else None,
        "mode": _find(dps, 21),
        "supports_colour": "24" in dps,
        "colour": _colour_hex_to_rgb(colour_raw) if colour_raw else None,
    }


def set_power(dev: tinytuya.BulbDevice, on: bool):
    dev.turn_on() if on else dev.turn_off()


def set_bright(dev: tinytuya.BulbDevice, pct: int):
    raw = max(10, round(pct / 100 * 990 + 10))
    dev.set_value(22, raw)


def set_temp(dev: tinytuya.BulbDevice, pct: int):
    # ensure white mode so colour temp is visible, then set it
    dev.set_mode("white")
    dev.set_value(23, round(pct * 10))


def set_colour(dev: tinytuya.BulbDevice, r: int, g: int, b: int):
    dev.set_colour(r, g, b)


# Named scenes. White profiles use temp (0=warm…100=cool) + bright (0-100).
# A "colour" [r,g,b] makes it a colour scene; temp/bright act as CCT fallback
# for devices without colour support (the CCT bulb).
PROFILES = {
    "working": {"label": "Arbeiten", "temp": 100, "bright": 100},
    "reading": {"label": "Lesen", "temp": 65, "bright": 90},
    "relax":   {"label": "Entspannen", "temp": 15, "bright": 55},
    "night":   {"label": "Nacht", "colour": [255, 0, 0], "temp": 0, "bright": 8},
}


def apply_profile(dev: tinytuya.BulbDevice, key: str):
    p = PROFILES[key]
    dev.turn_on()
    if "colour" in p:
        try:
            dev.set_colour(*p["colour"])
            return
        except Exception:
            pass  # CCT-only device → fall through to the white fallback
    dev.set_mode("white")
    dev.set_value(23, round(p["temp"] * 10))
    dev.set_value(22, max(10, round(p["bright"] / 100 * 990 + 10)))
