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

function nearBottom() {
  return output.scrollTop + output.clientHeight >= output.scrollHeight - 80;
}

function print(text, cls, instant) {
  const p = document.createElement("p");
  if (cls) p.className = cls;
  output.appendChild(p);
  if (instant || settings.typewriter === "off") {
    p.textContent = text;
    if (nearBottom()) output.scrollTop = output.scrollHeight;
  } else {
    queue.push({ p, text, done: false });
    if (!typing) typeNext();
  }
  return p;
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
    // Follow the reveal only if the reader is at the bottom; a long room
    // description reads from the TOP, at the reader's own pace (CCB).
    if (nearBottom()) output.scrollTop = output.scrollHeight;
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
    print("(type RESTORE to return to a saved position, or RESTART to begin anew)", "blocked", instant);
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
    // No focus here: composing by chip should not summon the keyboard
    // (CCB) -- tap the input line when you want to type.
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
  // A comma chains commands ("go east, go south" -- the map's tap-to-walk
  // routes, or typed by hand). Each step runs as its own turn; a blocked
  // step abandons the rest, so a shifted tomb never walks you blind.
  const steps = text.split(",").map((s) => s.trim()).filter(Boolean);
  let anchor = null;
  for (const step of steps) {
    const echo = print("> " + step, "echo", true);
    anchor = anchor ?? echo;
    const payload = api.command(step);
    render(payload);
    if (
      steps.length > 1 &&
      JSON.parse(payload).events.some((ev) => ev.channel === "blocked")
    ) {
      print("(the way is barred -- the rest of the route is abandoned)", "blocked", true);
      break;
    }
  }
  // Read from the TOP of the turn (CCB): the echoed command pins to the
  // top of the view and the player scrolls down at their own pace.
  output.scrollTop = Math.max(0, anchor.offsetTop - 4);
}

cmd.addEventListener("keydown", (e) => {
  ensureAudio();
  click();
  if (e.key === "Enter") submit();
});
document.getElementById("send").addEventListener("pointerdown", (e) => {
  e.preventDefault(); // don't steal focus from wherever it is
  ensureAudio();
  click();
  submit();
});
document.addEventListener("pointerdown", ensureAudio, { once: true });

/* ------------------------------------------------------- swipe panels */
/* Swipe right -> the inventory (from the left edge). Swipe left -> the map
   of EXPLORED rooms (from the right): nodes you have stood in, arcs labeled
   with the direction of travel, dashed stubs where you haven't gone (CCB).
   The i/m buttons in the status bar do the same for mouse-and-keyboard. */

const panelInv = document.getElementById("panel-inv");
const panelMap = document.getElementById("panel-map");

function closePanels() {
  panelInv.classList.add("hidden");
  panelMap.classList.add("hidden");
  // Empty the panels once they have slid away: iOS WebKit can otherwise
  // show STALE painted content (ghost room labels) from the previous
  // render when the layer comes back (CCB's phantom 'Tomb Exterior').
  setTimeout(() => {
    if (panelInv.classList.contains("hidden")) panelInv.replaceChildren();
    if (panelMap.classList.contains("hidden")) panelMap.replaceChildren();
  }, 260);
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text) node.textContent = text;
  return node;
}

function closeButton() {
  const b = el("span", "panel-close", "[ RESUME ]");
  b.addEventListener("pointerdown", (e) => { e.preventDefault(); closePanels(); });
  return b;
}

function openInventory() {
  if (!api) return;
  const data = JSON.parse(api.panels()).inventory;
  panelInv.replaceChildren(el("h2", "", "PACK"));
  const section = (title) => panelInv.appendChild(el("div", "inv-section", title));
  if (!data.carried.length) panelInv.appendChild(el("div", "inv-item", "(nothing carried)"));
  for (const it of data.carried) panelInv.appendChild(el("div", "inv-item", `* ${it.description}`));
  if (data.worn.length) {
    section("worn");
    for (const it of data.worn) panelInv.appendChild(el("div", "inv-item", `* ${it.description}`));
  }
  if (data.wounds.length) {
    section("wounds");
    for (const w of data.wounds)
      panelInv.appendChild(el("div", "inv-wound", `\u2665 ${w.name} (${w.slots}) - ${w.description}`));
  }
  if (data.slots) section(`slots ${data.slots}`);
  panelInv.appendChild(closeButton());
  panelMap.classList.add("hidden");
  panelInv.classList.remove("hidden");
}

