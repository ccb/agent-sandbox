import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";
import type { ChainElements } from "../../types/promptviz";
import { cyStyle, DAGRE_LAYOUT, FALLBACK_LAYOUT } from "./cytoscapeSetup";

interface Props {
  elements: ChainElements;
  /** Called with the node id when a node is tapped. */
  onSelectNode: (nodeId: string) => void;
}

/**
 * Draws one chain's DAG with Cytoscape + dagre. Ported from promptviz.js: a
 * fresh Cytoscape instance per chain, the dagre top-to-bottom layout (with a
 * breadthfirst fallback), and a tap handler that surfaces the node id.
 */
export function PromptChainGraph({ elements, onSelectNode }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Hold the latest callback in a ref so the effect depends only on `elements`
  // — otherwise a new callback identity would rebuild (and re-fit) the graph.
  const onSelectRef = useRef(onSelectNode);
  onSelectRef.current = onSelectNode;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const cy = cytoscape({
      container,
      elements: { nodes: elements.nodes, edges: elements.edges },
      style: cyStyle(),
      wheelSensitivity: 0.25,
      minZoom: 0.2,
      maxZoom: 2.5,
    });

    try {
      cy.layout(DAGRE_LAYOUT).run();
    } catch (e) {
      console.warn("dagre layout unavailable; using breadthfirst", e);
      cy.layout(FALLBACK_LAYOUT).run();
    }

    cy.on("tap", "node", (evt) => onSelectRef.current(evt.target.id()));

    return () => cy.destroy();
  }, [elements]);

  return <div className="pcv-cy" ref={containerRef} />;
}
