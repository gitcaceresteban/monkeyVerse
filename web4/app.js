/* monkeyVerse v4 — Isla Simple. Front-end: renders the island, streams world
 * state over a WebSocket, lets you select & follow an agent, plays a tone per
 * sound, and shows the communication / reproduction / analysis reports. All
 * vanilla JS, no external dependencies (works offline on the Raspberry Pi). */
"use strict";

const S = {
  simId: null, ws: null, wsGen: 0,
  mapSize: 50, land: null, veg: null,
  agents: [], sounds: [], links: [], metrics: {}, runner: {},
  selectedId: null, following: false, debug: false,
  camera: { x: 0, y: 0, scale: 1 },
  lastAgentFetch: 0, lastTabFetch: 0, activeTab: "agent",
  prevSoundKey: "",
};

const $ = (id) => document.getElementById(id);
const api = (p) => `/api/simulations/${S.simId}${p}`;

/* ------------------------------------------------------------------ boot */
async function boot() {
  wireControls();
  buildSpeedButtons();
  let sims = await fetch("/api/simulations").then((r) => r.json()).catch(() => []);
  const saved = localStorage.getItem("mv4.sim");
  let pick = sims.find((s) => s.id === saved) || sims[0];
  if (!pick) {
    const res = await fetch("/api/simulations", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: "{}" }).then((r) => r.json());
    pick = { id: res.id };
  }
  await selectSim(pick.id);
}

async function selectSim(id) {
  S.simId = id;
  localStorage.setItem("mv4.sim", id);
  S.selectedId = null; S.following = false; renderFollowBadge();
  const isl = await fetch(api("/island")).then((r) => r.json());
  S.mapSize = isl.size; S.land = isl.land; S.veg = isl.veg;
  openWs();
  refreshTab(true);
}

