import { describe, expect, it } from "vitest";
// The contents nav is a list of ids that must exist as elements on the page. A
// stale entry is a dead link AND a hole in the scroll-spy, and neither shows up
// as a type error — so check the source for the target, which needs no DOM.
// Vite's `?raw` hands the file over as a string; `node:fs` would mean pulling in
// @types/node just for this test.
//
// The page is split across several files: the Implementation and Cost sections
// live in their own components (HomeView.tsx was already 745 lines), so all are
// searched, and page order is checked against their concatenation in render
// order.
import caseStudySource from "./CaseStudySection.tsx?raw";
import costSource from "./CostSection.tsx?raw";
import { TOC } from "./HomeView";
import homeSource from "./HomeView.tsx?raw";
import implSource from "./ImplementationSection.tsx?raw";
import reflectionsSource from "./ReflectionsSection.tsx?raw";

// HomeView renders each section component partway down, so splicing the
// components' source in at their call sites reproduces the rendered id order.
const MOUNTS: [string, string][] = [
  ["<CaseStudySection />", caseStudySource],
  ["<ImplementationSection />", implSource],
  ["<CostSection />", costSource],
  ["<ReflectionsSection />", reflectionsSource],
];
const source = MOUNTS.reduce((acc, [mount, src]) => acc.replace(mount, src), homeSource);

describe("landing-page contents nav", () => {
  it.each(MOUNTS.map(([mount]) => [mount]))("splices %s in at its mount point", (mount) => {
    expect(homeSource).toContain(mount);
  });

  it.each(TOC.map((e) => [e.id, e.label]))("%s points at a real target", (id) => {
    expect(source).toContain(`id="${id}"`);
  });

  it("lists its entries in page order", () => {
    const positions = TOC.map((e) => source.indexOf(`id="${e.id}"`));
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });
});
