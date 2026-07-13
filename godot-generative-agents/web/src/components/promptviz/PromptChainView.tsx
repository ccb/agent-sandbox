import { useEffect, useState } from "react";
import type { Chain, ChainIndexEntry } from "../../types/promptviz";
import { PromptChainGraph } from "./PromptChainGraph";
import { PromptPanel } from "./PromptPanel";
import "./promptviz.css";

// Static JSON written by scripts/gen_promptviz.py (pnpm gen:promptviz). BASE_URL
// keeps it correct if the app is ever served under a sub-path.
const PROMPTVIZ_BASE = `${import.meta.env.BASE_URL}promptviz/`;

const LEGEND = [
  { kind: "start", label: "start" },
  { kind: "decision", label: "decision (LLM)" },
  { kind: "parse", label: "parse (LLM)" },
  { kind: "narrate", label: "narrate (LLM)" },
  { kind: "gate", label: "gate (no LLM)" },
];

/**
 * The "Prompt chains" view: a chain selector, the Cytoscape DAG, a legend, and a
 * side panel that shows the clicked node's prompt. Ported from promptviz's Flask
 * single-page app — here the graph + prompts come from precomputed static JSON
 * instead of live /graph.json and /prompt endpoints.
 */
export function PromptChainView() {
  const [chains, setChains] = useState<ChainIndexEntry[] | null>(null);
  const [chainId, setChainId] = useState<string | null>(null);
  const [chain, setChain] = useState<Chain | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  // Load the chain index once; default to the first chain.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${PROMPTVIZ_BASE}chains.json`);
        if (!res.ok) throw new Error(`HTTP ${res.status} fetching chains.json`);
        const list = (await res.json()) as ChainIndexEntry[];
        if (cancelled) return;
        setChains(list);
        if (list.length) setChainId(list[0].id);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Load the selected chain whenever it changes.
  useEffect(() => {
    if (!chainId) return;
    let cancelled = false;
    setChain(null);
    setSelectedNode(null);
    (async () => {
      try {
        const res = await fetch(`${PROMPTVIZ_BASE}${chainId}.json`);
        if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${chainId}.json`);
        const data = (await res.json()) as Chain;
        if (!cancelled) setChain(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chainId]);

  const detail = chain && selectedNode ? (chain.prompts[selectedNode] ?? null) : null;

  return (
    <div className="pcv">
      <header className="pcv-topbar">
        <div className="pcv-brand">
          <span className="pcv-logo" aria-hidden="true">
            ⛓
          </span>
          <span className="pcv-name">Prompt Chain Visualizer</span>
        </div>
        <div className="pcv-controls">
          <label htmlFor="pcv-chain-select">chain</label>
          <select
            id="pcv-chain-select"
            value={chainId ?? ""}
            onChange={(e) => setChainId(e.target.value)}
          >
            {(chains ?? []).map((c) => (
              <option key={c.id} value={c.id} title={c.description}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      <main className="pcv-layout">
        <section className="pcv-graph-pane">
          {error && <div className="pcv-status pcv-error">{error}</div>}
          {!error && !chain && <div className="pcv-status">Loading…</div>}
          {chain && <PromptChainGraph elements={chain.elements} onSelectNode={setSelectedNode} />}
          <ul className="pcv-legend" aria-label="legend">
            {LEGEND.map((item) => (
              <li key={item.kind}>
                <span className={`pcv-swatch k-${item.kind}`} />
                {item.label}
              </li>
            ))}
          </ul>
        </section>
        <aside className="pcv-panel" aria-live="polite">
          <PromptPanel detail={detail} />
        </aside>
      </main>
    </div>
  );
}
