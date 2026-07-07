/* monkeyVerse v2 — living-planet observer. Vanilla JS, no dependencies. */
"use strict";
const $ = (s) => document.querySelector(s);
const api = (p, o) => fetch(p, o).then((r) => (r.ok ? r.json() : Promise.reject(r)));

const S = {
  sims: [], current: null, ws: null, state: null, schema: null,
  tool: null, colorMode: "species", mode: "live", frames: [], pastFrame: null,
  tab: "live", speciesColors: {},
};

async function boot() {
  S.schema = await api("/api/config/schema");
  buildForm(S.schema);
  await refreshList();
  setInterval(refreshList, 4000);
  $("#newBtn").onclick = $("#emptyNew").onclick = openModal;
  $("#cancelBtn").onclick = closeModal;
  $("#modalBg").onclick = (e) => { if (e.target.id === "modalBg") closeModal(); };
  $("#createBtn").onclick = createSim;
  $("#pauseBtn").onclick = togglePause;
  $("#deleteBtn").onclick = deleteSim;
  $("#forkBtn").onclick = forkSim;
  $("#insClose").onclick = () => $("#inspector").classList.remove("show");
  $("#refreshHist").onclick = loadHistory;
  $("#colorMode").onchange = (e) => { S.colorMode = e.target.value; };
  $("#speed").oninput = (e) => { $("#speedVal").textContent = e.target.value + " p/s"; };
  $("#speed").onchange = (e) => control("speed", parseFloat(e.target.value));
  $("#tlSlider").oninput = onScrub;
  $("#tlLive").onclick = goLive;
  document.querySelectorAll("[data-tool]").forEach((b) => b.onclick = () => armTool(b));
  document.querySelectorAll(".tabbar button").forEach((b) => b.onclick = () => selectTab(b.dataset.tab));
  $("#world").addEventListener("click", onCanvasClick);
  window.addEventListener("resize", () => renderCurrent());
  requestAnimationFrame(loop);
}

/* ---------------- config form ---------------- */
function buildForm(cfg) {
  const grid = $("#formGrid"); grid.innerHTML = "";
  cfg.schema.forEach((f) => {
    const div = document.createElement("div"); div.className = "field";
    const help = f.help ? `<div class="help">${f.help}</div>` : "";
    const step = f.step || (f.type === "float" ? "any" : "1");
    const min = f.min !== undefined ? `min="${f.min}"` : "", max = f.max !== undefined ? `max="${f.max}"` : "";
    const type = f.type === "text" ? "text" : "number";
    div.innerHTML = `<label>${f.label}</label><input data-key="${f.key}" data-type="${f.type}"
      type="${type}" value="${cfg.defaults[f.key]}" ${min} ${max} step="${step}">${help}`;
    grid.appendChild(div);
  });
}
function readForm() {
  const out = {};
  document.querySelectorAll("#formGrid input").forEach((i) => {
    const t = i.dataset.type; let v = i.value;
    if (t === "int") v = parseInt(v, 10); else if (t === "float") v = parseFloat(v);
    out[i.dataset.key] = v;
  });
  return out;
}
function openModal() {
  const inp = document.querySelector('#formGrid input[data-key="name"]');
  if (inp) inp.value = "planeta-" + Math.random().toString(36).slice(2, 6);
  $("#modalBg").classList.add("open");
}
function closeModal() { $("#modalBg").classList.remove("open"); }
async function createSim() {
  $("#createBtn").disabled = true;
  try {
    const { id } = await api("/api/simulations", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(readForm()) });
    closeModal(); await refreshList(); selectSim(id);
  } catch (e) { alert("No se pudo crear el planeta."); }
  $("#createBtn").disabled = false;
}