/* ------------------------------------------------------------------ websocket */
function openWs() {
  if (S.ws) { try { S.ws.close(); } catch (e) {} }
  const gen = ++S.wsGen;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${S.simId}`);
  S.ws = ws;
  ws.onmessage = (ev) => {
    if (gen !== S.wsGen) return;
    const st = JSON.parse(ev.data);
    if (st.error) return;
    onState(st);
  };
  ws.onclose = () => { if (gen === S.wsGen) setTimeout(openWs, 1000); };
}

function onState(st) {
  S.agents = st.agents || [];
  S.sounds = st.sounds || [];
  S.links = st.links || [];
  S.metrics = st.metrics || {};
  S.runner = st.runner || {};
  if (st.veg) S.veg = st.veg;
  updateTopbar();
  playSounds();
  draw();
  // keep the agent panel & tabs fresh at a gentle cadence
  const now = performance.now();
  if (S.selectedId != null && now - S.lastAgentFetch > 700) { S.lastAgentFetch = now; fetchAgent(); }
  if (now - S.lastTabFetch > 1500) { S.lastTabFetch = now; refreshTab(false); }
  reflectSpeed();
}

/* ------------------------------------------------------------------ topbar */
function updateTopbar() {
  const m = S.metrics;
  $("m-tick").textContent = m.tick ?? 0;
  $("m-pop").textContent = m.population ?? 0;
  $("m-a").textContent = m.sex_a ?? 0;
  $("m-b").textContent = m.sex_b ?? 0;
  $("m-births").textContent = m.births ?? 0;
  $("m-deaths").textContent = m.deaths ?? 0;
  $("m-repro").textContent = m.reproductions ?? 0;
  $("m-veg").textContent = Math.round(m.veg_total ?? 0);
  $("m-int").textContent = m.interactions_interval ?? 0;
  $("m-snd").textContent = m.sounds_interval ?? 0;
  $("m-div").textContent = (m.lang_diversity ?? 0).toFixed(2);
}

function buildSpeedButtons() {
  const presets = [["⏸", 0], ["0.5×", 0.5], ["1×", 1], ["2×", 2], ["5×", 5]];
  const box = $("speeds");
  box.innerHTML = "";
  presets.forEach(([label, val]) => {
    const b = document.createElement("button");
    b.textContent = label; b.dataset.speed = val;
    b.onclick = () => setSpeed(val);
    box.appendChild(b);
  });
}

async function setSpeed(v) {
  await fetch(api("/speed"), { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ speed: v }) });
  reflectSpeed(v);
}

function reflectSpeed(force) {
  const spd = force != null ? force : (S.runner.speed ?? 1);
  document.querySelectorAll("#speeds button").forEach((b) => {
    b.classList.toggle("active", parseFloat(b.dataset.speed) === spd);
  });
}

/* ------------------------------------------------------------------ canvas */
const cv = $("canvas");
const ctx = cv.getContext("2d");
let DPR = window.devicePixelRatio || 1;

function fit() {
  DPR = window.devicePixelRatio || 1;
  const r = cv.parentElement.getBoundingClientRect();
  cv.width = Math.floor(r.width * DPR); cv.height = Math.floor(r.height * DPR);
  draw();
}
window.addEventListener("resize", fit);

function computeCamera() {
  const W = cv.width, H = cv.height, n = S.mapSize;
  let base = Math.min(W, H) / n;
  let scale = base, cx = W / 2, cy = H / 2, wx = n / 2, wy = n / 2;
  if (S.following && S.selectedId != null) {
    const a = S.agents.find((x) => x.id === S.selectedId);
    if (a) { scale = base * 2.0; wx = a.x; wy = a.y; }
  }
  S.camera = { scale, cx, cy, wx, wy };
}
function w2s(x, y) {
  const c = S.camera;
  return [c.cx + (x - c.wx) * c.scale, c.cy + (y - c.wy) * c.scale];
}
function s2w(sx, sy) {
  const c = S.camera;
  return [(sx - c.cx) / c.scale + c.wx, (sy - c.cy) / c.scale + c.wy];
}

function draw() {
  if (!S.land) return;
  computeCamera();
  const W = cv.width, H = cv.height, n = S.mapSize, sc = S.camera.scale;
  ctx.fillStyle = "#0a1622"; ctx.fillRect(0, 0, W, H);
  // water + land + vegetation
  const cell = sc * 1.02;
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const [sx, sy] = w2s(x, y);
      if (sx < -cell || sy < -cell || sx > W + cell || sy > H + cell) continue;
      const isLand = S.land[y][x];
      if (!isLand) { ctx.fillStyle = "#12314e"; }
      else {
        const v = S.veg ? S.veg[y][x] : 0;
        if (v > 0.02) {
          const g = Math.min(1, v);
          ctx.fillStyle = `rgb(${Math.round(30 + 20 * g)},${Math.round(70 + 110 * g)},${Math.round(50 + 30 * g)})`;
        } else ctx.fillStyle = "#1d3324";
      }
      ctx.fillRect(sx - cell / 2, sy - cell / 2, cell, cell);
    }
  }
  // interaction links
  ctx.lineWidth = Math.max(1, sc * 0.18); ctx.strokeStyle = "rgba(255,209,102,.7)";
  for (const l of S.links) {
    const [x1, y1] = w2s(l[0], l[1]); const [x2, y2] = w2s(l[2], l[3]);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }
  // agents
  for (const a of S.agents) {
    const [sx, sy] = w2s(a.x, a.y);
    const rad = Math.max(3, sc * 0.42);
    const base = a.sex === "A" ? [255, 138, 92] : [87, 199, 255];
    ctx.beginPath(); ctx.arc(sx, sy, rad, 0, 7);
    ctx.fillStyle = `rgb(${base[0]},${base[1]},${base[2]})`;
    ctx.globalAlpha = 0.45 + 0.55 * Math.min(1, (a.energy || 0) / 90);
    ctx.fill(); ctx.globalAlpha = 1;
    // sex ring
    ctx.lineWidth = Math.max(1, sc * 0.1);
    ctx.strokeStyle = a.sex === "A" ? "#ffb999" : "#a9e2ff"; ctx.stroke();
    if (a.gen > 0) { // small mark for born-in-world agents
      ctx.fillStyle = "rgba(255,255,255,.85)";
      ctx.beginPath(); ctx.arc(sx, sy - rad - 2, Math.max(1, sc * 0.09), 0, 7); ctx.fill();
    }
    // selection
    if (a.id === S.selectedId) {
      ctx.strokeStyle = "#ffd166"; ctx.lineWidth = Math.max(1.5, sc * 0.16);
      ctx.beginPath(); ctx.arc(sx, sy, rad + sc * 0.35, 0, 7); ctx.stroke();
    }
    // sound bubble
    if (a.last_sound != null && a.last_sound >= 0) {
      drawSound(sx, sy - rad - sc * 0.6, a.last_sound, sc);
    }
  }
}

function drawSound(sx, sy, sound, sc) {
  const r = Math.max(7, sc * 0.5);
  ctx.beginPath(); ctx.arc(sx, sy, r, 0, 7);
  ctx.fillStyle = "rgba(12,22,34,.92)"; ctx.fill();
  ctx.strokeStyle = "#7cc4ff"; ctx.lineWidth = 1.4; ctx.stroke();
  ctx.fillStyle = "#dff1ff"; ctx.font = `700 ${Math.max(9, r)}px ui-monospace, monospace`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(sound), sx, sy + 0.5);
}

/* click to select ------------------------------------------------------- */
cv.addEventListener("click", (e) => {
  const r = cv.getBoundingClientRect();
  const sx = (e.clientX - r.left) * DPR, sy = (e.clientY - r.top) * DPR;
  const [wx, wy] = s2w(sx, sy);
  let best = null, bd = 2.2;
  for (const a of S.agents) {
    const d = Math.hypot(a.x - wx, a.y - wy);
    if (d < bd) { bd = d; best = a; }
  }
  if (best) { S.selectedId = best.id; S.following = true; renderFollowBadge();
    setTab("agent"); fetchAgent(); }
});

function renderFollowBadge() {
  const badge = $("follow-badge");
  if (S.following && S.selectedId != null) {
    badge.classList.remove("hidden"); $("follow-id").textContent = "#" + S.selectedId;
  } else badge.classList.add("hidden");
}

/* ------------------------------------------------------------------ audio */
function playSounds() {
  if (!MVAudio.isEnabled() || !S.sounds.length) return;
  const key = S.metrics.tick + ":" + S.sounds.map((s) => s.id + "-" + s.sound).join(",");
  if (key === S.prevSoundKey) return;
  S.prevSoundKey = key;
  const sel = S.selectedId != null ? S.agents.find((a) => a.id === S.selectedId) : null;
  for (const s of S.sounds) {
    let loud = 0.28, prio = 0;
    if (sel) {
      const d = Math.hypot(s.x - sel.x, s.y - sel.y);
      loud = Math.max(0.12, 0.6 - d / 20);
      if (s.id === sel.id) { loud = 0.6; prio = 2; }
      else if (d < 9) prio = 1;
    }
    MVAudio.play(s.sound, loud, prio);
  }
}

/* ------------------------------------------------------------------ agent panel */
async function fetchAgent() {
  if (S.selectedId == null) return;
  const d = await fetch(api(`/agent/${S.selectedId}`)).then((r) => r.ok ? r.json() : null).catch(() => null);
  const body = $("agent-body"), empty = $("agent-empty");
  if (!d) { // died
    body.classList.add("hidden"); empty.classList.remove("hidden");
    empty.innerHTML = `El agente #${S.selectedId} ya no está vivo.<br><span class="mut">Falleció o salió del mundo.</span>`;
    return;
  }
  empty.classList.add("hidden"); body.classList.remove("hidden");
  body.innerHTML = agentHtml(d);
  // clickable sound chips (audition)
  body.querySelectorAll(".snd[data-s]").forEach((el) =>
    el.onclick = () => MVAudio.play(parseInt(el.dataset.s), 0.6, 2));
  body.querySelectorAll("[data-goto]").forEach((el) =>
    el.onclick = () => { S.selectedId = parseInt(el.dataset.goto); S.following = true;
      renderFollowBadge(); fetchAgent(); });
}