/* Compass geometry: where each direction PLACES the far room, in grid cells.
   North is up, west is left; up/down and in/out lean diagonally (the old
   IF-mapper convention) so they read apart from north/south. Odd passages
   ("left stairs") have no vector and take the nearest free diagonal. */
const DIR_VEC = {
  north: [0, -1], south: [0, 1], east: [1, 0], west: [-1, 0],
  northeast: [1, -1], northwest: [-1, -1], southeast: [1, 1], southwest: [-1, 1],
  up: [1, -1], down: [-1, 1], in: [1, 1], inside: [1, 1],
  out: [-1, -1], outside: [-1, -1],
};
const DIR_OPP = {
  north: "south", south: "north", east: "west", west: "east",
  northeast: "southwest", southwest: "northeast",
  northwest: "southeast", southeast: "northwest",
  up: "down", down: "up", in: "out", out: "in",
  inside: "outside", outside: "inside",
};

function mapLayout(nodes, edges, here) {
  // COMPASS-TRUE layout: BFS out from the current room, placing each new
  // room in the cell its direction actually points to, so the geometry
  // never argues with the labels. An occupied cell pushes the room further
  // out along the same bearing.
  const adj = new Map(nodes.map((n) => [n, []]));
  for (const e of edges) {
    // The layout bearing comes from whichever side speaks compass: the
    // canopic stairs are "right stairs" one way but "up" the other, and
    // one honest bearing is enough to draw the line true.
    const v = DIR_VEC[e.dir] || (DIR_VEC[e.back] || []).map((c) => -c);
    adj.get(e.from)?.push({ to: e.to, vec: v.length ? v : null });
    adj.get(e.to)?.push({ to: e.from, vec: v.length ? v.map((c) => -c) : null });
  }
  const start = here ?? nodes[0];
  const grid = new Map([[start, [0, 0]]]);
  const key = (x, y) => `${Math.round(x * 2)},${Math.round(y * 2)}`;
  const taken = new Set([key(0, 0)]);
  const place = (from, vec) => {
    const [fx, fy] = grid.get(from);
    const tries = vec
      ? [1, 2, 3, 4].map((k) => [fx + vec[0] * k, fy + vec[1] * k])
      : [[1, 1], [-1, 1], [1, -1], [-1, -1], [2, 0], [-2, 0], [0, 2], [0, -2]]
          .map(([dx, dy]) => [fx + dx, fy + dy]);
    for (const [x, y] of tries) if (!taken.has(key(x, y))) return [x, y];
    return [fx + 5, fy + 5];
  };
  const queue = [start];
  while (queue.length) {
    const n = queue.shift();
    for (const hop of adj.get(n) || []) {
      if (grid.has(hop.to)) continue;
      const p = place(n, hop.vec);
      grid.set(hop.to, p);
      taken.add(key(p[0], p[1]));
      queue.push(hop.to);
    }
  }
  let parked = 0;
  for (const n of nodes) if (!grid.has(n)) grid.set(n, [parked++, 3]);
  const xs = [...grid.values()].map((p) => p[0]);
  const ys = [...grid.values()].map((p) => p[1]);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const pos = new Map();
  for (const [n, [x, y]] of grid)
    pos.set(n, { x: 14 + (x - minX) * 150, y: 24 + (y - minY) * 92 });
  return pos;
}

function mapRoute(m, target) {
  // Shortest explored path from HERE to the tapped room, as the commands
  // that actually walk it -- each hop uses the word its own side of the
  // passage answers to ("right stairs" down, "up" back). One-way passages
  // (back: null) are never walked backward.
  const adj = new Map(m.nodes.map((n) => [n, []]));
  for (const e of m.edges) {
    adj.get(e.from)?.push({ to: e.to, cmd: e.dir });
    if (e.back) adj.get(e.to)?.push({ to: e.from, cmd: e.back });
  }
  const prev = new Map([[m.here, null]]);
  const queue = [m.here];
  while (queue.length) {
    const n = queue.shift();
    if (n === target) break;
    for (const hop of adj.get(n) || [])
      if (!prev.has(hop.to)) {
        prev.set(hop.to, { from: n, cmd: hop.cmd });
        queue.push(hop.to);
      }
  }
  if (!prev.has(target)) return null;
  const route = [];
  for (let n = target; prev.get(n); n = prev.get(n).from)
    route.unshift(prev.get(n).cmd);
  return route;
}

