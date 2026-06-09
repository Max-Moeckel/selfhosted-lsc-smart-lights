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

function skeleton(name) {
  return `
  <div class="col-12 col-md-6">
  <div class="card bg-dark border-secondary h-100">
    <div class="card-body">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <span class="fw-semibold">${name}</span>
        <span class="badge text-bg-secondary">
          <span class="spinner-border spinner-border-sm" style="width:.8rem;height:.8rem"></span>
        </span>
      </div>
      <div class="placeholder-glow">
        <span class="placeholder col-3 mb-2"></span>
        <span class="placeholder col-12"></span>
        <span class="placeholder col-12"></span>
      </div>
    </div>
  </div>
  </div>`;
}

function renderSkeletons(names) {
  document.getElementById('lamps').innerHTML = names.map(skeleton).join('');
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
  const [profiles, names] = await Promise.all([api('/api/profiles'), api('/api/devices')]);
  PROFILES = profiles;
  renderSkeletons(names);          // show lamp cards immediately
  loadWakeup(names);               // populate the wake-up panel in parallel
  refresh();                       // fill in live status when it arrives
  setInterval(refresh, 10000);
})();