function bar(v, color, max = 1) {
  const pct = Math.max(0, Math.min(100, (v / max) * 100));
  return `<div class="bar"><i style="width:${pct}%;background:${color}"></i></div>`;
}

function agentHtml(d) {
  const sexPill = `<span class="pill ${d.sex.toLowerCase()}">${d.sex}</span>`;
  let h = `<div class="card"><h3>Agente #${d.id} ${sexPill}
     <span class="mut">· gen ${d.generation}</span></h3>
    <div class="kv"><span>Estado</span><span>${d.state}</span></div>
    <div class="kv"><span>Energía</span><span>${d.energy.toFixed(1)}</span></div>
    ${bar(d.energy, "var(--veg)", 120)}
    <div class="kv"><span>Hambre</span><span>${(d.hunger*100|0)}%</span></div>
    <div class="kv"><span>Edad</span><span>${d.age} ${d.mature ? "· maduro" : "· joven"}</span></div>
    <div class="kv"><span>Posición</span><span>${d.x.toFixed(1)}, ${d.y.toFixed(1)}</span></div>
    <div class="kv"><span>Hijos</span><span>${d.n_children}</span></div>
    <div class="kv"><span>Recompensa total</span><span>${d.reward_total.toFixed(1)}</span></div>
    <div class="kv"><span>Interacciones · sonidos</span><span>${d.n_interactions} · ${d.n_sounds}</span></div>
    ${d.repro_cd > 0 ? `<div class="kv"><span>Cooldown repr.</span><span>${d.repro_cd}</span></div>` : ""}
    ${d.parent_a ? `<div class="kv"><span>Padres</span><span>
        <a href="#" data-goto="${d.parent_a}">#${d.parent_a}</a> ·
        <a href="#" data-goto="${d.parent_b}">#${d.parent_b}</a></span></div>` : ""}
  </div>`;

  // genes
  h += `<div class="card"><h3>Genes (fisiología)</h3>`;
  for (const [k, v] of Object.entries(d.genes)) {
    if (k === "hue") continue;
    h += `<div class="kv"><span>${k}</span><span>${v.toFixed(2)}</span></div>`;
  }
  h += `</div>`;

  // sounds emitted / heard
  h += `<div class="card"><h3>Últimos sonidos emitidos</h3><div class="sounds-row">`;
  h += d.emitted.length ? d.emitted.slice(-10).map((e) =>
    `<div class="snd" data-s="${e.sound}">${e.sound}</div>`).join("")
    : `<span class="mut">todavía ninguno</span>`;
  h += `</div><h3 style="margin-top:8px">Últimos oídos</h3><div class="sounds-row">`;
  h += d.heard.length ? d.heard.slice(-10).map((e) =>
    `<div class="snd" data-s="${e.sound}">${e.sound}<small>#${e.from}</small></div>`).join("")
    : `<span class="mut">nada por ahora</span>`;
  h += `</div></div>`;

  // relationships
  h += `<div class="card"><h3>Relaciones (${d.memory.distinct_known})</h3>`;
  if (d.relationships.length) {
    for (const r of d.relationships.slice(0, 8)) {
      h += `<div class="rel"><a href="#" data-goto="${r.agent_id}">#${r.agent_id}</a>
        <span title="afinidad">${bar((r.affinity+1)/2, r.affinity>=0?"var(--ok)":"var(--heart)")}</span>
        <span class="mut">af ${r.affinity.toFixed(2)} · fam ${r.familiarity.toFixed(2)}
        · +${r.positive}/-${r.negative} · 🔊${r.sounds_heard}</span></div>`;
    }
  } else h += `<span class="mut">sin relaciones aún</span>`;
  h += `</div>`;

  // nearby
  h += `<div class="card"><h3>Cerca</h3>`;
  if (d.nearby.length) {
    for (const nb of d.nearby.slice(0, 6))
      h += `<div class="kv"><span><a href="#" data-goto="${nb.id}">#${nb.id}</a>
        <span class="pill ${nb.sex.toLowerCase()}">${nb.sex}</span></span>
        <span class="mut">${nb.dist} celdas · ${nb.state} · af ${nb.affinity.toFixed(2)}</span></div>`;
  } else h += `<span class="mut">nadie a la vista</span>`;
  h += `</div>`;

  // debug: why it did what it did
  if (S.debug && d.debug) {
    h += `<div class="card debug"><h3>🐞 Decisión (por qué)</h3>
      <div class="mut">Acción: <b>${d.debug.chosen}</b> · recompensa ${d.debug.last_reward}
      · plasticidad ${d.memory.fast_weight_norm}</div>
      <h3 style="margin-top:8px">Salidas más activas</h3><div class="io">`;
    for (const [k, v] of d.debug.top_outputs)
      h += `<div class="k">${k}</div><div class="v ${v>0.5?"hot":""}">${v.toFixed(2)}</div>`;
    h += `</div><h3 style="margin-top:8px">Entradas</h3><div class="io">`;
    for (const [k, v] of d.debug.inputs)
      h += `<div class="k">${k}</div><div class="v">${v.toFixed(2)}</div>`;
    h += `</div></div>`;
  }
  return h;
}

