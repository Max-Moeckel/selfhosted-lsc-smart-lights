"""Shared local-LAN control logic for LSC smart lights (used by CLI and web app)."""

import json
import os
from pathlib import Path

import tinytuya

CONFIG_PATH = Path(os.environ.get("LSC_CONFIG", Path(__file__).parent / "config" / "devices.json"))


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    with CONFIG_PATH.open() as f:
        return json.load(f)


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


def parse_status(dps: dict | None) -> dict:
    """Normalise raw DPS into {online, on, bright, temp} with bright/temp as 0-100."""
    if dps is None:
        return {"online": False, "on": None, "bright": None, "temp": None}
    on = _find(dps, 20)
    bright_raw = _find(dps, 22)
    temp_raw = _find(dps, 23)
    return {
        "online": True,
        "on": bool(on) if on is not None else None,
        "bright": round((bright_raw - 10) / 990 * 100) if bright_raw is not None else None,
        "temp": round(temp_raw / 10) if temp_raw is not None else None,
    }


def set_power(dev: tinytuya.BulbDevice, on: bool):
    dev.turn_on() if on else dev.turn_off()


def set_bright(dev: tinytuya.BulbDevice, pct: int):
    raw = max(10, round(pct / 100 * 990 + 10))
    dev.set_value(22, raw)


def set_temp(dev: tinytuya.BulbDevice, pct: int):
    dev.set_value(23, round(pct * 10))
