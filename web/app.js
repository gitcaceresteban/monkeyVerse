/* monkeyVerse observer UI — vanilla JS, no external dependencies. */
"use strict";

const $ = (s) => document.querySelector(s);
const api = (p, o) => fetch(p, o).then((r) => (r.ok ? r.json() : Promise.reject(r)));

const S = {
  sims: [],
  current: null,      // sim id
  ws: null,
  state: null,        // latest render frame
  schema: null,
  placeMode: null,    // e.g. "food" -> next canvas click seeds food
  tab: "live",
};

/* ------------------------------------------------------------------ boot */
async function boot() {
  const cfg = await api("/api/config/schema");
  S.schema = cfg;
  buildForm(cfg);
  await refreshList();
  setInterval(refreshList, 4000);

  $("#newBtn").onclick = openModal;
  $("#emptyNew").onclick = openModal;
  $("#cancelBtn").onclick = closeModal;
  $("#modalBg").onclick = (e) => { if (e.target.id === "modalBg") closeModal(); };
  $("#createBtn").onclick = createSim;
  $("#pauseBtn").onclick = togglePause;
  $("#deleteBtn").onclick = deleteSim;
  $("#insClose").onclick = () => $("#inspector").classList.remove("show");
  $("#refreshHist").onclick = loadHistory;

  $("#speed").oninput = (e) => { $("#speedVal").textContent = e.target.value + " p/s"; };
  $("#speed").onchange = (e) => control("speed", parseFloat(e.target.value));

  document.querySelectorAll("[data-iv]").forEach((b) => {
    b.onclick = () => intervene(b.dataset.iv);
  });
  document.querySelectorAll(".tabbar button").forEach((b) => {
    b.onclick = () => selectTab(b.dataset.tab);
  });

  const cv = $("#world");
  cv.addEventListener("click", onCanvasClick);
  window.addEventListener("resize", () => S.state && render(S.state));
  requestAnimationFrame(loop);
}

/* ------------------------------------------------------------ config form */
function buildForm(cfg) {
  const grid = $("#formGrid");
  grid.innerHTML = "";
  cfg.schema.forEach((f) => {
    const div = document.createElement("div");
    div.className = "field";
    const help = f.help ? `<div class="help">${f.help}</div>` : "";
    const step = f.step || (f.type === "float" ? "any" : "1");
    const min = f.min !== undefined ? `min="${f.min}"` : "";
    const max = f.max !== undefined ? `max="${f.max}"` : "";
    const val = cfg.defaults[f.key];
    const type = f.type === "text" ? "text" : "number";
    div.innerHTML =
      `<label>${f.label}</label>
       <input data-key="${f.key}" data-type="${f.type}" type="${type}"
              value="${val}" ${min} ${max} step="${step}">${help}`;
    grid.appendChild(div);
  });
}

function readForm() {
  const out = {};
  document.querySelectorAll("#formGrid input").forEach((inp) => {
    const t = inp.dataset.type;
    let v = inp.value;
    if (t === "int") v = parseInt(v, 10);
    else if (t === "float") v = parseFloat(v);
    out[inp.dataset.key] = v;
  });
  return out;
}

function openModal() {
  // fresh random name each time
  const inp = document.querySelector('#formGrid input[data-key="name"]');
  if (inp) inp.value = "mundo-" + Math.random().toString(36).slice(2, 6);
  $("#modalBg").classList.add("open");
}
function closeModal() { $("#modalBg").classList.remove("open"); }

