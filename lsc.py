#!/usr/bin/env python3
"""CLI for local LAN control of LSC Smart lights via TinyTuya."""

import json
import sys
from pathlib import Path

import tinytuya

CONFIG_PATH = Path(__file__).parent / "config" / "devices.json"

USAGE = """\
Usage:
  lsc.py status
  lsc.py <ceiling|bulb> on|off
  lsc.py <ceiling|bulb> bright <0-100>
  lsc.py <ceiling|bulb> temp <0-100>
  lsc.py <ceiling|bulb> dps
"""


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"Config not found: {CONFIG_PATH}\n"
            "Run the wizard (see README) and create config/devices.json."
        )
    with CONFIG_PATH.open() as f:
        return json.load(f)


def make_device(name: str, cfg: dict) -> tinytuya.BulbDevice:
    dev = tinytuya.BulbDevice(
        dev_id=cfg["id"],
        address=cfg["ip"],
        local_key=cfg["key"],
        version=float(cfg["version"]),
    )
    dev.set_socketTimeout(3)
    dev.set_socketRetryLimit(1)
    return dev


def get_status(name: str, dev: tinytuya.BulbDevice) -> dict | None:
    """Return status dict or None if offline."""
    try:
        data = dev.status()
        if "Error" in data:
            return None
        return data.get("dps", {})
    except Exception:
        return None


def find_dps(dps: dict, *keys: str):
    """Return value of first matching key (int or str) found in dps."""
    for k in keys:
        if k in dps:
            return dps[k]
        if str(k) in dps:
            return dps[str(k)]
    return None


def print_status(name: str, dps: dict | None) -> None:
    if dps is None:
        print(f"{name:8s}  OFFLINE")
        return
    on = find_dps(dps, "20", 20)
    bright_raw = find_dps(dps, "22", 22)
    temp_raw = find_dps(dps, "23", 23)

    on_str = ("ON" if on else "OFF") if on is not None else "?"
    # brightness: raw 10–1000 → 0–100 %
    bright_str = f"{round((bright_raw - 10) / 990 * 100)}%" if bright_raw is not None else "?"
    # colour temp: raw 0–1000 (0=warm, 1000=cool) → 0–100
    temp_str = f"{round(temp_raw / 10)}%" if temp_raw is not None else "?"

    print(f"{name:8s}  {on_str:3s}  bright={bright_str:5s}  temp={temp_str}")


# ── commands ────────────────────────────────────────────────────────────────

def cmd_status(cfg: dict) -> None:
    for name, dcfg in cfg.items():
        dev = make_device(name, dcfg)
        dps = get_status(name, dev)
        print_status(name, dps)


def cmd_on_off(name: str, dev: tinytuya.BulbDevice, state: bool) -> None:
    try:
        dev.turn_on() if state else dev.turn_off()
        print(f"{name}: {'ON' if state else 'OFF'}")
    except Exception as e:
        print(f"{name}: OFFLINE ({e})")


def cmd_bright(name: str, dev: tinytuya.BulbDevice, pct: int) -> None:
    # 0–100 % → raw 10–1000
    raw = max(10, round(pct / 100 * 990 + 10))
    try:
        dev.set_value(22, raw)
        print(f"{name}: brightness → {pct}%")
    except Exception as e:
        print(f"{name}: OFFLINE ({e})")


def cmd_temp(name: str, dev: tinytuya.BulbDevice, pct: int) -> None:
    # 0=warm, 100=cool → raw 0–1000
    raw = round(pct * 10)
    try:
        dev.set_value(23, raw)
        print(f"{name}: colour temp → {pct}% (cool)")
    except Exception as e:
        print(f"{name}: OFFLINE ({e})")


def cmd_dps(name: str, dev: tinytuya.BulbDevice) -> None:
    dps = get_status(name, dev)
    if dps is None:
        print(f"{name}: OFFLINE")
    else:
        print(f"{name} raw DPS:")
        for k, v in sorted(dps.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
            print(f"  {k}: {v}")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(USAGE)
        sys.exit(1)

    cfg = load_config()

    if args[0] == "status":
        cmd_status(cfg)
        return

    name = args[0]
    if name not in cfg:
        sys.exit(f"Unknown device '{name}'. Known: {', '.join(cfg)}")

    dev = make_device(name, cfg[name])

    if len(args) < 2:
        print(USAGE)
        sys.exit(1)

    subcmd = args[1]

    if subcmd == "on":
        cmd_on_off(name, dev, True)
    elif subcmd == "off":
        cmd_on_off(name, dev, False)
    elif subcmd == "bright":
        if len(args) < 3:
            sys.exit("bright requires a value 0-100")
        pct = int(args[2])
        if not 0 <= pct <= 100:
            sys.exit("bright value must be 0-100")
        cmd_bright(name, dev, pct)
    elif subcmd == "temp":
        if len(args) < 3:
            sys.exit("temp requires a value 0-100")
        pct = int(args[2])
        if not 0 <= pct <= 100:
            sys.exit("temp value must be 0-100")
        cmd_temp(name, dev, pct)
    elif subcmd == "dps":
        cmd_dps(name, dev)
    else:
        print(USAGE)
        sys.exit(f"Unknown subcommand '{subcmd}'")


if __name__ == "__main__":
    main()
