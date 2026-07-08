/* The terminal loop: boot Pyodide, install the engine wheel, and wire the
   input line to app_api (docs/design/ios-tomb-app.md §1). No framework --
   the whole UI is this file.

   M3 dressing (§3): typewriter reveal, synthesized WebAudio (hum, keyclicks,
   a beep for ✗, a thud for ♥), phosphor flicker, and a settings overlay --
   every piece toggleable and persisted, honest defaults (all on). */

const output = document.getElementById("output");
const cmd = document.getElementById("cmd");
const statusRoom = document.getElementById("status-room");
const statusScore = document.getElementById("status-score");
const chipsVerbs = document.getElementById("chips-verbs");
const chipsNouns = document.getElementById("chips-nouns");
const bootscreen = document.getElementById("bootscreen");
const boottext = document.getElementById("boottext");
const suggestbar = document.getElementById("suggestbar");
const settingsPanel = document.getElementById("settings");

let api = null;

/* ---------------------------------------------------------------- settings */

const DEFAULTS = {
  crt: true,        // scanlines, vignette, flicker
  typewriter: "on", // "on" | "fast" | "off"
  sound: true,
  haptics: true,
  chips: true,
  textsize: "normal", // "small" | "normal" | "large"
};
let settings = { ...DEFAULTS };
try {
  Object.assign(settings, JSON.parse(localStorage.getItem("tomb_settings") || "{}"));
} catch (e) { /* defaults */ }

function applySettings() {
  document.body.classList.toggle("no-crt", !settings.crt);
  document.body.classList.toggle("size-small", settings.textsize === "small");
  document.body.classList.toggle("size-large", settings.textsize === "large");
  suggestbar.style.display = settings.chips ? "" : "none";
  hum(settings.sound);
  try { localStorage.setItem("tomb_settings", JSON.stringify(settings)); } catch (e) {}
  renderSettings();
}

const SETTING_ROWS = [
  ["crt", "CRT EFFECTS", [true, false], (v) => (v ? "ON" : "OFF")],
  ["typewriter", "TYPEWRITER", ["on", "fast", "off"], (v) => v.toUpperCase()],
  ["sound", "SOUND", [true, false], (v) => (v ? "ON" : "OFF")],
  ["haptics", "HAPTICS", [true, false], (v) => (v ? "ON" : "OFF")],
  ["chips", "WORD CHIPS", [true, false], (v) => (v ? "ON" : "OFF")],
  ["textsize", "TEXT SIZE", ["small", "normal", "large"], (v) => v.toUpperCase()],
];

function renderSettings() {
  const rows = SETTING_ROWS.map(([key, label, values, show]) => {
    const row = document.createElement("div");
    row.className = "setting-row";
    const name = document.createElement("span");
    name.textContent = label;
    const value = document.createElement("span");
    value.className = "setting-value";
    value.textContent = "< " + show(settings[key]) + " >";
    row.append(name, value);
    row.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const next = (values.indexOf(settings[key]) + 1) % values.length;
      settings[key] = values[next];
      click();
      applySettings();
    });
    return row;
  });
  const done = document.createElement("div");
  done.className = "setting-row setting-done";
  done.textContent = "[ RESUME EXPEDITION ]";
  done.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    toggleSettings(false);
  });
  settingsPanel.replaceChildren(...rows, done);
}

function toggleSettings(show) {
  const on = show ?? settingsPanel.classList.contains("hidden");
  settingsPanel.classList.toggle("hidden", !on);
  if (!on) cmd.focus();
}
document.getElementById("gear").addEventListener("pointerdown", (e) => {
  e.preventDefault();
  ensureAudio();
  click();
  toggleSettings();
});

/* ------------------------------------------------------------------- sound */
/* All synthesized -- no assets, no licenses. The AudioContext unlocks on the
   first user gesture (autoplay policy). */

let audio = null;
let humNodes = null;

function ensureAudio() {
  if (audio || !window.AudioContext) return;
  audio = new AudioContext();
  hum(settings.sound);
}