/* ---------------- sim list ---------------- */
async function refreshList() {
  try { S.sims = await api("/api/simulations"); } catch (e) { return; }
  const list = $("#simList"); list.innerHTML = "";
  S.sims.forEach((s) => {
    const el = document.createElement("div");
    el.className = "sim-card " + s.status + (s.id === S.current ? " active" : "");
    el.onclick = () => selectSim(s.id);
    el.innerHTML = `<div class="name">${s.name}<span class="dot"></span></div>
      <div class="meta"><span><b>${s.population}</b> vivos</span><span><b>${s.species}</b> esp.</span>
      <span>gen <b>${s.max_generation}</b></span></div>
      <div class="meta"><span>t ${fmt(s.tick)}</span><span>${s.weather}</span></div>`;
    list.appendChild(el);
  });
  if (!S.current && S.sims.length === 0) showEmpty(true);
}

/* ---------------- selection ---------------- */
function selectSim(id) {
  if (S.current === id) return;
  S.current = id; showEmpty(false); goLive();
  $("#toolbar").style.display = "flex"; $("#timeline").style.display = "flex";
  $("#rightbar").style.display = "flex"; $("#inspector").classList.remove("show");
  connectWS(id); refreshList(); loadFrames();
  const s = S.sims.find((x) => x.id === id);
  if (s) { $("#speed").value = s.target_sps; $("#speedVal").textContent = s.target_sps + " p/s";
    $("#pauseBtn").textContent = s.status === "paused" ? "▶" : "⏸"; }
  if (S.tab === "species") loadSpecies();
  if (S.tab === "chronicle") loadChronicle();
  if (S.tab === "history") loadHistory();
}
function showEmpty(on) { $("#empty").style.display = on ? "flex" : "none"; $("#hud").style.display = on ? "none" : "flex"; }

