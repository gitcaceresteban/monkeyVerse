/* monkeyVerse v4 — one short synthesized tone per sound 0-9.
 *
 * No audio files: every tone is generated with the Web Audio API so the app
 * stays self-contained and works offline on the Raspberry Pi. The pitch/waveform
 * of each digit is arbitrary but stable — a tone always sounds the same — but it
 * carries NO built-in meaning. What (if anything) a sound comes to mean is for
 * the agents to work out and for the observer to measure, never for us to assign.
 */
"use strict";

const MVAudio = (() => {
  let ctx = null;
  let enabled = false;
  let volume = 0.6;
  let activeVoices = 0;
  const MAX_VOICES = 6;

  // one distinct (frequency, waveform) pair per digit 0..9 — deliberately
  // meaningless, just an audible fingerprint so you can tell tones apart.
  const VOICES = [
    { f: 196, type: "sine" },
    { f: 247, type: "triangle" },
    { f: 294, type: "sawtooth" },
    { f: 349, type: "sine" },
    { f: 392, type: "triangle" },
    { f: 440, type: "square" },
    { f: 523, type: "triangle" },
    { f: 587, type: "sine" },
    { f: 659, type: "square" },
    { f: 784, type: "sawtooth" },
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
  function isEnabled() { return enabled; }
  function setVolume(v) { volume = Math.max(0, Math.min(1, v)); }

  // gain scales with how loud the sound should be for the listener (distance /
  // whether you're following the emitter). priority 2 = followed agent.
  function play(sound, loudness = 0.4, priority = 0) {
    if (!enabled) return;
    if (activeVoices >= MAX_VOICES && priority < 1) return;
    const v = VOICES[((sound % 10) + 10) % 10];
    const c = ensureCtx();
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = v.type;
    osc.frequency.value = v.f;
    const peak = volume * Math.max(0.05, Math.min(0.6, loudness)) * (priority >= 2 ? 1.3 : 1.0);
    const now = c.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.001, peak), now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.26);
    osc.connect(gain).connect(c.destination);
    activeVoices++;
    osc.start(now);
    osc.stop(now + 0.28);
    osc.onended = () => { activeVoices = Math.max(0, activeVoices - 1); };
  }

  return { setEnabled, isEnabled, setVolume, play };
})();