/* ------------------------------------------------------------------ tabs */
function setTab(name) {
  S.activeTab = name;
  document.querySelectorAll("#tabs button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.id === "tab-" + name));
  refreshTab(true);
}

async function refreshTab(force) {
  const t = S.activeTab;
  if (t === "comm") renderComm(await fetch(api("/communication")).then((r) => r.json()).catch(() => null));
  else if (t === "repro") renderRepro(await fetch(api("/reproduction")).then((r) => r.json()).catch(() => null));
  else if (t === "analysis") renderAnalysis(await fetch(api("/analysis")).then((r) => r.json()).catch(() => null));
}

function renderComm(c) {
  if (!c) return;
  const el = $("comm-body");
  let h = `<div class="card"><h3>Resumen</h3>
    <div class="kv"><span>Sonidos emitidos</span><span>${c.sounds_total}</span></div>
    <div class="kv"><span>Más usado</span><span>${c.most_used ?? "—"}</span></div>
    <div class="kv"><span>Diversidad (entropía)</span><span>${c.diversity.toFixed(3)}</span></div>
    <div class="kv"><span>Información mutua (sonido↔contexto)</span><span>${c.mutual_information.toFixed(3)}</span></div>
    </div>`;
  // per-sound usage
  h += `<div class="card"><h3>Uso por sonido</h3>`;
  const max = Math.max(1, ...c.emit_counts);
  for (let s = 0; s < c.emit_counts.length; s++) {
    h += `<div class="rel"><div class="snd" data-s="${s}">${s}</div>
      <span>${bar(c.emit_counts[s], "#57c7ff", max)}</span>
      <span class="mut">${c.emit_counts[s]}</span></div>`;
  }
  h += `</div>`;
  // emergent meaning
  if (c.emergent_meaning && c.emergent_meaning.length) {
    h += `<div class="card meaning"><h3>⚑ Posible significado emergente</h3>`;
    for (const m of c.emergent_meaning)
      h += `<div class="kv"><span>Sonido <b>${m.sound}</b> → «${m.context}»</span>
        <span>${(m.strength*100|0)}% · ×${m.lift} · n=${m.n}</span></div>`;
    h += `<div class="mut" style="margin-top:6px">Marcado sólo porque supera claramente la
      frecuencia base. Sigue siendo correlación, no un significado impuesto.</div></div>`;
  } else {
    h += `<div class="card"><div class="mut">Todavía no hay evidencia estadística de que
      ningún sonido tenga un significado fijo. Los agentes siguen usándolos de forma
      ambigua.</div></div>`;
  }
  // per-sound context/response detail
  h += `<div class="card"><h3>Contexto y respuesta por sonido</h3>`;
  for (const row of c.per_sound) {
    if (!row.context && !row.response) continue;
    h += `<div style="margin:6px 0"><b>Sonido ${row.sound}</b>
      <span class="mut">(emitido ${row.emitted}, oído ${row.heard})</span>`;
    if (row.context) h += `<div class="mut">contexto: ` +
      Object.entries(row.context).map(([k, v]) => `${k} ${(v*100|0)}%`).join(" · ") + `</div>`;
    if (row.response) h += `<div class="mut">respuesta: ` +
      Object.entries(row.response).map(([k, v]) => `${k} ${(v*100|0)}%`).join(" · ") + `</div>`;
    h += `</div>`;
  }
  h += `</div>`;
  el.innerHTML = h;
  el.querySelectorAll(".snd[data-s]").forEach((x) =>
    x.onclick = () => MVAudio.play(parseInt(x.dataset.s), 0.6, 2));
}

function renderRepro(r) {
  if (!r) return;
  let h = `<div class="card"><h3>Reproducción</h3>
    <div class="kv"><span>Intentos</span><span>${r.attempts}</span></div>
    <div class="kv"><span>Éxitos</span><span>${r.successes}</span></div>
    <div class="kv"><span>Afinidad media previa</span><span>${r.avg_affinity_before.toFixed(3)}</span></div>
    <div class="kv"><span>Parejas con señales previas</span><span>${(r.signals_fraction*100|0)}%</span></div>
    <div class="kv"><span>Generación máxima</span><span>${r.max_generation}</span></div>
    <div class="kv"><span>Generaciones presentes</span><span>${r.generations_present.join(", ")}</span></div>
  </div>`;
  h += `<div class="card"><h3>Requisitos (no basta la cercanía)</h3>
    <div class="mut">Sexos distintos · maduros · energía ≥ ${r.min_energy} · afinidad ≥ ${r.min_affinity}
      · ≥ ${r.min_interactions} interacciones · ≥ ${r.min_signals} señal · fuera de cooldown ·
      ambos eligen reproducirse.</div></div>`;
  h += `<div class="card"><h3>Parejas más fecundas (vivas)</h3>`;
  if (r.top_pairs.length) {
    for (const p of r.top_pairs)
      h += `<div class="kv"><span>#${p.parents[0]} × #${p.parents[1]}</span><span>${p.children} 🐣</span></div>`;
  } else h += `<span class="mut">aún sin descendencia registrada entre los vivos</span>`;
  h += `</div>`;
  $("repro-body").innerHTML = h;
}

function renderAnalysis(a) {
  if (!a) return;
  let h = `<div class="card"><h3>Estado del mundo</h3>
    <div class="kv"><span>Población</span><span>${a.population} (A ${a.sex_a} · B ${a.sex_b})</span></div>
    <div class="kv"><span>Nacimientos · muertes</span><span>${a.births} · ${a.deaths}</span></div>
    <div class="kv"><span>Reproducciones</span><span>${a.reproductions}</span></div>
    <div class="kv"><span>Generación máxima</span><span>${a.max_generation}</span></div>
  </div>`;
  h += `<div class="card"><h3>Observaciones</h3>`;
  for (const n of a.notes) h += `<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,.03)">• ${n}</div>`;
  h += `</div>`;
  $("analysis-body").innerHTML = h;
}

/* ------------------------------------------------------------------ controls */
function wireControls() {
  document.querySelectorAll("#tabs button").forEach((b) => b.onclick = () => setTab(b.dataset.tab));
  $("audio-on").onchange = (e) => MVAudio.setEnabled(e.target.checked);
  $("debug-on").onchange = (e) => { S.debug = e.target.checked; if (S.selectedId != null) fetchAgent(); };
  $("btn-unfollow").onclick = () => { S.following = false; renderFollowBadge(); };
  $("btn-reset").onclick = resetSim;
  $("btn-new").onclick = openNewModal;
  $("btn-cancel").onclick = () => $("modal").classList.add("hidden");
  $("new-form").onsubmit = submitNew;
  $("btn-export").onclick = toggleExport;
  wireExports();
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { $("modal").classList.add("hidden");
      $("export-menu").classList.add("hidden"); S.following = false; renderFollowBadge(); }
    else if (e.key === " " && e.target.tagName !== "INPUT") {
      e.preventDefault();
      setSpeed((S.runner.speed ?? 1) > 0 ? 0 : 1);
    }
  });
  fit();
}

