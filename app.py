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
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lichtsteuerung</title>
  <style>
    :root { color-scheme: dark; }
    body { font-family: system-ui, sans-serif; background:#15171c; color:#e8e8e8;
           margin:0; padding:1.5rem; }
    h1 { font-size:1.3rem; font-weight:600; margin:0 0 1rem; }
    .card { background:#1f2229; border:1px solid #2c2f38; border-radius:14px;
            padding:1.1rem 1.2rem; margin-bottom:1rem; }
    .row { display:flex; align-items:center; justify-content:space-between; gap:1rem; }
    .name { font-size:1.05rem; font-weight:600; }
    .state { font-size:.8rem; padding:.15rem .55rem; border-radius:99px; }
    .on  { background:#2e5d34; color:#bff5c4; }
    .off { background:#3a3d44; color:#b9bdc7; }
    .offline { background:#5d2e2e; color:#f5bfbf; }
    button { background:#2c2f38; color:#e8e8e8; border:1px solid #3a3d44;
             border-radius:9px; padding:.5rem .9rem; font-size:.9rem; cursor:pointer; }
    button:hover { background:#363a44; }
    button.power { min-width:64px; }
    label { display:block; font-size:.78rem; color:#9aa0ac; margin:.9rem 0 .25rem; }
    input[type=range] { width:100%; accent-color:#5b8cff; }
    .ctl { margin-top:.4rem; }
    .muted { opacity:.4; pointer-events:none; }
    .colourrow { display:flex; align-items:center; gap:.6rem; margin-top:.4rem; }
    input[type=color] { width:46px; height:34px; border:none; background:none;
                        border-radius:8px; cursor:pointer; padding:0; }
    .swatches { display:flex; gap:.35rem; flex-wrap:wrap; }
    .sw { width:26px; height:26px; border-radius:6px; border:1px solid #00000040;
          padding:0; cursor:pointer; }
    .profiles { display:flex; gap:.4rem; flex-wrap:wrap; margin-top:.7rem; }
    .prof { font-size:.82rem; padding:.4rem .7rem; }
    .wu-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
               gap:.6rem 1rem; margin-top:.5rem; }
    .wu-grid input, .wu-grid select { width:100%; box-sizing:border-box;
       background:#15171c; color:#e8e8e8; border:1px solid #3a3d44;
       border-radius:8px; padding:.4rem; }
    .switch { font-size:.85rem; color:#9aa0ac; display:flex; align-items:center; gap:.4rem; }
    .days { display:flex; gap:.35rem; flex-wrap:wrap; margin-top:.3rem; }
    .day { width:38px; padding:.35rem 0; text-align:center; font-size:.8rem; }
    .day.on { background:#2e4d7d; border-color:#3f63a0; color:#dbe6ff; }
  </style>
</head>
<body>
  <h1>Lichtsteuerung</h1>
  <div class="card" id="wakeup">
    <div class="row">
      <span class="name">Wake-up Light</span>
      <label class="switch"><input type="checkbox" id="wu-enabled"> aktiv</label>
    </div>
    <div class="wu-grid">
      <div><label>Startzeit</label><input type="time" id="wu-time"></div>
      <div><label>Dauer: <span id="wu-durl">30</span> min</label>
        <input type="range" id="wu-dur" min="10" max="60" step="5" value="30"
          oninput="document.getElementById('wu-durl').textContent=this.value"></div>
      <div><label>Lampe</label><select id="wu-device"></select></div>
    </div>
    <label>Wochentage</label>
    <div class="days" id="wu-days"></div>
    <div class="row" style="margin-top:.9rem">
      <button onclick="saveWakeup()">Speichern</button>
      <button onclick="testWakeup()">30-Sek-Test</button>
    </div>
  </div>
  <div id="lamps"></div>
  <script>
    let PROFILES = {};
    let partyActive = false;
    async function api(path, opts) {
      const r = await fetch(path, opts);
      return r.json();
    }
    function card(name, s) {
      const off = !s.online;
      const stateCls = off ? 'offline' : (s.on ? 'on' : 'off');
      const stateTxt = off ? 'offline' : (s.on ? 'an' : 'aus');
      const dim = off ? 'muted' : '';
      return `
      <div class="card">
        <div class="row">
          <span class="name">${name}</span>
          <span class="state ${stateCls}">${stateTxt}</span>
        </div>
        <div class="row ctl ${dim}">
          <button class="power" onclick="power('${name}', ${s.on ? 'false':'true'})">
            ${s.on ? 'Aus' : 'An'}
          </button>
        </div>
        <div class="profiles ${dim}">
          ${Object.entries(PROFILES).map(([k, lbl]) =>
            `<button class="prof" onclick="profile('${name}','${k}')">${lbl}</button>`).join('')}
          ${s.supports_colour ? `<button class="prof" onclick="toggleParty('${name}')"
            style="${partyActive ? 'background:#7d2e6b;border-color:#9c3a86;color:#ffd9f4' : ''}">
            ${partyActive ? 'Party aus' : 'Party'}</button>` : ''}
        </div>
        <div class="${dim}">
          <label>Helligkeit: <span id="bl-${name}">${s.bright ?? '-'}</span>%</label>
          <input type="range" min="1" max="100" value="${s.bright ?? 50}"
            class="ctl" oninput="document.getElementById('bl-${name}').textContent=this.value"
            onchange="setv('${name}','bright',this.value)">
          <label>Farbtemperatur (warm→kalt): <span id="tl-${name}">${s.temp ?? '-'}</span>%</label>
          <input type="range" min="0" max="100" value="${s.temp ?? 50}"
            class="ctl" oninput="document.getElementById('tl-${name}').textContent=this.value"
            onchange="setv('${name}','temp',this.value)">
          ${s.supports_colour ? `
          <label>Farbe</label>
          <div class="colourrow">
            <input type="color" value="${s.colour ?? '#ffffff'}"
              onchange="setcolour('${name}', this.value)">
            <span class="swatches">
              ${['#ff0000','#ff8000','#ffff00','#00ff00','#00ffff','#0000ff','#ff00ff','#ffffff']
                .map(c => `<button class="sw" style="background:${c}"
                          onclick="setcolour('${name}','${c}')"></button>`).join('')}
            </span>
          </div>` : ''}
        </div>
      </div>`;
    }
    async function refresh() {
      const [data, party] = await Promise.all([api('/api/status'), api('/api/party')]);
      partyActive = party.active;
      document.getElementById('lamps').innerHTML =
        Object.entries(data).map(([n, s]) => card(n, s)).join('');
    }
    async function power(name, on) {
      await api(`/api/${name}/power`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({on})});
      refresh();
    }
    async function setv(name, kind, val) {
      await api(`/api/${name}/${kind}`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({value:+val})});
    }
    async function setcolour(name, hex) {
      await api(`/api/${name}/colour`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({hex})});
    }
    async function profile(name, key) {
      await api(`/api/${name}/profile`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({key})});
      refresh();
    }
    const DAYNAMES = ['Mo','Di','Mi','Do','Fr','Sa','So'];
    let wuDays = [];
    function renderDays() {
      document.getElementById('wu-days').innerHTML = DAYNAMES.map((d,i) =>
        `<button class="day ${wuDays.includes(i)?'on':''}" onclick="toggleDay(${i})">${d}</button>`
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
    async function toggleParty(name) {
      const r = await api('/api/party', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({on: !partyActive, device: name})});
      partyActive = r.active;
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
    return jsonify({"active": party.is_active()})


@app.post("/api/party")
def party_set():
    body = request.json or {}
    if body.get("on"):
        device = body.get("device") or wakeup.load().get("device", "ceiling")
        party.start(device)
    else:
        party.stop()
    return jsonify({"active": party.is_active()})


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
