/* Prompt Chain Visualizer front-end.
 *
 * Fetches a chain's DAG from /graph.json, draws it with Cytoscape (dagre
 * layout), and on node click fetches /prompt/<chain>/<node> to fill the side
 * panel with the template's prompt (and, when a run is overlaid, the real calls).
 */
"use strict";

const MONO =
  'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';

const KIND_COLOR = {
  start: "#8b949e",
  decision: "#58a6ff",
  parse: "#d29922",
  narrate: "#3fb950",
  gate: "#bc8cff",
};

let cy = null;
let currentChain = null;

/* ---------- tiny DOM helper ---------- */
function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

function cyStyle() {
  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "text-wrap": "wrap",
        "text-max-width": "110px",
        "text-valign": "center",
        "text-halign": "center",
        color: "#0d1117",
        "font-family": MONO,
        "font-size": "11px",
        "font-weight": 600,
        shape: "round-rectangle",
        width: "label",
        height: "label",
        padding: "11px",
        "background-color": (n) => KIND_COLOR[n.data("kind")] || "#8b949e",
        "border-width": 2,
        "border-color": "rgba(255,255,255,0.18)",
      },
    },
    { selector: 'node[kind="gate"]', style: { shape: "diamond", padding: "16px" } },
    { selector: 'node[kind="start"]', style: { shape: "round-rectangle" } },
    {
      selector: "node[?fired]",
      style: { "border-width": 4, "border-color": "#f85149" },
    },
    {
      selector: "node:selected",
      style: { "border-width": 4, "border-color": "#ffffff" },
    },
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        width: 1.5,
        "line-color": "#56606b",
        "target-arrow-color": "#56606b",
        label: "data(label)",
        "font-family": MONO,
        "font-size": "8px",
        color: "#8b949e",
        "text-background-color": "#0d1117",
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-rotation": "autorotate",
      },
    },
    {
      selector: 'edge[condition="precondition_failure"]',
      style: {
        "line-style": "dashed",
        "line-color": "#bc8cff",
        "target-arrow-color": "#bc8cff",
      },
    },
    {
      selector: "edge[?fired]",
      style: {
        "line-color": "#f85149",
        "target-arrow-color": "#f85149",
        color: "#f0a3a0",
        width: 2.5,
      },
    },
  ];
}

function runLayout(graph) {
  try {
    graph
      .layout({ name: "dagre", rankDir: "TB", nodeSep: 45, rankSep: 70, padding: 26 })
      .run();
  } catch (e) {
    console.warn("dagre layout unavailable; using breadthfirst", e);
    graph
      .layout({ name: "breadthfirst", directed: true, padding: 26, spacingFactor: 1.15 })
      .run();
  }
}

async function loadChain(chainId) {
  const res = await fetch(`graph.json?chain=${encodeURIComponent(chainId)}`);
  if (!res.ok) {
    console.error("graph.json failed", res.status);
    return;
  }
  const data = await res.json();
  currentChain = data.chain;

  if (cy) cy.destroy();
  cy = cytoscape({
    container: document.getElementById("cy"),
    elements: data.elements,
    style: cyStyle(),
    wheelSensitivity: 0.25,
    minZoom: 0.2,
    maxZoom: 2.5,
  });
  runLayout(cy);
  cy.on("tap", "node", (evt) => showPrompt(evt.target.id()));
  resetPanel();
  updateOverlayBanner(data.overlay);
}

function updateOverlayBanner(overlay) {
  const banner = document.getElementById("overlay-banner");
  if (!overlay || !overlay.active) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.replaceChildren();
  banner.append(el("b", { text: "run " }));
  const bits = [
    overlay.provider,
    overlay.model,
    overlay.seed != null ? `seed ${overlay.seed}` : null,
    `${overlay.call_count} call${overlay.call_count === 1 ? "" : "s"}`,
  ].filter(Boolean);
  banner.append(document.createTextNode(bits.join(" · ")));
  if (overlay.note) banner.append(el("div", { class: "note", text: overlay.note }));
}

function resetPanel() {
  document.getElementById("panel-empty").hidden = false;
  const body = document.getElementById("panel-body");
  body.hidden = true;
  body.replaceChildren();
}

function codeBlock(text) {
  return el("pre", { class: "code", text: text });
}

async function showPrompt(nodeId) {
  const res = await fetch(
    `prompt/${encodeURIComponent(currentChain)}/${encodeURIComponent(nodeId)}`
  );
  if (!res.ok) return;
  const d = await res.json();

  const body = document.getElementById("panel-body");
  body.replaceChildren();
  document.getElementById("panel-empty").hidden = true;
  body.hidden = false;

  body.append(
    el("h2", { class: "node-title" }, [
      d.label,
      el("span", { class: `kind-badge ${d.kind}`, text: d.kind }),
    ])
  );
  if (d.description) body.append(el("p", { class: "node-desc", text: d.description }));

  if (d.note) body.append(el("p", { class: "note", text: d.note }));

  if (d.template) {
    body.append(el("div", { class: "section-label", text: "template" }));
    body.append(el("div", { class: "template-name", text: `${d.template}.prompty` }));

    const fm = d.frontmatter || {};
    if (fm.inputs && Object.keys(fm.inputs).length) {
      body.append(el("div", { class: "section-label", text: "inputs" }));
      const dl = el("dl", { class: "inputs" });
      for (const [name, meta] of Object.entries(fm.inputs)) {
        dl.append(el("dt", { text: name + (meta.type ? ` : ${meta.type}` : "") }));
        if (meta.description) dl.append(el("dd", { text: meta.description }));
      }
      body.append(dl);
    }

    if (d.error) {
      body.append(el("p", { class: "error", text: d.error }));
    }
    if (d.rendered != null) {
      body.append(el("div", { class: "section-label", text: "rendered (example)" }));
      body.append(codeBlock(d.rendered));
    }
    if (d.raw_source != null) {
      body.append(el("div", { class: "section-label", text: "template source" }));
      body.append(codeBlock(d.raw_source));
    }
  }

  if (Array.isArray(d.actual) && d.actual.length) {
    body.append(
      el("div", { class: "section-label", text: `actual calls (${d.actual.length})` })
    );
    for (const a of d.actual) {
      const card = el("div", { class: "actual-call" });
      const meta = el("div", { class: "actual-meta" });
      meta.append(el("b", { text: a.actor || "?" }));
      meta.append(
        document.createTextNode(
          ` · turn ${a.turn ?? "?"}${a.attempt ? ` · retry ${a.attempt}` : ""}`
        )
      );
      card.append(meta);
      if (a.user) card.append(codeBlock(a.user));
      if (a.response) card.append(codeBlock("→ " + a.response));
      body.append(card);
    }
  }
}

async function init() {
  const body = document.body;
  const select = document.getElementById("chain-select");

  let chains = [];
  try {
    chains = await (await fetch("chains")).json();
  } catch (e) {
    console.error("could not load chains", e);
  }
  for (const c of chains) {
    select.append(el("option", { value: c.id, title: c.description, text: c.label }));
  }

  const def = body.dataset.defaultChain || (chains[0] && chains[0].id);
  if (def) {
    select.value = def;
    await loadChain(def);
  }
  select.addEventListener("change", () => loadChain(select.value));
}

document.addEventListener("DOMContentLoaded", init);