async function resetSim() {
  if (!confirm("¿Reiniciar la isla con la misma configuración? Se perderá el progreso actual.")) return;
  const res = await fetch(api("/reset"), { method: "POST" }).then((r) => r.json());
  await selectSim(res.id);
}

/* new island modal ------------------------------------------------------ */
async function openNewModal() {
  const s = await fetch("/api/config/schema").then((r) => r.json());
  const fields = $("form-fields"); fields.innerHTML = "";
  for (const f of s.schema) {
    const full = f.type === "text" ? " full" : "";
    const wrap = document.createElement("div"); wrap.className = "field" + full;
    const step = f.step ? ` step="${f.step}"` : (f.type === "float" ? ` step="0.01"` : "");
    const min = f.min != null ? ` min="${f.min}"` : "", max = f.max != null ? ` max="${f.max}"` : "";
    const type = f.type === "text" ? "text" : "number";
    wrap.innerHTML = `<label>${f.label}</label>
      <input name="${f.key}" type="${type}" value="${f.default}"${step}${min}${max}>
      ${f.help ? `<span class="help">${f.help}</span>` : ""}`;
    fields.appendChild(wrap);
  }
  $("modal").classList.remove("hidden");
}

async function submitNew(e) {
  e.preventDefault();
  const fd = new FormData(e.target); const cfg = {};
  for (const [k, v] of fd.entries()) cfg[k] = (k === "name") ? v : parseFloat(v);
  const res = await fetch("/api/simulations", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg) }).then((r) => r.json());
  $("modal").classList.add("hidden");
  await selectSim(res.id);
}

/* export menu ----------------------------------------------------------- */
function toggleExport(e) {
  const m = $("export-menu");
  if (!m.classList.contains("hidden")) { m.classList.add("hidden"); return; }
  const r = e.target.getBoundingClientRect();
  m.style.top = (r.bottom + 6) + "px"; m.style.right = (window.innerWidth - r.right) + "px";
  m.classList.remove("hidden");
}
function wireExports() {
  const map = { "x-run": "/export/run.json", "x-events": "/export/events.csv",
    "x-metrics": "/export/metrics.csv", "x-gen": "/export/genealogy.json", "x-living": "/export/living.json" };
  for (const [id, path] of Object.entries(map)) {
    $(id).onclick = (e) => { e.preventDefault(); window.open(api(path), "_blank");
      $("export-menu").classList.add("hidden"); };
  }
  document.addEventListener("click", (e) => {
    if (!$("export-menu").contains(e.target) && e.target !== $("btn-export"))
      $("export-menu").classList.add("hidden");
  });
}

boot();
