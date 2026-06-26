import cytoscape from "cytoscape";
import dagre from "cytoscape-dagre";
import type { NodeKind } from "../../types/promptviz";

// Register the dagre layout once for the whole app (module load runs a single
// time, so we never double-register).
cytoscape.use(dagre);

const MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';

// Node fill by kind. Keep in sync with the --k-* CSS vars in promptviz.css
// (legend swatches + kind badges) — these are applied by the Cytoscape
// stylesheet, those by CSS. Ported from promptviz.js KIND_COLOR.
export const KIND_COLOR: Record<NodeKind, string> = {
  start: "#8b949e",
  decision: "#58a6ff",
  parse: "#d29922",
  narrate: "#3fb950",
  gate: "#bc8cff",
};

// The Cytoscape stylesheet, ported verbatim from promptviz.js cyStyle(). The
// per-kind background colors that were a JS mapper there are expressed here as
// one selector per kind (fully typed, no function mappers).
//
// @types/cytoscape's style-property typing is incomplete (e.g. text-background-*
// and text-rotation), so we assert the array's type rather than fight it — the
// values are validated by actually rendering the graph, not by the compiler.
export function cyStyle(): cytoscape.Stylesheet[] {
  const kindRules = (Object.keys(KIND_COLOR) as NodeKind[]).map((kind) => ({
    selector: `node[kind="${kind}"]`,
    style: { "background-color": KIND_COLOR[kind] },
  }));

  const rules = [
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
        "background-color": "#8b949e",
        "border-width": 2,
        "border-color": "rgba(255,255,255,0.18)",
      },
    },
    ...kindRules,
    { selector: 'node[kind="gate"]', style: { shape: "diamond", padding: "16px" } },
    { selector: "node[?fired]", style: { "border-width": 4, "border-color": "#f85149" } },
    { selector: "node:selected", style: { "border-width": 4, "border-color": "#ffffff" } },
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

  return rules as unknown as cytoscape.Stylesheet[];
}

// dagre layout opts (top-to-bottom DAG), ported from promptviz.js. @types don't
// model the dagre extension's options, so assert the type.
export const DAGRE_LAYOUT = {
  name: "dagre",
  rankDir: "TB",
  nodeSep: 45,
  rankSep: 70,
  padding: 26,
} as unknown as cytoscape.LayoutOptions;

// Fallback if the dagre extension ever fails to register.
export const FALLBACK_LAYOUT = {
  name: "breadthfirst",
  directed: true,
  padding: 26,
  spacingFactor: 1.15,
} as unknown as cytoscape.LayoutOptions;