function hum(on) {
  if (!audio) return;
  if (on && !humNodes) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = "triangle";
    osc.frequency.value = 55;
    gain.gain.value = 0.006; // barely there: the room tone of an old tube
    osc.connect(gain).connect(audio.destination);
    osc.start();
    humNodes = { osc, gain };
  } else if (!on && humNodes) {
    humNodes.osc.stop();
    humNodes = null;
  }
}

function blip({ freq = 440, to = null, time = 0.08, type = "square", vol = 0.03 }) {
  if (!audio || !settings.sound) return;
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  if (to) osc.frequency.exponentialRampToValueAtTime(to, audio.currentTime + time);
  gain.gain.value = vol;
  gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + time);
  osc.connect(gain).connect(audio.destination);
  osc.start();
  osc.stop(audio.currentTime + time);
}

function click() {
  // a mechanical keyclick: a tiny burst of decaying noise
  if (!audio || !settings.sound) return;
  const len = 0.012;
  const buf = audio.createBuffer(1, audio.sampleRate * len, audio.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) {
    data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
  }
  const src = audio.createBufferSource();
  const gain = audio.createGain();
  gain.gain.value = 0.05;
  src.buffer = buf;
  src.connect(gain).connect(audio.destination);
  src.start();
}

const sounds = {
  blocked: () => blip({ freq: 196, time: 0.1, vol: 0.025 }),
  damage: () => blip({ freq: 130, to: 36, time: 0.22, type: "sine", vol: 0.09 }),
  boot: () => blip({ freq: 220, to: 880, time: 0.35, type: "triangle", vol: 0.03 }),
  tick: () => blip({ freq: 1400, time: 0.008, type: "sine", vol: 0.008 }),
};

/* -------------------------------------------------------------- typewriter */
/* Lines queue and reveal at baud-ish speed; tapping the output (or entering
   the next command) completes everything instantly. Big batches -- boots and
   restores -- always render instantly. */

const queue = [];
let typing = false;

function print(text, cls, instant) {
  const p = document.createElement("p");
  if (cls) p.className = cls;
  output.appendChild(p);
  if (instant || settings.typewriter === "off") {
    p.textContent = text;
    output.scrollTop = output.scrollHeight;
  } else {
    queue.push({ p, text, done: false });
    if (!typing) typeNext();
  }
}

function typeNext() {
  const job = queue.shift();
  if (!job) { typing = false; return; }
  typing = true;
  const step = settings.typewriter === "fast" ? 5 : 2;
  const delay = settings.typewriter === "fast" ? 4 : 11;
  let i = 0;
  const tick = () => {
    if (job.done) { typeNext(); return; } // flushed mid-type
    i = Math.min(i + step, job.text.length);
    job.p.textContent = job.text.slice(0, i);
    output.scrollTop = output.scrollHeight;
    if (i % 24 < step) sounds.tick();
    if (i < job.text.length) setTimeout(tick, delay);
    else typeNext();
  };
  tick();
}

function flushTypewriter() {
  for (const job of queue) {
    job.done = true;
    job.p.textContent = job.text;
  }
  queue.length = 0;
  typing = false;
  output.scrollTop = output.scrollHeight;
}

output.addEventListener("pointerdown", flushTypewriter);

/* ------------------------------------------------------------------ render */

function haptic(kind) {
  if (!settings.haptics) return;
  // Present only inside the iOS shell; the web build silently skips it.
  try { window.webkit.messageHandlers.haptic.postMessage(kind); } catch (e) {}
}

