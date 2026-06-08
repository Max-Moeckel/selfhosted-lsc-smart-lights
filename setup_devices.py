#!/usr/bin/env python3
"""
Helper: reads tinytuya scan results + snapshot.json and writes config/devices.json.
Run after `python -m tinytuya wizard` and `python -m tinytuya scan`.
"""

import json
import sys
from pathlib import Path

SNAPSHOT = Path("snapshot.json")
OUT = Path("config/devices.json")

DEVICE_NAMES = {
    "ceiling": ["ceiling", "deckenleuchte", "lsc smart ceiling"],
    "bulb": ["bulb", "birne", "a65", "lsc a65"],
}


def match_name(label: str) -> str | None:
    label_l = label.lower()
    for name, keywords in DEVICE_NAMES.items():
        if any(k in label_l for k in keywords):
            return name
    return None


def main():
    if not SNAPSHOT.exists():
        sys.exit("snapshot.json not found — run `python -m tinytuya wizard` first.")

    with SNAPSHOT.open() as f:
        snap = json.load(f)

    devices = snap.get("devices", snap) if isinstance(snap, dict) else snap

    result = {}
    for dev in devices:
        name = match_name(dev.get("name", ""))
        if not name:
            # fallback: first unmatched device = ceiling, second = bulb
            for candidate in DEVICE_NAMES:
                if candidate not in result:
                    name = candidate
                    break
        if not name:
            continue
        result[name] = {
            "id": dev.get("id", ""),
            "ip": dev.get("ip", ""),
            "key": dev.get("key", ""),
            "version": str(dev.get("ver", dev.get("version", "3.3"))),
            "note": dev.get("name", ""),
        }

    if not result:
        sys.exit("No devices found in snapshot.json.")

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w") as f:
        json.dump(result, f, indent=2)
    print(f"Written {OUT}:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
