let PROFILES = {};
let partyActive = false;
let partyMode = null;  // "smooth" | "strobe" | "music" | null
let partyBpm = 0;      // music mode: current server tempo (manual or mic-detected)
let micOn = false;     // true while the mic is detecting and driving the tempo
// Manually tunable detection band (set via the sliders in the card). A beat = the
// average FFT magnitude inside [micFreqLo, micFreqHi] rising across an auto-set
// threshold. _binHz is the Hz width of one FFT bin (set once the AudioContext exists).
let micFreqLo = 60, micFreqHi = 3000, _binHz = 1;
// Beat threshold = this fraction of the adaptive peak band level (lMax). The floor
// doesn't matter here — onsets are relative to how hard the loudest hits land.
const BEAT_FRAC = 0.6;
// Anpasszeit in Sekunden: Zeitkonstante, über die das Centroid-Fenster auf den
// aktuellen Bereich zusammenschrumpft. Kürzer = reaktiver, mehr Farbwechsel auch
// bei höhenlastigen Songs; länger = ruhiger, näher an absoluter Zuordnung.
let micSpreadSec = 30;
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
  <div class="col-12 col-md-6" data-name="${name}">
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
            onclick="toggleParty('${name}','strobe')">Strobo</button>
          <button class="btn btn-sm ${psel(partyMode==='music' && micOn)}"
            onclick="toggleParty('${name}','music')">Musik</button>` : ''}
        </div>
        ${s.supports_colour && partyMode==='music' ? `
        <div class="border-top border-secondary pt-2 mb-3">
          <div class="input-group input-group-sm mb-2" style="max-width:200px">
            <input id="bpm-${name}" type="number" class="form-control" min="40" max="240"
              placeholder="${micOn ? 'höre…' : 'BPM'}"
              value="${partyBpm || ''}"
              oninput="partyBpm=+this.value||0"
              onkeydown="if(event.key==='Enter')setBpm('${name}')">
            <button class="btn ${psel(!micOn && partyBpm>0)}" onclick="setBpm('${name}')">Tempo</button>
          </div>
          ${micOn ? `
          <canvas id="spec-${name}" height="70" class="w-100 mb-1 rounded"
            style="background:#111;display:block"></canvas>
          <div class="d-flex align-items-center gap-2 small mb-1">
            <span style="width:7.5em">Band: <span id="bl-lo-${name}">${micFreqLo}</span>–<span id="bl-hi-${name}">${micFreqHi}</span> Hz</span>
            <input type="range" class="form-range" min="20" max="8000" step="10" value="${micFreqLo}"
              oninput="micFreqLo=Math.min(+this.value,micFreqHi-100);document.getElementById('bl-lo-${name}').textContent=micFreqLo">
            <input type="range" class="form-range" min="20" max="8000" step="10" value="${micFreqHi}"
              oninput="micFreqHi=Math.max(+this.value,micFreqLo+100);document.getElementById('bl-hi-${name}').textContent=micFreqHi">
          </div>
          <div class="d-flex align-items-center gap-2 small mb-1">
            <span style="width:8.5em">Anpassung: <span id="sp-${name}">${fmtSpread(micSpreadSec)}</span></span>
            <input type="range" class="form-range" min="0" max="100" step="1"
              value="${spreadPos(micSpreadSec)}" oninput="setSpread('${name}',+this.value)">
          </div>` : ''}
          <div class="small text-secondary" id="mic-${name}"></div>
        </div>` : ''}
        ${!(s.supports_colour && partyMode==='music') ? `
        <label class="form-label small mb-1">Helligkeit: <span id="bl-${name}">${s.bright ?? '-'}</span>%</label>
        <input type="range" class="form-range" min="1" max="100" value="${s.bright ?? 50}"
          oninput="document.getElementById('bl-${name}').textContent=this.value"
          onchange="setv('${name}','bright',this.value)">
        <label class="form-label small mb-1">Farbtemperatur (warm→kalt): <span id="tl-${name}">${s.temp ?? '-'}</span>%</label>
        <input type="range" class="form-range" min="0" max="100" value="${s.temp ?? 50}"
          oninput="document.getElementById('tl-${name}').textContent=this.value"
          onchange="setv('${name}','temp',this.value)">` : ''}
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
// A card's DOM is only rebuilt when its rendered HTML actually changes, so the 10 s
// status poll no longer wipes and re-creates every button on each tick — that churn
// detached buttons mid-click and made them "not react". A card the user is currently
// interacting with is also left alone, so a refresh can't yank a focused control.
let lastCardHtml = {};  // device name -> last HTML string we rendered for that card

function renderCards() {
  const names = deviceNames.length ? deviceNames : Object.keys(statusByName);
  const root = document.getElementById('lamps');
  const current = [...root.children];
  const sameStructure = current.length === names.length
    && names.every((n, i) => current[i].dataset.name === n);
  if (!sameStructure) {                 // first paint or the device list changed: full build
    root.innerHTML = names.map(n => {
      const html = card(n, statusByName[n] || pendingStatus());
      lastCardHtml[n] = html;
      return html;
    }).join('');
    return;
  }
  names.forEach((n, i) => {
    const html = card(n, statusByName[n] || pendingStatus());
    if (html === lastCardHtml[n]) return;            // unchanged → don't touch the DOM
    if (current[i].contains(document.activeElement)) return;  // user is interacting → defer
    current[i].outerHTML = html;
    lastCardHtml[n] = html;
  });
}

function renderPending(names) {
  deviceNames = names;
  renderCards();
}

async function refresh() {
  const [data, party] = await Promise.all([api('/api/status'), api('/api/party')]);
  partyActive = party.active;
  partyMode = party.mode;
  if (!partyActive || partyMode !== 'music') { stopMic(); micOn = false; }
  if (!micOn) partyBpm = party.bpm || 0;  // while the mic drives, the detected value wins
  // reflect the real active mode (e.g. after reopening the page), unless party runs
  if (!partyActive) {
    for (const [n, s] of Object.entries(data)) selected[n] = s.profile || null;
  }
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
  micOn = false;
  stopMic();
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
  // clicking the active mode turns it off; a different mode switches to it.
  // "music" here = mic-driven tempo; the manual Tempo button uses setBpm().
  const isMic = mode === 'music';
  const turnOn = !(partyActive && partyMode === mode && (!isMic || micOn));
  partyActive = turnOn;             // optimistic: colour the button immediately
  partyMode = turnOn ? mode : null;
  micOn = turnOn && isMic;
  if (turnOn) { selected[name] = null; if (isMic) partyBpm = 0; }
  stopMic();
  renderCards();
  const r = await api('/api/party', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({on: turnOn, device: name, mode, bpm: 0})});
  partyActive = r.active;           // reconcile with server truth
  partyMode = r.mode;
  partyBpm = r.bpm || 0;
  if (turnOn && isMic && partyActive) {
    micOn = true;
    startMic(name).catch(e => {
      micOn = false;
      renderCards();
      alert('Mikrofon nicht verfügbar (' + e.message + ').\n' +
            'Tipp: Mikro braucht HTTPS oder localhost, und die Musik muss über ' +
            'Lautsprecher hörbar sein. Manuelle BPM funktioniert trotzdem.');
    });
  }
  renderCards();
  refresh();
}

async function setBpm(name) {
  const el = document.getElementById('bpm-' + name);  // may hold the live-detected value
  const bpm = Math.max(40, Math.min(240, +(el && el.value) || partyBpm || 120));
  partyBpm = bpm;
  partyActive = true;
  partyMode = 'music';
  micOn = false;
  selected[name] = null;
  stopMic();                        // manual tempo is server-timed, no mic needed
  renderCards();
  const r = await api('/api/party', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({on: true, device: name, mode: 'music', bpm})});
  partyActive = r.active;
  partyMode = r.mode;
  partyBpm = r.bpm || bpm;
  renderCards();
}

// Adaptation-time slider runs on a log scale (0.5 s … 120 s) so the short, common
// values stay precise while still reaching 2-minute windows. Position 0–100 ↔ seconds.
const SPREAD_MIN = 0.5, SPREAD_RATIO = 240;   // 0.5 s × 240 = 120 s
function spreadPos(sec) {
  return Math.round(100 * Math.log(sec / SPREAD_MIN) / Math.log(SPREAD_RATIO));
}
function fmtSpread(sec) {
  return sec >= 60 ? (sec / 60).toFixed(1) + ' min' : sec + ' s';
}
function setSpread(name, pos) {
  const sec = SPREAD_MIN * Math.pow(SPREAD_RATIO, pos / 100);
  micSpreadSec = sec >= 10 ? Math.round(sec) : Math.round(sec * 10) / 10;
  const el = document.getElementById('sp-' + name);
  if (el) el.textContent = fmtSpread(micSpreadSec);
}

// --- Mic tempo detection (Web Audio). Reports the detected BPM to the server,
// which then metronomes at that tempo until a new BPM is reported. ---
let _ac = null, _ms = null, _raf = null, _src = null, _an = null;

async function startMic(name) {
  // Disable the browser's voice processing — noiseSuppression/echoCancellation
  // treat steady music as noise and gate the mic to near-silence.
  _ms = await navigator.mediaDevices.getUserMedia({audio: {
    echoCancellation: false, noiseSuppression: false, autoGainControl: false}});
  _ac = new (window.AudioContext || window.webkitAudioContext)();
  if (_ac.state === 'suspended') await _ac.resume();  // else the analyser yields silence
  _src = _ac.createMediaStreamSource(_ms);
  _an = _ac.createAnalyser();
  _an.fftSize = 1024;
  _an.smoothingTimeConstant = 0.1;   // little smoothing so onset transients stay sharp
  _binHz = _ac.sampleRate / _an.fftSize;  // Hz per FFT bin → maps slider Hz to bin index
  // Keep module-level refs (so nodes aren't GC'd) and run the graph into a muted
  // sink — some browsers only pull audio when it reaches the destination.
  const sink = _ac.createGain();
  sink.gain.value = 0;
  _src.connect(_an);
  _an.connect(sink);
  sink.connect(_ac.destination);
  const an = _an;
  const buf = new Uint8Array(an.frequencyBinCount);
  let prevLevel = 0, last = 0, sentBpm = 0, flashUntil = 0, lastSync = 0;
  let cMin = null, cMax = null;      // adaptive centroid range, in log-Hz
  let lMin = null, lMax = null;      // adaptive band-level range, drives brightness
  let lastFrame = 0;                  // for frame-rate-independent adaptation timing
  let beats = [];                    // recent onset timestamps for tempo estimation
  const meter = () => document.getElementById('mic-' + name);
  const tick = () => {
    an.getByteFrequencyData(buf);
    const now = performance.now();
    const dt = lastFrame ? (now - lastFrame) / 1000 : 0;  // real seconds since last frame
    lastFrame = now;
    // Beat = average magnitude inside the user-set band rising across the
    // threshold. The visible spectrum + draggable band/threshold let the user
    // aim detection at whatever part of the track carries the beat.
    const loBin = Math.max(1, Math.floor(micFreqLo / _binHz));
    const hiBin = Math.min(buf.length - 1, Math.ceil(micFreqHi / _binHz));
    let level = 0;
    for (let i = loBin; i <= hiBin; i++) level += buf[i];
    level /= Math.max(1, hiBin - loBin + 1);
    // Spectral centroid over the whole visible range (≤8 kHz) → hue: bass-heavy
    // sound sits low (red/warm), bright treble sits high (blue/violet). This is
    // deliberately NOT the beat band — the narrow band would barely move.
    const maxBin = Math.min(buf.length - 1, Math.ceil(8000 / _binHz));
    let csum = 0, cden = 0;
    for (let i = 1; i <= maxBin; i++) { csum += i * buf[i]; cden += buf[i]; }
    const cbin = cden > 0 ? csum / cden : 0;
    const cfreq = cbin * _binHz;
    // Adaptive mapping: track the centroid's own recent min/max (log-Hz) and map
    // within that window to the full wheel, so treble-heavy songs still span the
    // colours. New extremes widen the window instantly; otherwise it slowly
    // contracts toward the current value — the Spreizung slider sets how fast.
    const lf = Math.log2((cfreq || 100) / 100);
    const decay = 1 - Math.exp(-dt / micSpreadSec);   // contraction per frame for this time constant
    if (cMin === null) { cMin = cMax = lf; }
    if (lf < cMin) cMin = lf; else cMin += (lf - cMin) * decay;
    if (lf > cMax) cMax = lf; else cMax += (lf - cMax) * decay;
    const span = Math.max(0.3, cMax - cMin);   // floor avoids hue jitter when near-constant
    const ct = Math.max(0, Math.min(1, (lf - cMin) / span));
    const hue = Math.round(ct * 280);          // 0 red (bass) → 280 violet (treble)
    // Brightness from band intensity, auto-ranged like the centroid: track the
    // band level's own recent min/max and map within it, so quiet and loud tracks
    // both use the full brightness span without a manual threshold.
    if (lMin === null) { lMin = lMax = level; }
    if (level < lMin) lMin = level; else lMin += (level - lMin) * decay;
    if (level > lMax) lMax = level; else lMax += (level - lMax) * decay;
    const lspan = Math.max(20, lMax - lMin);   // floor avoids brightness jitter in near-silence
    const bnorm = Math.max(0, Math.min(1, (level - lMin) / lspan));
    const v = Math.round(350 + 650 * bnorm);
    // auto beat threshold at a fraction of the adaptive peak; rising edge across
    // it = onset, with a refractory gap (~max 300 bpm)
    const beatThresh = BEAT_FRAC * lMax;
    const isBeat = level > beatThresh && prevLevel <= beatThresh && now - last > 200;
    prevLevel = level;
    if (isBeat) flashUntil = now + 120;
    const cMinBin = (100 * 2 ** cMin) / _binHz, cMaxBin = (100 * 2 ** cMax) / _binHz;
    drawSpectrum(name, buf, loBin, hiBin, now < flashUntil, cbin, hue, cMinBin, cMaxBin, lMin, lMax, beatThresh);
    // feed the server the live colour+brightness ~5 Hz; it renders on its metronome
    if (now - lastSync > 180) {
      lastSync = now;
      api('/api/party/sync', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({hue, v})});
    }
    const m = meter();
    if (m) {
      m.textContent = `Pegel ${level.toFixed(0)} · Hell ${v} · BPM ${partyBpm || '–'}`
        + (now < flashUntil ? '  ●' : '');
    }
    if (isBeat) {
      last = now;
      beats.push(now);
      if (beats.length > 6) beats.shift();
      // median of recent inter-onset gaps → stable BPM, ignoring the odd miss/double.
      // Two onsets (one gap) already give a first estimate so the field fills fast.
      if (beats.length >= 2) {
        const gaps = [];
        for (let i = 1; i < beats.length; i++) gaps.push(beats[i] - beats[i - 1]);
        gaps.sort((a, b) => a - b);
        const bpm = Math.round(60000 / gaps[Math.floor(gaps.length / 2)]);
        if (bpm >= 40 && bpm <= 240) {
          partyBpm = bpm;
          const el = document.getElementById('bpm-' + name);
          if (el) el.value = bpm;    // live display
          // push the tempo to the server when it shifts; it metronomes on its own
          if (Math.abs(bpm - sentBpm) >= 2) {
            sentBpm = bpm;
            api('/api/party', {method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({on: true, device: name, mode: 'music', bpm})});
          }
        }
      }
    }
    _raf = requestAnimationFrame(tick);
  };
  tick();
}

// Live FFT bars up to ~8 kHz. In-band bins (beat band) are highlighted, out-of-band
// dimmed. A horizontal line marks the beat threshold; a vertical line (coloured in
// the hue it produces) marks the spectral centroid that drives the colour.
function drawSpectrum(name, buf, loBin, hiBin, flash, centroidBin, hue, cMinBin, cMaxBin, briFloor, briCeil, beatThresh) {
  const cv = document.getElementById('spec-' + name);
  if (!cv) return;
  const w = cv.clientWidth || 300, h = cv.height;
  if (cv.width !== w) cv.width = w;   // match the CSS-stretched width once
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, w, h);
  const maxBin = Math.min(buf.length - 1, Math.ceil(8000 / _binHz));
  const bw = w / maxBin;
  for (let i = 1; i <= maxBin; i++) {
    const bh = buf[i] / 255 * h;
    ctx.fillStyle = (i >= loBin && i <= hiBin) ? '#4ea0ff' : '#384050';
    ctx.fillRect((i - 1) * bw, h - bh, Math.max(1, bw), bh);
  }
  // adaptive centroid window edges (the range the hue is normalised within)
  ctx.strokeStyle = '#555';
  ctx.lineWidth = 1;
  for (const b of [cMinBin, cMaxBin]) {
    if (!(b > 0)) continue;
    const x = (b - 1) * bw;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  if (centroidBin > 0) {
    const cx = (centroidBin - 1) * bw;
    ctx.strokeStyle = `hsl(${hue}, 100%, 60%)`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, 0);
    ctx.lineTo(cx, h);
    ctx.stroke();
  }
  // Lines over the beat band, since they all relate to the band level. Beat
  // threshold (orange, = 60% of the peak) gates onset detection; the two green
  // lines are the auto-ranged brightness floor/ceiling brightness maps between.
  const bandL = (loBin - 1) * bw, bandR = hiBin * bw;
  const ty = h - beatThresh / 255 * h;
  ctx.strokeStyle = flash ? '#ff5555' : '#ffb000';
  ctx.lineWidth = flash ? 2 : 1;
  ctx.beginPath();
  ctx.moveTo(bandL, ty);
  ctx.lineTo(bandR, ty);
  ctx.stroke();
  ctx.strokeStyle = '#3ddc84';
  ctx.lineWidth = 1;
  for (const lvl of [briFloor, briCeil]) {
    if (lvl == null) continue;
    const y = h - lvl / 255 * h;
    ctx.beginPath();
    ctx.moveTo(bandL, y);
    ctx.lineTo(bandR, y);
    ctx.stroke();
  }
}

function stopMic() {
  if (_raf) { cancelAnimationFrame(_raf); _raf = null; }
  if (_ms) { _ms.getTracks().forEach(t => t.stop()); _ms = null; }
  if (_ac) { _ac.close().catch(() => {}); _ac = null; }
  _src = null; _an = null;
  document.querySelectorAll('[id^="mic-"]').forEach(el => el.textContent = '');
}

(async () => {
  const [profiles, names] = await Promise.all([api('/api/profiles'), api('/api/devices')]);
  PROFILES = profiles;
  renderPending(names);            // show clickable lamp cards immediately
  loadWakeup(names);               // populate the wake-up panel in parallel
  refresh();                       // fill in live status when it arrives
  setInterval(refresh, 10000);
})();
