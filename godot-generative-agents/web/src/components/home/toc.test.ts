import { describe, expect, it } from "vitest";
import { TOC } from "./HomeView";
// The contents nav is a list of ids that must exist as elements on the page. A
// stale entry is a dead link AND a hole in the scroll-spy, and neither shows up
// as a type error — so check the source for the target, which needs no DOM.
// Vite's `?raw` hands the file over as a string; `node:fs` would mean pulling in
// @types/node just for this test.
//
// The page is split across two files: the Implementation section lives in its
// own component (HomeView.tsx was already 745 lines), so both are searched, and
// page order is checked against their concatenation in render order.
import homeSource from "./HomeView.tsx?raw";
import implSource from "./ImplementationSection.tsx?raw";

// HomeView renders <ImplementationSection /> partway down, so splicing the
// component's source in at that call site reproduces the rendered id order.
const MOUNT = "<ImplementationSection />";
const source = homeSource.replace(MOUNT, implSource);

describe("landing-page contents nav", () => {
  it("splices the section source in at its mount point", () => {
    expect(homeSource).toContain(MOUNT);
  });

  it.each(TOC.map((e) => [e.id, e.label]))("%s points at a real target", (id) => {
    expect(source).toContain(`id="${id}"`);
  });

  it("lists its entries in page order", () => {
    const positions = TOC.map((e) => source.indexOf(`id="${e.id}"`));
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });
});
