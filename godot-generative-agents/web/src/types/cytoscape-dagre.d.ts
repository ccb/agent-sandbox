// cytoscape-dagre ships no type declarations. Its default export is a Cytoscape
// extension (a function passed to `cytoscape.use`), so type it as such.
declare module "cytoscape-dagre" {
  import type { Ext } from "cytoscape";
  const ext: Ext;
  export default ext;
}
