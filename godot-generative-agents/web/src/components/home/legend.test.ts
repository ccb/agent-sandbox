import { describe, expect, it } from "vitest";
import { SIDEBAR_LEGEND } from "./HomeView";

// The legend under the replay demo points at PNGs exported from the viewer's own
// sidebar by godot/tools/export_sidebar_icons.gd. A renamed or missing export is a
// broken image on the landing page and nothing a type error would catch — so pin
// each entry to a file that really exists. `import.meta.glob` is Vite's own
// (eager: we only want the keys), which keeps this test free of @types/node, same
// reason toc.test.ts reads the page with `?raw` instead of node:fs.
const FILES = Object.keys(import.meta.glob("../../../public/sidebar-icons/*.png"));

describe("replay-demo sidebar legend", () => {
  const withIcons = SIDEBAR_LEGEND.filter((e) => e.icon);

  it("has icon entries to check", () => {
    expect(withIcons.length).toBeGreaterThan(0);
  });

  it.each(withIcons.map((e) => [e.icon as string]))("%s exists in public/", (icon) => {
    expect(FILES.some((f) => f.endsWith(`/${icon}`))).toBe(true);
  });

  it("exports no icon the legend has stopped using", () => {
    const used = new Set(withIcons.map((e) => e.icon));
    expect(FILES.filter((f) => !used.has(f.split("/").pop() as string))).toEqual([]);
  });
});
