// Shape of the JSON emitted by scripts/gen_promptviz.py (one file per chain),
// which mirrors promptviz's Flask /graph.json + /prompt responses. The optional
// run-overlay is dropped in the static port, so `fired` is always false here.

export type NodeKind = "start" | "decision" | "parse" | "narrate" | "gate";

export interface CyNode {
  data: {
    id: string;
    label: string;
    kind: NodeKind;
    template: string | null;
    description: string;
    fired: boolean;
  };
}

export interface CyEdge {
  data: {
    id: string;
    source: string;
    target: string;
    label: string;
    condition: string | null;
    fired: boolean;
  };
}

export interface ChainElements {
  nodes: CyNode[];
  edges: CyEdge[];
}

/** One template input declared in a .prompty frontmatter. */
export interface PromptInput {
  type?: string;
  description?: string;
}

/** A node's prompt detail (keyed by node id in `Chain.prompts`). Fields past the
 *  first five appear only for templated nodes (or carry a `note`/`error`). */
export interface PromptDetail {
  id: string;
  label: string;
  kind: NodeKind;
  template: string | null;
  description: string;
  note?: string;
  error?: string;
  rendered?: string;
  raw_source?: string;
  frontmatter?: {
    name?: string;
    description?: string;
    inputs?: Record<string, PromptInput>;
  };
}

export interface Chain {
  chain: string;
  label: string;
  description: string;
  elements: ChainElements;
  prompts: Record<string, PromptDetail>;
}

export interface ChainIndexEntry {
  id: string;
  label: string;
  description: string;
}