async function createSim() {
  const cfg = readForm();
  $("#createBtn").disabled = true;
  try {
    const { id } = await api("/api/simulations", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
    closeModal();
    await refreshList();
    selectSim(id);
  } catch (e) { alert("No se pudo crear el mundo."); }
  $("#createBtn").disabled = false;
}

/* ---------------------------------------------------------- sim list */
async function refreshList() {
  try {
    S.sims = await api("/api/simulations");
  } catch (e) { return; }
  const list = $("#simList");
  list.innerHTML = "";
  S.sims.forEach((s) => {
    const el = document.createElement("div");
    el.className = "sim-card " + s.status + (s.id === S.current ? " active" : "");
    el.onclick = () => selectSim(s.id);
    el.innerHTML =
      `<div class="name">${s.name}<span class="dot"></span></div>
       <div class="meta">
         <span><b>${s.population}</b> vivos</span>
         <span>gen <b>${s.max_generation}</b></span>
         <span>t <b>${fmt(s.tick)}</b></span>
       </div>
       <div class="meta">
         <span>♁ ${fmt(s.births_total)}</span>
         <span>✝ ${fmt(s.deaths_total)}</span>
         <span>${s.event !== "estable" ? "⚠ " + s.event : ""}</span>
       </div>`;
    list.appendChild(el);
  });
  if (!S.current && S.sims.length === 0) showEmpty(true);
}

/* ---------------------------------------------------------- selection */
function selectSim(id) {
  if (S.current === id) return;
  S.current = id;
  showEmpty(false);
  $("#controls").style.display = "flex";
  $("#rightbar").style.display = "flex";
  $("#inspector").classList.remove("show");
  connectWS(id);
  refreshList();
  const s = S.sims.find((x) => x.id === id);
  if (s) {
    $("#speed").value = s.target_sps;
    $("#speedVal").textContent = s.target_sps + " p/s";
    $("#pauseBtn").textContent = s.status === "paused" ? "▶ Reanudar" : "⏸ Pausar";
  }
  if (S.tab === "history") loadHistory();
  if (S.tab === "events") loadEvents();
}

function showEmpty(on) {
  $("#empty").style.display = on ? "flex" : "none";
  $("#hud").style.display = on ? "none" : "flex";
}

/* ---------------------------------------------------------- websocket */
function connectWS(id) {
  if (S.ws) { try { S.ws.close(); } catch (e) {} S.ws = null; }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${id}`);
  S.ws = ws;
  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.error) return;
    if (S.current !== id) return;
    S.state = data;
    updateHUD(data);
    updateStats(data);
  };
  ws.onclose = () => { if (S.current === id) setTimeout(() => connectWS(id), 1500); };
}

/* ---------------------------------------------------------- render loop */
function loop() {
  if (S.state) render(S.state);
  requestAnimationFrame(loop);
}

function render(state) {
  const cv = $("#world");
  const stage = $("#stage");
  const dpr = window.devicePixelRatio || 1;
  const w = stage.clientWidth, h = stage.clientHeight;
  if (cv.width !== w * dpr || cv.height !== h * dpr) {
    cv.width = w * dpr; cv.height = h * dpr;
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#070b10";
  ctx.fillRect(0, 0, w, h);

  // food field
  const food = state.food;
  if (food && food.length) {
    const rows = food.length, cols = food[0].length;
    const cw = w / cols, ch = h / rows;
    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        const v = food[i][j];
        if (v <= 0.01) continue;
        const g = Math.floor(40 + v * 150);
        ctx.fillStyle = `rgb(${Math.floor(20 + v * 30)},${g},${Math.floor(40 + v * 60)})`;
        ctx.globalAlpha = 0.35 + v * 0.5;
        ctx.fillRect(j * cw, i * ch, cw + 1, ch + 1);
      }
    }
    ctx.globalAlpha = 1;
  }

  // agents
  const sx = w / state.width, sy = h / state.height;
  const agents = state.agents || [];
  for (const a of agents) {
    const [x, y, hue, e, gen] = a;
    const px = x * sx, py = y * sy;
    const r = 1.6 + e * 3.2;
    ctx.beginPath();
    ctx.arc(px, py, r, 0, 6.2832);
    ctx.fillStyle = `hsl(${Math.floor(hue * 360)}, 75%, ${40 + e * 25}%)`;
    ctx.fill();
  }
}

/* ---------------------------------------------------------- HUD + stats */
function updateHUD(state) {
  const st = state.stats, rn = state.runner || {};
  const ev = st.event && st.event !== "estable"
    ? `<div class="chip event">⚠ ${st.event}</div>` : "";
  $("#hud").innerHTML =
    `<div class="chip">🕒 t <b>${fmt(state.tick)}</b></div>
     <div class="chip">👥 <b>${st.population}</b></div>
     <div class="chip">🧬 gen <b>${st.max_generation}</b></div>
     <div class="chip">⚡ <b>${st.avg_energy}</b></div>
     <div class="chip">📡 <b>${(st.signal_activity * 1000).toFixed(1)}</b>‰</div>
     <div class="chip">${(rn.real_sps || 0).toFixed(0)} p/s real</div>
     ${ev}`;
}

function updateStats(state) {
  if (S.tab !== "live") return;
  const st = state.stats;
  const g = $("#statgrid");
  const cells = [
    ["Población", st.population], ["Gen. máx.", st.max_generation],
    ["Nacim. (int.)", st.births], ["Muertes (int.)", st.deaths],
    ["Energía media", st.avg_energy], ["Edad media", st.avg_age],
  ];
  g.innerHTML = cells.map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");

  const gm = st.gene_means || {};
  const bounds = {
    metabolism: [0.4, 1.8], diet_efficiency: [0.5, 1.6], repro_threshold: [35, 220],
    repro_investment: [0.2, 0.7], max_age: [400, 5000], mutation_rate: [0, 0.5], hue: [0, 1],
  };
  const names = {
    metabolism: "metabolismo", diet_efficiency: "digestión", repro_threshold: "umbral repr.",
    repro_investment: "inversión", max_age: "longevidad", mutation_rate: "mutación", hue: "color",
  };
  $("#genes").innerHTML = Object.keys(bounds).map((k) => {
    const [lo, hi] = bounds[k];
    const v = gm[k] || 0;
    const pct = Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));
    return `<div class="gene-row"><span class="lbl">${names[k]}</span>
      <span class="bar"><div style="width:${pct}%"></div></span>
      <span class="val">${v.toFixed(2)}</span></div>`;
  }).join("");
}

/* ---------------------------------------------------------- controls */
async function control(action, value) {
  if (!S.current) return;
  await api(`/api/simulations/${S.current}/control`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, value }),
  }).catch(() => {});
}

function togglePause() {
  const s = S.sims.find((x) => x.id === S.current);
  if (!s) return;
  const paused = s.status === "paused";
  control(paused ? "resume" : "pause");
  s.status = paused ? "running" : "paused";
  $("#pauseBtn").textContent = paused ? "⏸ Pausar" : "▶ Reanudar";
}

async function deleteSim() {
  if (!S.current || !confirm("¿Eliminar este mundo y toda su historia?")) return;
  await api(`/api/simulations/${S.current}`, { method: "DELETE" }).catch(() => {});
  if (S.ws) { try { S.ws.close(); } catch (e) {} }
  S.current = null; S.state = null;
  $("#controls").style.display = "none";
  $("#rightbar").style.display = "none";
  showEmpty(true);
  refreshList();
}

function intervene(kind) {
  if (kind === "food") {
    S.placeMode = "food";
    $("#hud").insertAdjacentHTML("beforeend",
      '<div class="chip" id="placeHint">👆 Clic en el mundo para sembrar</div>');
    return;
  }
  api(`/api/simulations/${S.current}/intervene`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, params: {} }),
  }).catch(() => {});
}

function onCanvasClick(e) {
  if (!S.state) return;
  const cv = $("#world");
  const rect = cv.getBoundingClientRect();
  const wx = Math.floor((e.clientX - rect.left) / rect.width * S.state.width);
  const wy = Math.floor((e.clientY - rect.top) / rect.height * S.state.height);

  if (S.placeMode === "food") {
    S.placeMode = null;
    const h = $("#placeHint"); if (h) h.remove();
    api(`/api/simulations/${S.current}/intervene`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "food", params: { x: wx, y: wy, radius: 7, amount: 1.5 } }),
    }).catch(() => {});
    return;
  }
  // otherwise: inspect nearest agent
  inspectNear(wx, wy);
}

async function inspectNear(wx, wy) {
  const agents = S.state.agents || [];
  let best = null, bd = 1e9;
  for (const a of agents) {
    const d = (a[0] - wx) ** 2 + (a[1] - wy) ** 2;
    if (d < bd) { bd = d; best = a; }
  }
  if (!best || bd > 25) { $("#inspector").classList.remove("show"); return; }
  // find id via detail endpoint search: we only have coords, so approximate by
  // asking the server for the nearest? Instead we scan the live agents by position.
  // The server exposes agent by id; we don't have id here, so show local info.
  const [x, y, hue, e, gen] = best;
  $("#insTitle").textContent = "Individuo · gen " + gen;
  $("#insBody").innerHTML =
    `<div class="row">Posición <b>${x}, ${y}</b></div>
     <div class="row">Generación <b>${gen}</b></div>
     <div class="row">Energía <b>${(e * 120).toFixed(0)}</b></div>
     <div class="row">Linaje (color) <b><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:hsl(${Math.floor(hue*360)},75%,55%)"></span></b></div>
     <div class="row" style="margin-top:6px;color:var(--muted);font-size:10.5px">El color codifica el linaje: individuos del mismo tono comparten ascendencia.</div>`;
  $("#inspector").classList.add("show");
}

/* ---------------------------------------------------------- tabs / history */
function selectTab(tab) {
  S.tab = tab;
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
  if (tab === "history") loadHistory();
  if (tab === "events") loadEvents();
}

async function loadHistory() {
  if (!S.current) return;
  let data;
  try { data = await api(`/api/simulations/${S.current}/stats?limit=3000`); }
  catch (e) { return; }
  if (!data.length) return;
  const ticks = data.map((d) => d.tick);
  lineChart("chartPop", ticks, [{ v: data.map((d) => d.population), c: "#4dd6a8" }]);
  lineChart("chartBD", ticks, [
    { v: data.map((d) => d.births), c: "#6aa8ff" },
    { v: data.map((d) => d.deaths), c: "#ff6b6b" },
  ]);
  lineChart("chartGen", ticks, [{ v: data.map((d) => d.max_generation), c: "#ffcf5c" }]);
  lineChart("chartSig", ticks, [{ v: data.map((d) => d.signal_activity), c: "#c58bff" }]);
}

async function loadEvents() {
  if (!S.current) return;
  let evs;
  try { evs = await api(`/api/simulations/${S.current}/events?limit=80`); }
  catch (e) { return; }
  const icon = { climate: "🌍", intervention: "✋" };
  $("#eventLog").innerHTML = evs.map((e) => {
    const label = e.type === "climate" ? e.data.name
      : e.type === "intervention" ? e.data.kind : e.type;
    return `<div class="ev"><span class="t">t ${fmt(e.tick)}</span>
      <span>${icon[e.type] || "•"} ${label}</span></div>`;
  }).join("") || '<div style="color:var(--muted)">Sin eventos aún.</div>';
}

/* ---------------------------------------------------------- mini charts */
function lineChart(id, xs, series) {
  const cv = document.getElementById(id);
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight || 90;
  cv.width = w * dpr; cv.height = h * dpr;
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  let max = 0;
  series.forEach((s) => s.v.forEach((v) => { if (v > max) max = v; }));
  if (max <= 0) max = 1;
  const pad = 6;
  const n = xs.length;
  series.forEach((s) => {
    ctx.beginPath();
    ctx.strokeStyle = s.c; ctx.lineWidth = 1.6;
    s.v.forEach((v, i) => {
      const px = pad + (i / Math.max(1, n - 1)) * (w - 2 * pad);
      const py = h - pad - (v / max) * (h - 2 * pad);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    });
    ctx.stroke();
  });
  ctx.fillStyle = "#7d8ba0"; ctx.font = "9px sans-serif";
  ctx.fillText(String(Math.round(max)), 3, 10);
}

/* ---------------------------------------------------------- utils */
function fmt(n) {
  if (n == null) return "0";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}

boot();
