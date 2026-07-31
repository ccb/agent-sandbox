// Pure helpers for reading/writing a single nested knob by path — pulled out
// of SetupView.tsx so the sim_config path logic is unit-testable in plain
// Node, the same way configBody.ts is.

// Read a nested numeric knob out of a knobs dict by path (0 if absent).
export function knobAt(knobs: Record<string, unknown>, path: string[]): number {
  let cur: unknown = knobs;
  for (const seg of path) {
    if (typeof cur !== "object" || cur === null) return 0;
    cur = (cur as Record<string, unknown>)[seg];
  }
  return typeof cur === "number" ? cur : 0;
}

// Set a nested value by path into a fresh nested-dict edit ({a:{b:{c:v}}}).
export function nest(path: string[], value: number): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  let cur = root;
  path.forEach((seg, i) => {
    if (i === path.length - 1) cur[seg] = value;
    else {
      const next: Record<string, unknown> = {};
      cur[seg] = next;
      cur = next;
    }
  });
  return root;
}