function openMap() {
  if (!api) return;
  const m = JSON.parse(api.panels()).map;
  panelMap.replaceChildren(el("h2", "", "THE EXPEDITION SO FAR"));
  const pos = mapLayout(m.nodes, m.edges, m.here);
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("preserveAspectRatio", "xMidYMin meet");
  // The viewBox is set AFTER drawing, from the true extent of everything
  // drawn -- stub labels overshoot the node grid and were getting cropped.
  const box = { x0: 0, y0: 0, x1: 300, y1: 80 };
  const ext = (x, y, padX = 0, padY = 0) => {
    box.x0 = Math.min(box.x0, x - padX);
    box.y0 = Math.min(box.y0, y - padY);
    box.x1 = Math.max(box.x1, x + padX);
    box.y1 = Math.max(box.y1, y + padY);
  };
  const sub = (name, attrs, cls) => {
    const q = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) q.setAttribute(k, v);
    if (cls) q.setAttribute("class", cls);
    svg.appendChild(q);
    return q;
  };
  const center = (n) => ({ x: pos.get(n).x + 62, y: pos.get(n).y + 14 });
  // An edge label sits a third of the way out from ITS OWN room, nudged off
  // the line, so each end reads as "leave this room that way". The reverse
  // is labeled only when it answers to a different word than the opposite.
  const edgeLabel = (a, b, word) => {
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    // Step just past the edge of the label's own box (66 wide, 18 tall at
    // the worst angle), clamped so two-ended labels can't cross the middle.
    const clear = Math.abs(dx / len) * 66 + Math.abs(dy / len) * 18 + 10;
    const f = Math.min(0.42, clear / len);
    const lx = a.x + dx * f - (dy / len) * 9;
    const ly = a.y + dy * f + (dx / len) * 9 + 3;
    const t = sub("text", { x: lx, y: ly }, "map-label");
    t.setAttribute("text-anchor", "middle");
    t.textContent = word;
    ext(lx, ly, 30, 10);
  };
  for (const e of m.edges) {
    const a = center(e.from), b = center(e.to);
    sub("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y }, "map-edge");
    edgeLabel(a, b, e.dir);
    if (e.back && e.back !== DIR_OPP[e.dir]) edgeLabel(b, a, e.back);
  }
  let stubTilt = -1;
  for (const st of m.stubs) {
    const a = center(st.from);
    let v = DIR_VEC[st.dir];
    if (!v) {
      stubTilt = -stubTilt; // odd directions alternate sides, un-piled
      v = [0.6 * stubTilt, 0.6];
    }
    const bx = a.x + v[0] * 88, by = a.y + v[1] * 42;
    sub("line", { x1: a.x, y1: a.y, x2: bx, y2: by }, "map-stub");
    const t = sub(
      "text",
      { x: bx + Math.sign(v[0]) * 4, y: by + (v[1] >= 0 ? 12 : -6) },
      "map-label"
    );
    t.setAttribute(
      "text-anchor",
      v[0] > 0 ? "start" : v[0] < 0 ? "end" : "middle"
    );
    t.textContent = st.dir + "?";
    ext(bx, by, 64, 16);
  }
  for (const n of m.nodes) {
    const p = pos.get(n);
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", "map-node" + (n === m.here ? " here" : ""));
    const rect = document.createElementNS(NS, "rect");
    for (const [k, v] of Object.entries({ x: p.x, y: p.y, width: 124, height: 28, rx: 3 }))
      rect.setAttribute(k, v);
    const label = document.createElementNS(NS, "text");
    label.setAttribute("x", p.x + 62);
    label.setAttribute("y", p.y + 18);
    label.setAttribute("text-anchor", "middle");
    label.textContent = n.length > 22 ? n.slice(0, 21) + "\u2026" : n;
    g.append(rect, label);
    ext(p.x, p.y);
    ext(p.x + 124, p.y + 28);
    // Tap a room to walk back to it: the explored route lands in the input
    // as "go X, go Y" for the player to review and send (CCB's user ask).
    g.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      click();
      if (n === m.here || !m.here) { closePanels(); return; }
      const route = mapRoute(m, n);
      if (!route) return; // unreachable through explored passages
      cmd.value = route.map((d) => "go " + d).join(", ");
      closePanels();
    });
    svg.appendChild(g);
  }
  svg.setAttribute(
    "viewBox",
    `${box.x0 - 8} ${box.y0 - 8} ${box.x1 - box.x0 + 16} ${box.y1 - box.y0 + 16}`
  );
  panelMap.appendChild(svg);
  panelMap.appendChild(el("div", "inv-section",
    m.here ? `you are in ${m.here} -- tap a room to walk back to it` : ""));
  panelMap.appendChild(closeButton());
  panelInv.classList.add("hidden");
  panelMap.classList.remove("hidden");
}

