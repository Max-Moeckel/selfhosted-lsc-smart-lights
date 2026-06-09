"""Simple web UI to control LSC smart lights over LAN. Deployable via Docker."""

from flask import Flask, jsonify, request, render_template_string

import lamp

app = Flask(__name__)

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
  </style>
</head>
<body>
  <h1>Lichtsteuerung</h1>
  <div id="lamps"></div>
  <script>
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
        <div class="${dim}">
          <label>Helligkeit: <span id="bl-${name}">${s.bright ?? '-'}</span>%</label>
          <input type="range" min="1" max="100" value="${s.bright ?? 50}"
            class="ctl" oninput="document.getElementById('bl-${name}').textContent=this.value"
            onchange="setv('${name}','bright',this.value)">
          <label>Farbtemperatur (warm→kalt): <span id="tl-${name}">${s.temp ?? '-'}</span>%</label>
          <input type="range" min="0" max="100" value="${s.temp ?? 50}"
            class="ctl" oninput="document.getElementById('tl-${name}').textContent=this.value"
            onchange="setv('${name}','temp',this.value)">
        </div>
      </div>`;
    }
    async function refresh() {
      const data = await api('/api/status');
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
    refresh();
    setInterval(refresh, 10000);
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
