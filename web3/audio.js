/* monkeyVerse v3 — a short synthesized tone per language symbol (0-9).
 * No audio files: everything is generated with the Web Audio API so the app
 * stays self-contained and works offline on the Raspberry Pi. */
"use strict";

const MVAudio = (() => {
  let ctx = null;
  let enabled = false;
  let volume = 0.6;
  let activeVoices = 0;
  const MAX_VOICES = 6;

  // one distinct (frequency, waveform) pair per digit — arbitrary but stable,
  // so the same symbol always sounds the same.
  const VOICES = [
    { f: 220, type: "sine" },      // 0 neutral
    { f: 330, type: "triangle" },  // 1 comida
    { f: 140, type: "sawtooth" },  // 2 peligro
    { f: 494, type: "sine" },      // 3 pareja/reproducción
    { f: 392, type: "triangle" },  // 4 seguir
    { f: 262, type: "square" },    // 5 alejarse
    { f: 175, type: "triangle" },  // 6 territorio
    { f: 587, type: "sine" },      // 7 ayuda
    { f: 110, type: "square" },    // 8 amenaza
    { f: 440, type: "sawtooth" },  // 9 exploración
  ];

  function ensureCtx() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  function setEnabled(v) { enabled = v; if (v) ensureCtx(); }
  function setVolume(v) { volume = Math.max(0, Math.min(1, v)); }

  // priority: 2 = selected agent, 1 = nearby, 0 = ambient/background
  function play(symbol, priority = 0) {
    if (!enabled) return;
    if (activeVoices >= MAX_VOICES && priority < 1) return; // drop low-priority when busy
    const v = VOICES[symbol % VOICES.length];
    const c = ensureCtx();
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = v.type;
    osc.frequency.value = v.f;
    const peak = volume * (priority >= 2 ? 0.5 : priority === 1 ? 0.3 : 0.15);
    const now = c.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.001, peak), now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
    osc.connect(gain).connect(c.destination);
    activeVoices++;
    osc.start(now);
    osc.stop(now + 0.24);
    osc.onended = () => { activeVoices = Math.max(0, activeVoices - 1); };
  }

  return { setEnabled, setVolume, play };
})();
