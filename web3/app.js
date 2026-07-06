/* monkeyVerse v3 — observable living-planet UI. Vanilla JS, no dependencies. */
"use strict";
const $ = (s) => document.querySelector(s);
const api = (p, o) => fetch(p, o).then((r) => (r.ok ? r.json() : Promise.reject(r)));

const S = {
  sims: [], current: null, ws: null, state: null, schema: null,
  tool: null, colorMode: "species", mode: "live", frames: [], pastFrame: null,
  tab: "live", speciesColors: {},
  selectedAgentId: null, agentDetail: null, followMode: false,
  showRadii: false, showTraj: false, soundOn: false, volume: 0.6,
  seenInteractionIds: new Set(), lastInterPoll: 0,
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
  $("#exportBtn").onclick = exportData;
  $("#insClose").onclick = closeInspector;
  $("#followBtn").onclick = toggleFollow;
  $("#playSymbolBtn").onclick = replayLastSymbol;
  $("#refreshHist").onclick = loadHistory;
  $("#refreshInter").onclick = loadInteractions;
  $("#colorMode").onchange = (e) => { S.colorMode = e.target.value; };
  $("#toggleRadii").onclick = (e) => { S.showRadii = !S.showRadii; e.target.classList.toggle("on", S.showRadii); };
  $("#toggleTraj").onclick = (e) => { S.showTraj = !S.showTraj; e.target.classList.toggle("on", S.showTraj); };
  $("#toggleSound").onclick = (e) => {
    S.soundOn = !S.soundOn; e.target.classList.toggle("on", S.soundOn);
    MVAudio.setEnabled(S.soundOn);
  };
  $("#volume").oninput = (e) => { S.volume = e.target.value / 100; MVAudio.setVolume(S.volume); };
  $("#tlSlider").oninput = onScrub;
  $("#tlLive").onclick = goLive;
  $("#filterAgent").onchange = loadInteractions;
  $("#filterType").onchange = loadInteractions;

  document.querySelectorAll("[data-tool]").forEach((b) => { b.onclick = () => armTool(b); });
  document.querySelectorAll(".tabbar button").forEach((b) => { b.onclick = () => selectTab(b.dataset.tab); });

  const sidebar = $("#sidebar"), rightbar = $("#rightbar");
  $("#openSidebarBtn")?.addEventListener("click", () => sidebar.classList.add("open"));
  $("#openRightbarBtn")?.addEventListener("click", () => rightbar.classList.add("open"));
  $("#closeSidebar")?.addEventListener("click", () => sidebar.classList.remove("open"));

  $("#world").addEventListener("click", onCanvasClick);
  window.addEventListener("resize", () => renderCurrent());
  requestAnimationFrame(loop);
  setInterval(pollAudioInteractions, 900);
  setInterval(refreshAgentDetail, 1500);
}

