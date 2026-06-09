let PROFILES = {};
let partyActive = false;
let partyMode = null;  // "smooth" | "strobe" | null
let selected = {};  // device name -> currently chosen profile key
let deviceNames = [];
let statusByName = {};  // last known status per device, for instant re-renders

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}

// status used before the first /api/status returns: controls are shown and
// clickable, only the colour/party widgets (which need device capabilities)
// wait for real status.
function pendingStatus() {
  return {online: true, on: false, bright: null, temp: null,
          mode: null, supports_colour: false, colour: null, pending: true};
}

function card(name, s) {
  const off = !s.online;
  const pending = !!s.pending;
  const stateCls = off ? 'text-bg-danger' : (s.on ? 'text-bg-success' : 'text-bg-secondary');
  const stateTxt = off ? 'offline' : (s.on ? 'an' : 'aus');
  const badge = pending
    ? `<span class="badge text-bg-secondary">
         <span class="spinner-border spinner-border-sm" style="width:.8rem;height:.8rem"></span>
       </span>`
    : `<span class="badge ${stateCls}">${stateTxt}</span>`;
  const dim = off ? 'opacity-50 pe-none' : '';
  const psel = (on) => on ? 'btn-primary' : 'btn-outline-light';
  return `
  <div class="col-12 col-md-6">
  <div class="card bg-dark border-secondary h-100">
    <div class="card-body">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <span class="fw-semibold">${name}</span>
        ${badge}
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

// Render from cached status (no network) so optimistic UI changes show instantly.
function renderCards() {
  const names = deviceNames.length ? deviceNames : Object.keys(statusByName);
  document.getElementById('lamps').innerHTML =
    names.map(n => card(n, statusByName[n] || pendingStatus())).join('');
}

function renderPending(names) {
  deviceNames = names;
  renderCards();
}

async function refresh() {
  const [data, party] = await Promise.all([api('/api/status'), api('/api/party')]);
  partyActive = party.active;
  partyMode = party.mode;
  statusByName = data;
  renderCards();
}

async function power(name, on) {
  if (statusByName[name]) statusByName[name].on = on;  // optimistic
  renderCards();
  await api(`/api/${name}/power`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({on})});
  refresh();
}

async function setv(name, kind, val) {
  selected[name] = null;
  if (statusByName[name]) statusByName[name][kind] = +val;
  await api(`/api/${name}/${kind}`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({value:+val})});
}

async function setcolour(name, hex) {
  selected[name] = null;
  if (statusByName[name]) statusByName[name].colour = hex;
  await api(`/api/${name}/colour`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({hex})});
}

async function profile(name, key) {
  const wasParty = partyActive;
  selected[name] = key;            // optimistic: highlight immediately
  partyActive = false;
  partyMode = null;
  renderCards();
  if (wasParty) {
    await api('/api/party', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({on:false})});
  }
  await api(`/api/${name}/profile`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({key})});
  refresh();                       // reconcile with real state
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
  partyActive = turnOn;            // optimistic: colour the button immediately
  partyMode = turnOn ? mode : null;
  if (turnOn) selected[name] = null;
  renderCards();
  const r = await api('/api/party', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({on: turnOn, device: name, mode})});
  partyActive = r.active;          // reconcile with server truth
  partyMode = r.mode;
  renderCards();
  refresh();
}

(async () => {
  const [profiles, names] = await Promise.all([api('/api/profiles'), api('/api/devices')]);
  PROFILES = profiles;
  renderPending(names);            // show clickable lamp cards immediately
  loadWakeup(names);               // populate the wake-up panel in parallel
  refresh();                       // fill in live status when it arrives
  setInterval(refresh, 10000);
})();