/* ---------------- websocket ---------------- */
function connectWS(id) {
  if (S.ws) { try { S.ws.close(); } catch (e) {} }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${id}`); S.ws = ws;
  ws.onmessage = (ev) => {
    const d = JSON.parse(ev.data); if (d.error || S.current !== id) return;
    S.state = d; updateSpeciesColors(d.species); updateHUD(d); updateLive(d);
  };
  ws.onclose = () => { if (S.current === id) setTimeout(() => connectWS(id), 1500); };
}

/* ---------------- render ---------------- */
function loop() { renderCurrent(); requestAnimationFrame(loop); }
function renderCurrent() {
  if (S.mode === "past" && S.pastFrame) render(S.pastFrame, S.pastFrame.light ?? 1);
  else if (S.state) render(S.state, S.state.light ?? 1);
}

function render(state, light) {
  const cv = $("#world"), stage = $("#stage");
  const dpr = window.devicePixelRatio || 1, w = stage.clientWidth, h = stage.clientHeight;
  if (cv.width !== w * dpr || cv.height !== h * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const L = state.layers; if (!L) return;
  const rows = L.elev.length, cols = L.elev[0].length, cw = w / cols, ch = h / rows;
  const dim = 0.4 + 0.6 * light;
  for (let i = 0; i < rows; i++) for (let j = 0; j < cols; j++) {
    let r, g, b;
    const e = L.elev[i][j];
    if (L.water[i][j]) { r = 18 + e * 40; g = 55 + e * 60; b = 95 + e * 70; }
    else if (L.mountain[i][j]) { const s = e > 0.93 ? 200 : 100 + e * 70; r = s; g = s + 4; b = s + 12; }
    else { const v = L.veg[i][j]; r = 74 * (1 - v) + 38 * v; g = 58 * (1 - v) + 120 * v; b = 44 * (1 - v) + 52 * v; }
    if (L.flood[i][j]) { r = r * .4 + 40; g = g * .4 + 80; b = b * .4 + 150; }
    const f = L.fire[i][j]; if (f > 0.08) { r = r * (1 - f) + 255 * f; g = g * (1 - f) + 150 * f; b = b * (1 - f) + 30 * f; }
    ctx.fillStyle = `rgb(${r * dim | 0},${g * dim | 0},${b * dim | 0})`;
    ctx.fillRect(j * cw, i * ch, cw + 1, ch + 1);
  }
  const sx = w / state.width, sy = h / state.height;
  for (const a of state.agents) {
    const isLive = a.length >= 6;
    const spid = isLive ? a[4] : a[2], diet = isLive ? a[5] : a[3];
    const en = isLive ? a[3] : 0.5;
    ctx.beginPath(); ctx.arc(a[0] * sx, a[1] * sy, 1.5 + en * 3, 0, 6.2832);
    ctx.fillStyle = agentColor(spid, diet); ctx.fill();
  }
}
function agentColor(spid, diet) {
  if (S.colorMode === "diet") {
    const r = 60 + diet * 180, g = 180 - diet * 130, b = 70 - diet * 30;
    return `rgb(${r | 0},${g | 0},${b | 0})`;
  }
  return S.speciesColors[spid] || hashColor(spid);
}
function hashColor(id) { const hue = (id * 47) % 360; return `hsl(${hue},70%,58%)`; }
function updateSpeciesColors(species) {
  if (!species) return;
  species.forEach((sp) => {
    const c = sp.color || [.5, .5, .5];
    S.speciesColors[sp.id] = `rgb(${c[0] * 255 | 0},${80 + c[1] * 120 | 0},${c[2] * 255 | 0})`;
  });
}

/* ---------------- HUD + panels ---------------- */
function updateHUD(state) {
  const st = state.stats, rn = state.runner || {};
  const night = state.light < 0.5 ? '<div class="chip">🌙 noche</div>' : '<div class="chip">☀️ día</div>';
  const dis = (state.stats.weather && state.stats.weather !== "templado") ? `<div class="chip warn">⚠ ${st.weather}</div>` : "";
  const past = S.mode === "past" ? '<div class="chip time">🕰️ viendo el pasado</div>' : "";
  $("#hud").innerHTML = `<div class="chip">🕒 t <b>${fmt(state.tick)}</b></div>
    <div class="chip">👥 <b>${st.population}</b></div><div class="chip">🧬 <b>${st.species}</b> esp.</div>
    <div class="chip">gen <b>${st.max_generation}</b></div>${night}
    <div class="chip">${(rn.real_sps || 0).toFixed(0)} p/s</div>${dis}${past}`;
}
function updateLive(state) {
  if (S.tab !== "live") return;
  const st = state.stats;
  $("#statgrid").innerHTML = [["Población", st.population], ["Especies", st.species],
    ["Gen. máx.", st.max_generation], ["Energía", st.avg_energy],
    ["Señales ‰", (st.sound_activity * 1000).toFixed(1)], ["Vegetación", fmt(Math.round(st.veg_total))]]
    .map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  const tot = Math.max(1, st.population), h = st.herbivores, c = st.carnivores, o = tot - h - c;
  $("#trophic").innerHTML =
    `<div style="width:${h / tot * 100}%;background:#46d6a6">${h}</div>
     <div style="width:${o / tot * 100}%;background:#7d8ba0">${o}</div>
     <div style="width:${c / tot * 100}%;background:#ff6b6b">${c}</div>`;
  const gm = st.gene_means || {};
  const B = { metabolism: [.4, 1.8], plant_eff: [.3, 1.6], meat_eff: [.3, 1.6], diet: [0, 1], size: [.6, 1.6],
    vision: [.6, 1.6], speed: [0, 1], max_age: [500, 8000], repro_threshold: [25, 170], mutation_rate: [0, .5] };
  const NM = { metabolism: "metabolismo", plant_eff: "herbivoría", meat_eff: "carnivoría", diet: "dieta",
    size: "tamaño", vision: "visión", speed: "velocidad", max_age: "longevidad", repro_threshold: "umbral repr.", mutation_rate: "mutación" };
  $("#genes").innerHTML = Object.keys(B).map((k) => {
    const [lo, hi] = B[k], v = gm[k] || 0, p = Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100));
    return `<div class="gene-row"><span class="lbl">${NM[k]}</span><span class="bar"><div style="width:${p}%"></div></span><span class="val">${v.toFixed(2)}</span></div>`;
  }).join("");
}

/* ---------------- controls & god tools ---------------- */
async function control(action, value) {
  if (!S.current) return;
  await api(`/api/simulations/${S.current}/control`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, value }) }).catch(() => {});
}
function togglePause() {
  const s = S.sims.find((x) => x.id === S.current); if (!s) return;
  const paused = s.status === "paused"; control(paused ? "resume" : "pause");
  s.status = paused ? "running" : "paused"; $("#pauseBtn").textContent = paused ? "⏸" : "▶";
}
async function deleteSim() {
  if (!S.current || !confirm("¿Eliminar este planeta y toda su historia?")) return;
  await api(`/api/simulations/${S.current}`, { method: "DELETE" }).catch(() => {});
  if (S.ws) { try { S.ws.close(); } catch (e) {} }
  S.current = null; S.state = null; $("#toolbar").style.display = "none";
  $("#timeline").style.display = "none"; $("#rightbar").style.display = "none"; showEmpty(true); refreshList();
}
async function forkSim() {
  if (!S.current) return;
  const { id } = await api(`/api/simulations/${S.current}/fork`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }).catch(() => ({}));
  if (id) { await refreshList(); selectSim(id); }
}
const INSTANT = { rain: 1, drought: 1, flood: 1, spawn_species: 1 };
function armTool(btn) {
  const t = btn.dataset.tool;
  if (INSTANT[t]) { intervene(t, {}); flash(btn); return; }
  document.querySelectorAll("[data-tool]").forEach((b) => b.classList.remove("armed"));
  if (S.tool === t) { S.tool = null; } else { S.tool = t; btn.classList.add("armed"); }
}
function flash(btn) { btn.classList.add("armed"); setTimeout(() => btn.classList.remove("armed"), 300); }
async function intervene(kind, params) {
  if (!S.current) return;
  await api(`/api/simulations/${S.current}/intervene`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind, params }) }).catch(() => {});
}
function onCanvasClick(e) {
  const base = (S.mode === "past" && S.pastFrame) ? S.pastFrame : S.state;
  if (!base) return;
  const cv = $("#world"), rect = cv.getBoundingClientRect();
  const wx = Math.floor((e.clientX - rect.left) / rect.width * base.width);
  const wy = Math.floor((e.clientY - rect.top) / rect.height * base.height);
  if (S.tool) {
    const params = { x: wx, y: wy };
    if (S.tool === "food") { params.radius = 8; params.amount = 1.6; }
    intervene(S.tool, params);
    document.querySelectorAll("[data-tool]").forEach((b) => b.classList.remove("armed")); S.tool = null;
    return;
  }
  inspectNear(wx, wy, base);
}
async function inspectNear(wx, wy, base) {
  let best = null, bd = 1e9;
  for (const a of base.agents) { const d = (a[0] - wx) ** 2 + (a[1] - wy) ** 2; if (d < bd) { bd = d; best = a; } }
  if (!best || bd > 30) { $("#inspector").classList.remove("show"); return; }
  const isLive = best.length >= 6, spid = isLive ? best[4] : best[2], diet = isLive ? best[5] : best[3];
  $("#insTitle").textContent = "Individuo";
  $("#insBody").innerHTML =
    `<div class="row">Posición <b>${best[0]}, ${best[1]}</b></div>
     <div class="row">Especie <b>#${spid}</b></div>
     <div class="row">Dieta <b>${diet < .35 ? "herbívoro" : diet > .65 ? "carnívoro" : "omnívoro"}</b></div>
     <div class="row">Color linaje <b><span style="display:inline-block;width:11px;height:11px;border-radius:3px;background:${agentColor(spid, diet)}"></span></b></div>`;
  $("#inspector").classList.add("show");
}

/* ---------------- time machine ---------------- */
async function loadFrames() {
  if (!S.current) return;
  try { const d = await api(`/api/simulations/${S.current}/frames`); S.frames = d.ticks || []; } catch (e) { S.frames = []; }
  const sl = $("#tlSlider"); sl.max = Math.max(0, S.frames.length - 1);
  if (S.mode === "live") sl.value = sl.max;
  setTimeout(() => { if (S.current) loadFrames(); }, 6000);
}
async function onScrub(e) {
  const idx = parseInt(e.target.value, 10); const tick = S.frames[idx];
  if (tick === undefined) return;
  S.mode = "past"; $("#tlMode").textContent = "Pasado"; $("#tlTick").textContent = fmt(tick);
  try { S.pastFrame = await api(`/api/simulations/${S.current}/frame?tick=${tick}`); } catch (e) {}
}
function goLive() {
  S.mode = "live"; S.pastFrame = null; $("#tlMode").textContent = "En vivo"; $("#tlTick").textContent = "—";
  const sl = $("#tlSlider"); sl.value = sl.max;
}

/* ---------------- tabs ---------------- */
function selectTab(tab) {
  S.tab = tab;
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
  if (tab === "species") loadSpecies();
  if (tab === "chronicle") loadChronicle();
  if (tab === "history") loadHistory();
  if (tab === "live" && S.state) updateLive(S.state);
}
async function loadSpecies() {
  if (!S.current) return;
  let d; try { d = await api(`/api/simulations/${S.current}/species`); } catch (e) { return; }
  updateSpeciesColors(d.living);
  $("#speciesList").innerHTML = (d.living || []).map((sp) =>
    `<div class="species-row"><span class="swatch" style="background:${S.speciesColors[sp.id] || hashColor(sp.id)}"></span>
     <span class="nm">${sp.name} <span class="pp">#${sp.id}</span></span>
     <span class="pp"><b style="color:var(--text)">${sp.pop}</b> · desde t${fmt(sp.founded_tick)}</span></div>`).join("")
    || '<div style="color:var(--muted)">Aún no hay especies registradas.</div>';
}
async function loadChronicle() {
  if (!S.current) return;
  let d; try { d = await api(`/api/simulations/${S.current}/milestones?limit=200`); } catch (e) { return; }
  $("#chronicle").innerHTML = d.slice().reverse().map((m) =>
    `<div class="ms-row"><span class="t">t ${fmt(m.tick)}</span><span class="lb">${m.label || m.kind}</span></div>`).join("")
    || '<div style="color:var(--muted)">La historia aún no comienza…</div>';
}
async function loadHistory() {
  if (!S.current) return;
  let d; try { d = await api(`/api/simulations/${S.current}/stats?limit=3000`); } catch (e) { return; }
  if (!d.length) return;
  const t = d.map((r) => r.tick);
  line("cPop", t, [{ v: d.map((r) => r.population), c: "#46d6a6" }]);
  line("cSpp", t, [{ v: d.map((r) => r.species), c: "#b98bff" }]);
  line("cTro", t, [{ v: d.map((r) => r.herbivores), c: "#46d6a6" }, { v: d.map((r) => r.carnivores), c: "#ff6b6b" }]);
  line("cBD", t, [{ v: d.map((r) => r.births), c: "#5fa0ff" }, { v: d.map((r) => r.deaths), c: "#ff6b6b" }]);
  line("cSig", t, [{ v: d.map((r) => r.sound_activity), c: "#ffcf5c" }]);
}
function line(id, xs, series) {
  const cv = document.getElementById(id), dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight || 78; cv.width = w * dpr; cv.height = h * dpr;
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  let mx = 0; series.forEach((s) => s.v.forEach((v) => { if (v > mx) mx = v; })); if (mx <= 0) mx = 1;
  const pad = 6, n = xs.length;
  series.forEach((s) => {
    ctx.beginPath(); ctx.strokeStyle = s.c; ctx.lineWidth = 1.5;
    s.v.forEach((v, i) => { const px = pad + i / Math.max(1, n - 1) * (w - 2 * pad), py = h - pad - v / mx * (h - 2 * pad);
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
    ctx.stroke();
  });
  ctx.fillStyle = "#7688a0"; ctx.font = "9px sans-serif"; ctx.fillText(String(Math.round(mx)), 3, 10);
}

function fmt(n) { if (n == null) return "0"; if (n >= 1e6) return (n / 1e6).toFixed(1) + "M"; if (n >= 1e3) return (n / 1e3).toFixed(1) + "k"; return String(n); }
boot();
