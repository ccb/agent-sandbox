import { describe, expect, it } from "vitest";
// The contents nav is a list of ids that must exist as elements on the page. A
// stale entry is a dead link AND a hole in the scroll-spy, and neither shows up
// as a type error — so check the source for the target, which needs no DOM.
// Vite's `?raw` hands the file over as a string; `node:fs` would mean pulling in
// @types/node just for this test.
//
// The page is split across several files: the engine and Cost sections live in
// their own components (HomeView.tsx was already 745 lines), so all are
// searched, and page order is checked against their concatenation in render
// order.
import caseStudySource from "./CaseStudySection.tsx?raw";
import costSource from "./CostSection.tsx?raw";
import homeSource from "./HomeView.tsx?raw";
import implSource from "./ImplementationSection.tsx?raw";
import reflectionsSource from "./ReflectionsSection.tsx?raw";
import { TOC } from "./toc";

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

  it("numbers top-level sections, subsections, and appendix entries", () => {
    expect(TOC[0].number).toBeUndefined();
    expect(TOC[1].number).toBeUndefined();
    expect(TOC[2]).toMatchObject({ id: "case-study", number: "1" });
    expect(TOC[3]).toMatchObject({ id: "case-cast", number: "1.1" });
    expect(TOC[7]).toMatchObject({ id: "case-verdict", number: "1.5" });
    expect(TOC[8]).toMatchObject({ id: "architecture", number: "2" });
    expect(TOC[9]).toMatchObject({ id: "world", number: "2.1" });
    expect(TOC[15]).toMatchObject({ id: "decision", number: "2.7" });
    expect(TOC[20]).toMatchObject({ id: "reflections", number: "5" });
    expect(TOC[21]).toMatchObject({ id: "limitations", number: "6" });
    expect(TOC[22].id).toBe("appendix");
    expect(TOC[22].number).toBeUndefined();
    expect(TOC[23]).toMatchObject({ id: "acknowledgements", number: "A.1", sub: true });
    expect(TOC[25]).toMatchObject({ id: "references", number: "A.3", sub: true });
    expect(TOC.find((e) => e.id === "BibTeX")).toBeUndefined();
    expect(source).toContain('id="BibTeX"');
  });
});