function render(payloadJson, opts = {}) {
  const payload = JSON.parse(payloadJson);
  const instant = opts.instant || payload.events.length > 10;
  for (const ev of payload.events) {
    const cls =
      ev.channel === "damage" ? "damage" :
      ev.channel === "blocked" ? "blocked" : "";
    const prefix = ev.channel === "damage" ? "♥ " :
                   ev.channel === "blocked" ? "✗ " : "";
    print(prefix + ev.text, cls, instant);
    if (ev.channel === "damage") { haptic("damage"); sounds.damage(); }
    if (ev.channel === "blocked") sounds.blocked();
  }
  const s = payload.status;
  statusRoom.textContent = (s.room || "").toUpperCase();
  statusScore.textContent = `${s.score}/${s.max_score}   T:${s.turn}`;
  renderChips(payload.suggestions);
  if (s.game_over) {
    if (!s.won) { haptic("death"); sounds.damage(); }
    print(s.won ? "*** You have won. ***" : "*** The tomb keeps you. ***", "echo", instant);
    print("(type RESTORE to return to a saved position, or reload to start over)", "blocked", instant);
  }
}

function chip(word, cls, withSpace) {
  const el = document.createElement("span");
  el.className = "chip " + cls;
  el.textContent = word;
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault(); // keep the keyboard where it is
    ensureAudio();
    click();
    const sep = cmd.value && !cmd.value.endsWith(" ") ? " " : "";
    cmd.value += sep + word + (withSpace ? " " : "");
    cmd.focus();
  });
  return el;
}

function renderChips(sug) {
  chipsVerbs.replaceChildren(
    ...sug.exits.map((e) => chip(e, "", false)),
    ...sug.verbs.map((v) => chip(v, "", true))
  );
  chipsNouns.replaceChildren(...sug.nouns.map((n) => chip(n, "noun", false)));
}

function submit() {
  const text = cmd.value.trim();
  if (!text || !api) return;
  cmd.value = "";
  flushTypewriter();
  print("> " + text, "echo", true);
  render(api.command(text));
}

cmd.addEventListener("keydown", (e) => {
  ensureAudio();
  click();
  if (e.key === "Enter") submit();
});
document.addEventListener("pointerdown", ensureAudio, { once: true });

/* -------------------------------------------------------------------- boot */

async function main() {
  boottext.textContent += ".";
  // The manifest names the wheel and where the Pyodide runtime lives: the
  // CDN for the plain web deploy, "./pyodide/" when vendored (the iOS bundle
  // is fully offline -- build_dist.py --with-pyodide).
  const manifest = await (await fetch("manifest.json")).json();
  const base = manifest.pyodideBase ||
    "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  await new Promise((ok, bad) => {
    const s = document.createElement("script");
    s.src = base + "pyodide.js";
    s.onload = ok;
    s.onerror = () => bad(new Error("could not load the Python runtime"));
    document.head.appendChild(s);
  });
  const pyodide = await loadPyodide({ indexURL: base });
  boottext.textContent += ".";

  // The engine wheel: pure Python, zero dependencies (verified by the
  // blocked-imports audit). unpackArchive installs it without micropip.
  const wheel = await (await fetch(manifest.wheel)).arrayBuffer();
  pyodide.unpackArchive(wheel, "wheel");
  boottext.textContent += ".";

  const bridge = await (await fetch("app_api.py")).text();
  pyodide.FS.writeFile("app_api.py", bridge);
  pyodide.runPython("import app_api");
  api = {
    command: (t) => pyodide.runPython(`app_api.command(${JSON.stringify(t)})`),
    boot: (seed) => pyodide.runPython(`app_api.boot(${seed})`),
  };

  // Seed: resume the autosave's seed when one exists (so RESTORE AUTO is
  // meaningful across visits), else the clock.
  let seed = Date.now() % 1000000;
  let hasAuto = false;
  try {
    const auto = localStorage.getItem("tomb_save_auto");
    if (auto) { seed = JSON.parse(auto).seed ?? seed; hasAuto = true; }
  } catch (e) { /* fresh expedition */ }

  applySettings();
  render(api.boot(seed));
  if (hasAuto) {
    print("(an unfinished expedition is on file -- type RESTORE AUTO to resume it)", "blocked", true);
  }
  bootscreen.classList.add("done");
  sounds.boot();
  cmd.focus();
}

main().catch((e) => {
  boottext.textContent = "the phosphor fails to warm:\n" + e;
});
