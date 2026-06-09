"""Simple web UI to control LSC smart lights over LAN. Deployable via Docker."""

import threading

from flask import Flask, jsonify, request, render_template

import lamp
import party
import wakeup

app = Flask(__name__)
wakeup.start()


def _device(name):
    cfg = lamp.load_config()
    if name not in cfg:
        return None, None
    return cfg[name], lamp.make_device(cfg[name])


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/profiles")
def profiles():
    return jsonify({k: v["label"] for k, v in lamp.PROFILES.items()})


@app.get("/api/devices")
def devices():
    # names only, straight from config — no LAN round-trip, so the UI can render
    # the lamp cards immediately instead of waiting on the slow status query
    return jsonify(list(lamp.load_config().keys()))


@app.get("/api/status")
def status():
    cfg = lamp.load_config()
    out = {}
    for name, dcfg in cfg.items():
        dev = lamp.make_device(dcfg)
        st = lamp.parse_status(lamp.get_dps(dev))
        st["profile"] = lamp.match_profile(st)
        out[name] = st
    return jsonify(out)


@app.post("/api/<name>/power")
def power(name):
    _, dev = _device(name)
    if dev is None:
        return jsonify({"error": "unknown device"}), 404
    wakeup.cancel()
    try:
        lamp.set_power(dev, bool(request.json.get("on")))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.post("/api/<name>/bright")
def bright(name):
    _, dev = _device(name)
    if dev is None:
        return jsonify({"error": "unknown device"}), 404
    val = max(1, min(100, int(request.json.get("value", 50))))
    wakeup.cancel()
    try:
        lamp.set_bright(dev, val)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.post("/api/<name>/temp")
def temp(name):
    _, dev = _device(name)
    if dev is None:
        return jsonify({"error": "unknown device"}), 404
    val = max(0, min(100, int(request.json.get("value", 50))))
    wakeup.cancel()
    try:
        lamp.set_temp(dev, val)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.post("/api/<name>/colour")
def colour(name):
    _, dev = _device(name)
    if dev is None:
        return jsonify({"error": "unknown device"}), 404
    hexval = (request.json.get("hex") or "").lstrip("#")
    if len(hexval) != 6:
        return jsonify({"error": "invalid colour"}), 400
    wakeup.cancel()
    try:
        r, g, b = (int(hexval[i:i + 2], 16) for i in (0, 2, 4))
        lamp.set_colour(dev, r, g, b)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/wakeup")
def wakeup_get():
    return jsonify(wakeup.load())


@app.post("/api/wakeup")
def wakeup_set():
    return jsonify(wakeup.save(request.json or {}))


@app.post("/api/wakeup/test")
def wakeup_test():
    cfg = wakeup.load()
    # short 30-second preview so you don't wait the full duration
    threading.Thread(
        target=wakeup.run_sunrise,
        args=(cfg["device"], 0.5),
        daemon=True,
    ).start()
    return jsonify({"ok": True})


@app.get("/api/party")
def party_get():
    return jsonify({"active": party.is_active(), "mode": party.active_mode(),
                    "bpm": party.current_bpm()})


@app.post("/api/party")
def party_set():
    body = request.json or {}
    if body.get("on"):
        wakeup.cancel()
        device = body.get("device") or wakeup.load().get("device", "ceiling")
        party.start(device, body.get("mode", "smooth"), int(body.get("bpm", 0) or 0))
    else:
        party.stop()
    return jsonify({"active": party.is_active(), "mode": party.active_mode(),
                    "bpm": party.current_bpm()})


@app.post("/api/party/sync")
def party_sync():
    # high-rate (~5 Hz) live colour feed from the browser's mic analysis;
    # consumed by the party metronome, so keep it cheap
    body = request.json or {}
    party.set_sync(int(body.get("hue", 0)), int(body.get("v", 1000)))
    return jsonify({"ok": True})


@app.post("/api/<name>/profile")
def profile(name):
    _, dev = _device(name)
    if dev is None:
        return jsonify({"error": "unknown device"}), 404
    key = request.json.get("key")
    if key not in lamp.PROFILES:
        return jsonify({"error": "unknown profile"}), 400
    wakeup.cancel()
    try:
        lamp.apply_profile(dev, key)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
