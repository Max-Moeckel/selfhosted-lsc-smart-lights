"""Simple web UI to control LSC smart lights over LAN. Deployable via Docker."""

import threading

from flask import Flask, jsonify, request, render_template_string

import lamp
import party
import wakeup

app = Flask(__name__)
wakeup.start()

PAGE = """\
<!doctype html>
<html lang="de" data-bs-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lichtsteuerung</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
        rel="stylesheet"
        integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH"
        crossorigin="anonymous">
  <style>
    body { background:#15171c; }
    .container { max-width: 960px; }
    input[type=range] { accent-color:#5b8cff; }
    input[type=color] { width:46px; height:38px; padding:0; }
    .swatches { display:flex; gap:.35rem; flex-wrap:wrap; }
    .sw { width:30px; height:30px; border-radius:6px; border:1px solid #00000040;
          padding:0; cursor:pointer; }
    .day { min-width:42px; }
  </style>
</head>
<body class="text-light">
  <div class="container py-3">
    <h1 class="h4 fw-semibold mb-3">Lichtsteuerung</h1>
    <div id="lamps" class="row g-3"></div>

    <div class="card bg-dark border-secondary mt-4" id="wakeup">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-3">
          <h2 class="h6 mb-0">Wake-up Light</h2>
          <div class="form-check form-switch m-0">
            <input class="form-check-input" type="checkbox" id="wu-enabled">
            <label class="form-check-label small" for="wu-enabled">aktiv</label>
          </div>
        </div>
        <div class="row g-3">
          <div class="col-12 col-sm-4">
            <label class="form-label small">Startzeit</label>
            <input type="time" class="form-control" id="wu-time">
          </div>
          <div class="col-12 col-sm-4">
            <label class="form-label small">Dauer: <span id="wu-durl">30</span> min</label>
            <input type="range" class="form-range" id="wu-dur" min="10" max="60" step="5" value="30"
              oninput="document.getElementById('wu-durl').textContent=this.value">
          </div>
          <div class="col-12 col-sm-4">
            <label class="form-label small">Lampe</label>
            <select class="form-select" id="wu-device"></select>
          </div>
        </div>
        <label class="form-label small mt-3">Wochentage</label>
        <div class="d-flex flex-wrap gap-1" id="wu-days"></div>
        <div class="d-flex gap-2 mt-3">
          <button class="btn btn-primary btn-sm" onclick="saveWakeup()">Speichern</button>
          <button class="btn btn-outline-light btn-sm" onclick="testWakeup()">30-Sek-Test</button>
        </div>
      </div>
    </div>
  </div>
  <script>
    let PROFILES = {};
    let partyActive = false;
    let partyMode = null;  // "smooth" | "strobe" | null
    let selected = {};  // device name -> currently chosen profile key
    async function api(path, opts) {
      const r = await fetch(path, opts);
      return r.json();
    }
    function card(name, s) {
      const off = !s.online;
      const stateCls = off ? 'text-bg-danger' : (s.on ? 'text-bg-success' : 'text-bg-secondary');
      const stateTxt = off ? 'offline' : (s.on ? 'an' : 'aus');
      const dim = off ? 'opacity-50 pe-none' : '';
      const psel = (on) => on ? 'btn-primary' : 'btn-outline-light';
      return `
      <div class="col-12 col-md-6">
      <div class="card bg-dark border-secondary h-100">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-semibold">${name}</span>
            <span class="badge ${stateCls}">${stateTxt}</span>
          </div>
          <div class="${dim}">
            <button class="btn btn-sm ${s.on ? 'btn-secondary' : 'btn-success'} mb-2"
              style="min-width:64px" onclick="power('${name}', ${s.on ? 'false':'true'})">
              ${s.on ? 'Aus' : 'An'}
            </button>
            <div class="d-flex flex-wrap gap-1 mb-3">
              ${Object.entries(PROFILES).map(([k, lbl]) =>
                `<button class="btn btn-sm ${psel(!partyActive && selected[name]===k)}"
                  onclick="profile('${name}','${k}')">${lbl}</button>`).join('')}
              ${s.supports_colour ? `
              <button class="btn btn-sm ${psel(partyMode==='smooth')}"
                onclick="toggleParty('${name}','smooth')">Party</button>
              <button class="btn btn-sm ${psel(partyMode==='strobe')}"
                onclick="toggleParty('${name}','strobe')">Strobo</button>` : ''}
            </div>
            <label class="form-label small mb-1">Helligkeit: <span id="bl-${name}">${s.bright ?? '-'}</span>%</label>
            <input type="range" class="form-range" min="1" max="100" value="${s.bright ?? 50}"
              oninput="document.getElementById('bl-${name}').textContent=this.value"
              onchange="setv('${name}','bright',this.value)">
            <label class="form-label small mb-1">Farbtemperatur (warm→kalt): <span id="tl-${name}">${s.temp ?? '-'}</span>%</label>
            <input type="range" class="form-range" min="0" max="100" value="${s.temp ?? 50}"
              oninput="document.getElementById('tl-${name}').textContent=this.value"
              onchange="setv('${name}','temp',this.value)">
            ${s.supports_colour ? `
            <label class="form-label small mb-1">Farbe</label>
            <div class="d-flex align-items-center gap-2 flex-wrap">
              <input type="color" class="form-control form-control-color" value="${s.colour ?? '#ffffff'}"
                onchange="setcolour('${name}', this.value)">
              <span class="swatches">
                ${['#ff0000','#ff8000','#ffff00','#00ff00','#00ffff','#0000ff','#ff00ff','#ffffff']
                  .map(c => `<button class="sw" style="background:${c}"
                            onclick="setcolour('${name}','${c}')"></button>`).join('')}
              </span>
            </div>` : ''}
          </div>
        </div>
      </div>
      </div>`;
    }
    async function refresh() {
      const [data, party] = await Promise.all([api('/api/status'), api('/api/party')]);
      partyActive = party.active;
      partyMode = party.mode;
      document.getElementById('lamps').innerHTML =
        Object.entries(data).map(([n, s]) => card(n, s)).join('');
    }
    async function power(name, on) {
      await api(`/api/${name}/power`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({on})});
      refresh();
    }
    async function setv(name, kind, val) {
      selected[name] = null;
      await api(`/api/${name}/${kind}`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({value:+val})});
    }
    async function setcolour(name, hex) {
      selected[name] = null;
      await api(`/api/${name}/colour`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({hex})});
    }
    async function profile(name, key) {
      if (partyActive) {
        await api('/api/party', {method:'POST',
          headers:{'Content-Type':'application/json'}, body:JSON.stringify({on:false})});
        partyActive = false;
        partyMode = null;
      }
      await api(`/api/${name}/profile`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({key})});
      selected[name] = key;
      refresh();
    }
    const DAYNAMES = ['Mo','Di','Mi','Do','Fr','Sa','So'];
    let wuDays = [];
    function renderDays() {
      document.getElementById('wu-days').innerHTML = DAYNAMES.map((d,i) =>
        `<button class="btn btn-sm day ${wuDays.includes(i)?'btn-primary':'btn-outline-light'}"
          onclick="toggleDay(${i})">${d}</button>`
      ).join('');
    }
    function toggleDay(i) {
      wuDays = wuDays.includes(i) ? wuDays.filter(x=>x!==i) : [...wuDays, i].sort();
      renderDays();
    }
    async function loadWakeup(deviceNames) {
      const w = await api('/api/wakeup');
      document.getElementById('wu-enabled').checked = w.enabled;
      document.getElementById('wu-time').value = w.time;
      document.getElementById('wu-dur').value = w.duration_min;
      document.getElementById('wu-durl').textContent = w.duration_min;
      document.getElementById('wu-device').innerHTML =
        deviceNames.map(n => `<option ${n===w.device?'selected':''}>${n}</option>`).join('');
      wuDays = w.days || [];
      renderDays();
    }
    async function saveWakeup() {
      await api('/api/wakeup', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          enabled: document.getElementById('wu-enabled').checked,
          time: document.getElementById('wu-time').value,
          duration_min: +document.getElementById('wu-dur').value,
          device: document.getElementById('wu-device').value,
          days: wuDays,
        })});
      alert('Wake-up gespeichert');
    }
    async function testWakeup() {
      await saveWakeup();
      await api('/api/wakeup/test', {method:'POST'});
    }
    async function toggleParty(name, mode) {
      // clicking the active mode turns it off; a different mode switches to it
      const turnOn = !(partyActive && partyMode === mode);
      const r = await api('/api/party', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({on: turnOn, device: name, mode})});
      partyActive = r.active;
      partyMode = r.mode;
      if (partyActive) selected[name] = null;
      refresh();
    }
    (async () => {
      PROFILES = await api('/api/profiles');
      const st = await api('/api/status');
      await loadWakeup(Object.keys(st));
      refresh();
      setInterval(refresh, 10000);
    })();
  </script>
</body>
</html>
"""