/* ------------------------------------------------------------ config form */
function buildForm(cfg) {
  const grid = $("#formGrid");
  grid.innerHTML = "";
  cfg.schema.forEach((f) => {
    const div = document.createElement("div");
    div.className = "field";
    const help = f.help ? `<div class="help">${f.help}</div>` : "";
    if (f.type === "select") {
      const opts = f.options.map((o) => `<option value="${o}" ${o === f.default ? "selected" : ""}>${o}</option>`).join("");
      div.innerHTML = `<label>${f.label}</label><select data-key="${f.key}" data-type="select">${opts}</select>${help}`;
    } else {
      const step = f.step || (f.type === "float" ? "any" : "1");
      const min = f.min !== undefined ? `min="${f.min}"` : "", max = f.max !== undefined ? `max="${f.max}"` : "";
      const type = f.type === "text" ? "text" : "number";
      div.innerHTML = `<label>${f.label}</label><input data-key="${f.key}" data-type="${f.type}"
        type="${type}" value="${cfg.defaults[f.key]}" ${min} ${max} step="${step}">${help}`;
    }
    grid.appendChild(div);
  });
}
function readForm() {
  const out = {};
  document.querySelectorAll("#formGrid [data-key]").forEach((el) => {
    const t = el.dataset.type; let v = el.value;
    if (t === "int") v = parseInt(v, 10); else if (t === "float") v = parseFloat(v);
    out[el.dataset.key] = v;
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

/* ---------------------------------------------------------- sim list ---- */
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
      <div class="meta"><span>t ${fmt(s.tick)}</span><span>${s.weather}</span><span>${s.cognition_mode}</span></div>`;
    list.appendChild(el);
  });
  if (!S.current && S.sims.length === 0) showEmpty(true);
}

/* ---------------------------------------------------------- selection --- */
function selectSim(id) {
  if (S.current === id) return;
  S.current = id; showEmpty(false); goLive();
  S.selectedAgentId = null; S.agentDetail = null; S.followMode = false;
  S.seenInteractionIds = new Set();
  closeInspector();
  $("#toolbar").style.display = "flex"; $("#timeline").style.display = "flex";
  connectWS(id); refreshList(); loadFrames();
  document.querySelectorAll(".sidebar, .rightbar").forEach((el) => el.classList.remove("open"));
  const s = S.sims.find((x) => x.id === id);
  if (s) $("#pauseBtn").textContent = s.status === "paused" ? "▶" : "⏸";
  refreshTabData();
}
function showEmpty(on) { $("#empty").style.display = on ? "flex" : "none"; $("#hud").style.display = on ? "none" : "flex"; }

function connectWS(id) {
  if (S.ws) { try { S.ws.close(); } catch (e) {} }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${id}`); S.ws = ws;
  ws.onmessage = (ev) => {
    const d = JSON.parse(ev.data); if (d.error || S.current !== id) return;
    S.state = d; updateSpeciesColors(d.species); updateHUD(d); updateLive(d);
    updateAgentList(d);
  };
  ws.onclose = () => { if (S.current === id) setTimeout(() => connectWS(id), 1500); };
}

/* ---------------------------------------------------------- render loop - */
function loop() { renderCurrent(); requestAnimationFrame(loop); }
function renderCurrent() {
  if (S.mode === "past" && S.pastFrame) render(S.pastFrame, S.pastFrame.light ?? 1);
  else if (S.state) render(S.state, S.state.light ?? 1);
}

function findAgentTuple(state, id) {
  for (const a of state.agents) { if ((a.length >= 7 ? a[6] : null) === id) return a; }
  return null;
}

function render(state, light) {
  const cv = $("#world"), stage = $("#stage");
  const dpr = window.devicePixelRatio || 1, w = stage.clientWidth, h = stage.clientHeight;
  if (cv.width !== w * dpr || cv.height !== h * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const L = state.layers; if (!L) return;
  const rows = L.elev.length, cols = L.elev[0].length;
  const dim = 0.4 + 0.6 * light;

  let sel = null;
  if (S.selectedAgentId != null) sel = findAgentTuple(state, S.selectedAgentId);
  const follow = S.followMode && sel;

  // crop window (in downsampled-grid space) when following
  let gx0 = 0, gy0 = 0, gcols = cols, grows = rows;
  if (follow) {
    const gcx = (sel[0] / state.width) * cols, gcy = (sel[1] / state.height) * rows;
    const half = 16;
    gcols = Math.min(cols, half * 2); grows = Math.min(rows, half * 2);
    gx0 = Math.round(gcx - half); gy0 = Math.round(gcy - half);
  }
  const cw = w / gcols, ch = h / grows;

  for (let gi = 0; gi < grows; gi++) {
    let i = (gy0 + gi) % rows; if (i < 0) i += rows;
    for (let gj = 0; gj < gcols; gj++) {
      let j = (gx0 + gj) % cols; if (j < 0) j += cols;
      let r, g, b;
      const e = L.elev[i][j];
      if (L.water[i][j]) { r = 18 + e * 40; g = 55 + e * 60; b = 95 + e * 70; }
      else if (L.mountain[i][j]) { const s = e > 0.93 ? 200 : 100 + e * 70; r = s; g = s + 4; b = s + 12; }
      else { const v = L.veg[i][j]; r = 74 * (1 - v) + 38 * v; g = 58 * (1 - v) + 120 * v; b = 44 * (1 - v) + 52 * v; }
      if (L.flood[i][j]) { r = r * .4 + 40; g = g * .4 + 80; b = b * .4 + 150; }
      const f = L.fire[i][j]; if (f > 0.08) { r = r * (1 - f) + 255 * f; g = g * (1 - f) + 150 * f; b = b * (1 - f) + 30 * f; }
      ctx.fillStyle = `rgb(${r * dim | 0},${g * dim | 0},${b * dim | 0})`;
      ctx.fillRect(gj * cw, gi * ch, cw + 1, ch + 1);
    }
  }

  // world -> screen mapping consistent with the (possibly cropped) grid above
  const sxFull = cols / state.width, syFull = rows / state.height;
  function toScreen(wx, wy) {
    let gx = wx * sxFull - gx0, gy = wy * syFull - gy0;
    gx = ((gx % cols) + cols) % cols; gy = ((gy % rows) + rows) % rows;
    if (follow) { if (gx > gcols) gx -= cols; if (gy > grows) gy -= rows; }
    return [gx * cw, gy * ch];
  }

  const agents = state.agents || [];
  for (const a of agents) {
    const isLive = a.length >= 7;
    const spid = isLive ? a[4] : a[2], diet = isLive ? a[5] : a[3];
    const en = isLive ? a[3] : 0.5;
    const aid = isLive ? a[6] : null;
    const [px, py] = toScreen(a[0], a[1]);
    if (px < -20 || py < -20 || px > w + 20 || py > h + 20) continue;
    const isSel = aid != null && aid === S.selectedAgentId;
    ctx.beginPath(); ctx.arc(px, py, (isSel ? 2.4 : 1.5) + en * 3, 0, 6.2832);
    ctx.fillStyle = agentColor(spid, diet); ctx.fill();
    if (isSel) { ctx.lineWidth = 1.5; ctx.strokeStyle = "#fff"; ctx.stroke(); }
  }

  // overlays for the selected agent
  if (sel) {
    const [px, py] = toScreen(sel[0], sel[1]);
    if (S.showRadii && S.agentDetail?.live) {
      const r = S.agentDetail.live.perception_radius || 3;
      const rr = r * sxFull * cw;
      ctx.beginPath(); ctx.arc(px, py, rr, 0, 6.2832);
      ctx.strokeStyle = "rgba(95,160,255,.55)"; ctx.lineWidth = 1.2; ctx.stroke();
    }
    if (S.showTraj && S.agentDetail?.live?.trajectory) {
      const traj = S.agentDetail.live.trajectory;
      ctx.beginPath();
      traj.forEach(([tx, ty], i) => {
        const [sx, sy] = toScreen(tx, ty);
        i === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy);
      });
      ctx.strokeStyle = "rgba(185,139,255,.8)"; ctx.lineWidth = 1.6; ctx.stroke();
    }
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

/* ---------------------------------------------------------- HUD + panels  */
function updateHUD(state) {
  const st = state.stats, rn = state.runner || {};
  const night = state.light < 0.5 ? '<div class="chip">🌙 noche</div>' : '<div class="chip">☀️ día</div>';
  const dis = (st.weather && st.weather !== "templado") ? `<div class="chip warn">⚠ ${st.weather}</div>` : "";
  const past = S.mode === "past" ? '<div class="chip time">🕰️ pasado</div>' : "";
  $("#hud").innerHTML = `<div class="chip">🕒 t <b>${fmt(state.tick)}</b></div>
    <div class="chip">👥 <b>${st.population}</b></div><div class="chip">🧬 <b>${st.species}</b> esp.</div>
    <div class="chip">gen <b>${st.max_generation}</b></div>${night}
    <div class="chip">${(rn.real_tick_rate || 0).toFixed(1)}/${rn.tick_rate || "?"} t/s</div>${dis}${past}`;
  if (rn.tick_rate) $("#rateChip").textContent = `${rn.tick_rate} t/s (tiempo real)`;
}

function updateLive(state) {
  if (S.tab !== "live") return;
  const st = state.stats;
  $("#statgrid").innerHTML = [["Población", st.population], ["Especies", st.species],
    ["Gen. máx.", st.max_generation], ["Energía", st.avg_energy],
    ["Div. genética", st.genetic_diversity], ["Div. lenguaje", st.language_diversity]]
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

function updateAgentList(state) {
  if (S.tab !== "agents") return;
  const agents = (state.agents || []).filter((a) => a.length >= 7).slice(0, 200);
  $("#agentList").innerHTML = agents.map((a) => {
    const [x, y, hue, en, spid, diet, aid] = a;
    return `<div class="agent-row" data-id="${aid}">
      <span class="id">#${aid}</span>
      <span class="st">esp ${spid} · ${diet < .35 ? "herb" : diet > .65 ? "carn" : "omn"}</span>
      <span class="en">${(en * 120).toFixed(0)}</span></div>`;
  }).join("") || '<div style="color:var(--muted)">Sin agentes vivos.</div>';
  document.querySelectorAll("#agentList .agent-row").forEach((row) => {
    row.onclick = () => selectAgent(parseInt(row.dataset.id, 10));
  });
  const sel = $("#filterAgent");
  if (sel.childElementCount < 2 && agents.length) {
    const opts = agents.slice(0, 100).map((a) => `<option value="${a[6]}">#${a[6]}</option>`).join("");
    sel.innerHTML = '<option value="">Cualquier agente</option>' + opts;
  }
}

/* ---------------------------------------------------------- agent select */
function selectAgent(aid) {
  S.selectedAgentId = aid;
  $("#inspector").classList.add("show");
  refreshAgentDetail();
}
function closeInspector() {
  $("#inspector").classList.remove("show");
  S.selectedAgentId = null; S.agentDetail = null; S.followMode = false;
  $("#followBtn").classList.remove("on");
}
async function refreshAgentDetail() {
  if (!S.current || S.selectedAgentId == null) return;
  let d;
  try { d = await api(`/api/simulations/${S.current}/agent/${S.selectedAgentId}`); } catch (e) { return; }
  S.agentDetail = d;
  if (!d.live) return;
  renderInspector(d);
}
function renderInspector(d) {
  const a = d.live;
  $("#insTitle").textContent = `#${a.id} · ${a.species}`;
  const genesRows = ["metabolism", "diet", "size", "vision", "speed", "max_age"]
    .map((k) => `<div class="row">${k} <b>${a.genes[k].toFixed(2)}</b></div>`).join("");
  const lastInter = (a.last_interactions || []).slice(-4).reverse()
    .map((e) => `<div class="row">${e.type} → ${e.target_id ?? "-"} <b>${e.result || ""}</b></div>`).join("")
    || '<div class="row">sin interacciones aún</div>';
  const lastSym = (a.last_symbols || []).slice(-5).reverse()
    .map((s) => `<span class="symbol-chip"><b>${s.symbol}</b> ${s.label}</span>`).join("") || "—";
  $("#insBody").innerHTML = `
    <div class="row">Estado <b>${a.state}</b></div>
    <div class="row">Edad <b>${a.age}</b></div>
    <div class="row">Energía <b>${a.energy}</b></div>
    <div class="row">Generación <b>${a.generation}</b></div>
    <div class="row">Posición <b>${a.x}, ${a.y}</b></div>
    <div class="row">Hijos (fitness) <b>${a.fitness}</b></div>
    <div class="row">Ataques <b>${a.attacks}</b></div>
    <div class="row">Conoce a <b>${a.known_agents}</b> individuos</div>
    <div class="mini-h">Genes</div>${genesRows}
    <div class="mini-h">Últimas interacciones</div>${lastInter}
    <div class="mini-h">Últimos sonidos</div>${lastSym}
  `;
}
function toggleFollow() {
  S.followMode = !S.followMode;
  $("#followBtn").classList.toggle("on", S.followMode);
}
function replayLastSymbol() {
  const syms = S.agentDetail?.live?.last_symbols;
  if (syms && syms.length) MVAudio.play(syms[syms.length - 1].symbol, 2);
}

function onCanvasClick(e) {
  const base = (S.mode === "past" && S.pastFrame) ? S.pastFrame : S.state;
  if (!base) return;
  const cv = $("#world"), rect = cv.getBoundingClientRect();
  const relX = (e.clientX - rect.left) / rect.width, relY = (e.clientY - rect.top) / rect.height;

  if (S.tool) {
    const wx = Math.floor(relX * base.width), wy = Math.floor(relY * base.height);
    const params = { x: wx, y: wy };
    if (S.tool === "food") { params.radius = 8; params.amount = 1.6; }
    intervene(S.tool, params);
    document.querySelectorAll("[data-tool]").forEach((b) => b.classList.remove("armed")); S.tool = null;
    return;
  }
  const w = rect.width, h = rect.height;
  const L = base.layers, cols = L.elev[0].length, rows = L.elev.length;
  let gx0 = 0, gy0 = 0, gcols = cols, grows = rows;
  const sel = S.selectedAgentId != null ? findAgentTuple(base, S.selectedAgentId) : null;
  if (S.followMode && sel) {
    const gcx = (sel[0] / base.width) * cols, gcy = (sel[1] / base.height) * rows;
    const half = 16; gcols = Math.min(cols, half * 2); grows = Math.min(rows, half * 2);
    gx0 = Math.round(gcx - half); gy0 = Math.round(gcy - half);
  }
  const gx = gx0 + relX * gcols, gy = gy0 + relY * grows;
  const wx = Math.floor((gx / cols) * base.width), wy = Math.floor((gy / rows) * base.height);
  inspectNear(wx, wy, base);
}

function inspectNear(wx, wy, base) {
  let best = null, bd = 1e9;
  for (const a of base.agents) {
    if (a.length < 7) continue;
    const d = (a[0] - wx) ** 2 + (a[1] - wy) ** 2;
    if (d < bd) { bd = d; best = a; }
  }
  if (!best || bd > 40) return;
  selectAgent(best[6]);
}

/* ---------------------------------------------------------- controls ---- */
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
  S.current = null; S.state = null; closeInspector();
  $("#toolbar").style.display = "none"; $("#timeline").style.display = "none";
  showEmpty(true); refreshList();
}
async function forkSim() {
  if (!S.current) return;
  const { id } = await api(`/api/simulations/${S.current}/fork`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }).catch(() => ({}));
  if (id) { await refreshList(); selectSim(id); }
}
function exportData() {
  if (!S.current) return;
  window.open(`/api/simulations/${S.current}/export.json`, "_blank");
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

/* ---------------------------------------------------------- time machine */
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

/* ---------------------------------------------------------- tabs ------- */
function selectTab(tab) {
  S.tab = tab;
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
  refreshTabData();
}
function refreshTabData() {
  if (S.tab === "species") loadSpecies();
  if (S.tab === "agents" && S.state) updateAgentList(S.state);
  if (S.tab === "interactions") loadInteractions();
  if (S.tab === "language") loadLanguage();
  if (S.tab === "brains") loadBrains();
  if (S.tab === "history") loadHistory();
  if (S.tab === "live" && S.state) updateLive(S.state);
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

async function loadInteractions() {
  if (!S.current) return;
  const agent = $("#filterAgent").value, type = $("#filterType").value;
  const params = new URLSearchParams({ limit: "150" });
  if (agent) params.set("agent_id", agent);
  if (type) params.set("type", type);
  let d; try { d = await api(`/api/simulations/${S.current}/interactions?${params}`); } catch (e) { return; }
  $("#interList").innerHTML = d.map((ev) => {
    const sig = ev.signal != null ? ` [${ev.signal}]` : "";
    return `<div class="inter-row"><span class="t">t${fmt(ev.tick)}</span>
      <span class="k ${ev.type}">${ev.type}${sig}</span>
      <span class="desc">#${ev.agent_id} → ${ev.target_id ?? "-"} · ${ev.result || ""}</span></div>`;
  }).join("") || '<div style="color:var(--muted)">Sin interacciones con estos filtros.</div>';
}

async function loadLanguage() {
  if (!S.current) return;
  let d; try { d = await api(`/api/simulations/${S.current}/language`); } catch (e) { return; }
  $("#langDiversity").innerHTML =
    `<div class="stat"><div class="k">Diversidad global</div><div class="v">${d.diversity}</div></div>`;
  $("#symbolChips").innerHTML = d.most_used.map((s) =>
    `<span class="symbol-chip" data-symbol="${s.symbol}"><b>${s.symbol}</b> ${s.label} · ${fmt(s.count)}</span>`).join("");
  document.querySelectorAll("#symbolChips .symbol-chip").forEach((el) => {
    el.onclick = () => MVAudio.play(parseInt(el.dataset.symbol, 10), 2);
  });
  const rows = [];
  for (const [sid, prof] of Object.entries(d.species_profiles)) {
    for (const [sym, info] of Object.entries(prof.associations || {})) {
      rows.push(`<tr><td>esp #${sid}</td><td>${sym} (${d.legend[sym]})</td><td>${info.context}</td>
        <td>${(info.strength * 100).toFixed(0)}%</td><td>${info.n}</td></tr>`);
    }
  }
  $("#langAssoc").innerHTML = rows.length
    ? `<table class="symbol-table"><tr><th>especie</th><th>símbolo</th><th>contexto</th><th>fuerza</th><th>n</th></tr>${rows.join("")}</table>`
    : '<div style="color:var(--muted)">Aún no hay asociaciones medibles.</div>';
}

async function loadBrains() {
  if (!S.current) return;
  let d; try { d = await api(`/api/simulations/${S.current}/species`); } catch (e) { return; }
  $("#brainList").innerHTML = (d.living || []).map((sp) => `
    <div class="brain-card">
      <div class="row"><span>${sp.name} #${sp.id}</span><b>${sp.pop} vivos</b></div>
      <div class="row"><span>Complejidad de cerebro</span><b>${(sp.avg_complexity || 0).toFixed(3)}</b></div>
    </div>`).join("") || '<div style="color:var(--muted)">Sin especies vivas.</div>';
}

async function loadHistory() {
  if (!S.current) return;
  let d; try { d = await api(`/api/simulations/${S.current}/stats?limit=3000`); } catch (e) { return; }
  if (d.length) {
    const t = d.map((r) => r.tick);
    line("cPop", t, [{ v: d.map((r) => r.population), c: "#46d6a6" }]);
    line("cSpp", t, [{ v: d.map((r) => r.species), c: "#b98bff" }]);
    line("cTro", t, [{ v: d.map((r) => r.herbivores), c: "#46d6a6" }, { v: d.map((r) => r.carnivores), c: "#ff6b6b" }]);
    line("cBD", t, [{ v: d.map((r) => r.births), c: "#5fa0ff" }, { v: d.map((r) => r.deaths), c: "#ff6b6b" }]);
    line("cDiv", t, [{ v: d.map((r) => r.genetic_diversity), c: "#ffcf5c" }, { v: d.map((r) => r.language_diversity), c: "#5fa0ff" }]);
  }
  let ms; try { ms = await api(`/api/simulations/${S.current}/milestones?limit=200`); } catch (e) { ms = []; }
  $("#chronicle").innerHTML = ms.slice().reverse().map((m) =>
    `<div class="ms-row"><span class="t">t ${fmt(m.tick)}</span><span class="lb">${m.label || m.kind}</span></div>`).join("")
    || '<div style="color:var(--muted)">La historia aún no comienza…</div>';
}
function line(id, xs, series) {
  const cv = document.getElementById(id), dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight || 76; cv.width = w * dpr; cv.height = h * dpr;
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  let mx = 0; series.forEach((s) => s.v.forEach((v) => { if (v > mx) mx = v; })); if (mx <= 0) mx = 1;
  const pad = 6, n = xs.length;
  series.forEach((s) => {
    ctx.beginPath(); ctx.strokeStyle = s.c; ctx.lineWidth = 1.5;
    s.v.forEach((v, i) => { const px = pad + i / Math.max(1, n - 1) * (w - 2 * pad), py = h - pad - v / mx * (h - 2 * pad);
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
    ctx.stroke();
  });
  ctx.fillStyle = "#7688a0"; ctx.font = "9px sans-serif"; ctx.fillText(String(mx.toFixed(2)), 3, 10);
}

/* ---------------------------------------------------------- audio ------ */
async function pollAudioInteractions() {
  if (!S.current || !S.soundOn) return;
  let d; try { d = await api(`/api/simulations/${S.current}/interactions?type=${encodeURIComponent("señal")}&limit=25`); }
  catch (e) { return; }
  for (const ev of d) {
    if (S.seenInteractionIds.has(ev.id)) continue;
    S.seenInteractionIds.add(ev.id);
    if (ev.signal == null) continue;
    let priority = 0;
    if (S.selectedAgentId != null && (ev.agent_id === S.selectedAgentId || ev.target_id === S.selectedAgentId)) priority = 2;
    else priority = 1;
    MVAudio.play(ev.signal, priority);
  }
  if (S.seenInteractionIds.size > 2000) {
    S.seenInteractionIds = new Set(Array.from(S.seenInteractionIds).slice(-500));
  }
}

function fmt(n) {
  if (n == null) return "0";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}

boot();