document.getElementById("btn-inv").addEventListener("pointerdown", (e) => {
  e.preventDefault(); click();
  panelInv.classList.contains("hidden") ? openInventory() : closePanels();
});
document.getElementById("btn-map").addEventListener("pointerdown", (e) => {
  e.preventDefault(); click();
  panelMap.classList.contains("hidden") ? openMap() : closePanels();
});

let swipe = null;
output.addEventListener("touchstart", (e) => {
  if (e.touches.length === 1)
    swipe = { x: e.touches[0].clientX, y: e.touches[0].clientY };
}, { passive: true });
output.addEventListener("touchend", (e) => {
  if (!swipe) return;
  const dx = e.changedTouches[0].clientX - swipe.x;
  const dy = e.changedTouches[0].clientY - swipe.y;
  swipe = null;
  if (Math.abs(dx) < 60 || Math.abs(dy) > 50) return;
  if (dx > 0) openInventory();  // swipe right: the pack
  else openMap();               // swipe left: the expedition so far
}, { passive: true });
for (const panel of [panelInv, panelMap]) {
  panel.addEventListener("touchstart", (e) => {
    if (e.touches.length === 1)
      swipe = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  }, { passive: true });
  panel.addEventListener("touchend", (e) => {
    if (!swipe) return;
    const dx = e.changedTouches[0].clientX - swipe.x;
    swipe = null;
    if (Math.abs(dx) > 60) closePanels();  // counter-swipe dismisses
  }, { passive: true });
}

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
    panels: () => pyodide.runPython("app_api.panel_data()"),
  };

  // Seed: resume the autosave's seed when one exists, else the clock.
  let seed = Date.now() % 1000000;
  let hasAuto = false;
  try {
    const auto = localStorage.getItem("tomb_save_auto");
    if (auto) { seed = JSON.parse(auto).seed ?? seed; hasAuto = true; }
  } catch (e) { /* fresh expedition */ }

  applySettings();

  // The title holds until the player asks for the tomb (CCB). When an
  // unfinished expedition is on file, the CHOICE lives here on the title
  // screen -- continue it, or begin anew -- not as a banner in the story.
  boottext.textContent = "TOMB OF NASSAK AN-RAH\na Vaults of Vaarn expedition";
  boottext.classList.add("ready");
  const resume = await new Promise((begin) => {
    if (!hasAuto) {
      boottext.textContent += "\n\n[ tap or press any key to begin ]";
      const go = () => {
        document.removeEventListener("pointerdown", go);
        document.removeEventListener("keydown", go);
        begin(false);
      };
      document.addEventListener("pointerdown", go);
      document.addEventListener("keydown", go);
      return;
    }
    boottext.textContent += "\n\nan unfinished expedition is on file";
    const menu = document.createElement("div");
    menu.id = "bootmenu";
    for (const [label, value] of [
      ["[ CONTINUE THE EXPEDITION ]", true],
      ["[ BEGIN ANEW ]", false],
    ]) {
      const b = document.createElement("div");
      b.className = "boot-option";
      b.textContent = label;
      b.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        menu.remove();
        begin(value);
      });
      menu.appendChild(b);
    }
    boottext.after(menu);
  });

  if (resume && hasAuto) {
    render(api.boot(seed), { instant: true });
    output.replaceChildren(); // the restored look is the real opening
    render(api.command("restore auto"), { instant: true });
  } else {
    if (hasAuto) {
      try { localStorage.removeItem("tomb_save_auto"); } catch (e) {}
      seed = Date.now() % 1000000;
    }
    render(api.boot(seed));
  }
  output.scrollTop = 0; // the expedition reads from the top (CCB)
  bootscreen.classList.add("done");
  ensureAudio();
  sounds.boot();
  // No autofocus (CCB): the keyboard comes when the player taps the input.
}

main().catch((e) => {
  boottext.textContent = "the phosphor fails to warm:\n" + e;
});