def _device(name):
    cfg = lamp.load_config()
    if name not in cfg:
        return None, None
    return cfg[name], lamp.make_device(cfg[name])


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.get("/api/profiles")
def profiles():
    return jsonify({k: v["label"] for k, v in lamp.PROFILES.items()})


@app.get("/api/status")
def status():
    cfg = lamp.load_config()
    out = {}
    for name, dcfg in cfg.items():
        dev = lamp.make_device(dcfg)
        out[name] = lamp.parse_status(lamp.get_dps(dev))
    return jsonify(out)


@app.post("/api/<name>/power")
def power(name):
    _, dev = _device(name)
    if dev is None:
        return jsonify({"error": "unknown device"}), 404
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
    return jsonify({"active": party.is_active(), "mode": party.active_mode()})


@app.post("/api/party")
def party_set():
    body = request.json or {}
    if body.get("on"):
        device = body.get("device") or wakeup.load().get("device", "ceiling")
        party.start(device, body.get("mode", "smooth"))
    else:
        party.stop()
    return jsonify({"active": party.is_active(), "mode": party.active_mode()})


@app.post("/api/<name>/profile")
def profile(name):
    _, dev = _device(name)
    if dev is None:
        return jsonify({"error": "unknown device"}), 404
    key = request.json.get("key")
    if key not in lamp.PROFILES:
        return jsonify({"error": "unknown profile"}), 400
    try:
        lamp.apply_profile(dev, key)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081)
