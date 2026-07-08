/* The terminal loop: boot Pyodide, install the engine wheel, and wire the
   input line to app_api (docs/design/ios-tomb-app.md §1). No framework --
   the whole UI is this file. */

const output = document.getElementById("output");
const cmd = document.getElementById("cmd");
const statusRoom = document.getElementById("status-room");
const statusScore = document.getElementById("status-score");
const chipsVerbs = document.getElementById("chips-verbs");
const chipsNouns = document.getElementById("chips-nouns");
const bootscreen = document.getElementById("bootscreen");
const boottext = document.getElementById("boottext");

let api = null;

function print(text, cls) {
  const p = document.createElement("p");
  if (cls) p.className = cls;
  p.textContent = text;
  output.appendChild(p);
  output.scrollTop = output.scrollHeight;
}

function haptic(kind) {
  // Present only inside the iOS shell; the web build silently skips it.
  try { window.webkit.messageHandlers.haptic.postMessage(kind); } catch (e) {}
}

function render(payloadJson) {
  const payload = JSON.parse(payloadJson);
  for (const ev of payload.events) {
    const cls =
      ev.channel === "damage" ? "damage" :
      ev.channel === "blocked" ? "blocked" : "";
    const prefix = ev.channel === "damage" ? "♥ " :
                   ev.channel === "blocked" ? "✗ " : "";
    print(prefix + ev.text, cls);
    if (ev.channel === "damage") haptic("damage");
  }
  const s = payload.status;
  if (s.game_over && !s.won) haptic("death");
  statusRoom.textContent = (s.room || "").toUpperCase();
  statusScore.textContent = `${s.score}/${s.max_score}   T:${s.turn}`;
  renderChips(payload.suggestions);
  if (s.game_over) {
    print(s.won ? "*** You have won. ***" : "*** The tomb keeps you. ***", "echo");
    print("(type RESTORE to return to a saved position, or reload to start over)", "blocked");
  }
}

function chip(word, cls, withSpace) {
  const el = document.createElement("span");
  el.className = "chip " + cls;
  el.textContent = word;
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault(); // keep the keyboard where it is
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
  print("> " + text, "echo");
  render(api.command(text));
}

cmd.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submit();
});

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
  try {
    const auto = localStorage.getItem("tomb_save_auto");
    if (auto) seed = JSON.parse(auto).seed ?? seed;
  } catch (e) { /* fresh expedition */ }

  render(api.boot(seed));
  const auto = localStorage.getItem("tomb_save_auto");
  if (auto) {
    print("(an unfinished expedition is on file -- type RESTORE AUTO to resume it)", "blocked");
  }
  bootscreen.classList.add("done");
  cmd.focus();
}

main().catch((e) => {
  boottext.textContent = "the phosphor fails to warm:\n" + e;
});
