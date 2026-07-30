import { describe, expect, it } from "vitest";
import { TEX } from "./HomeView";
import { renderTeX } from "./TeX";

// KaTeX is configured with throwOnError: false so a bad formula degrades to red
// text instead of blanking the landing page. That makes this the check that a
// malformed literal never ships.
describe("landing-page formulas", () => {
  it.each(Object.entries(TEX))("%s renders without a KaTeX error", (_name, src) => {
    expect(renderTeX(src, true)).not.toContain("katex-error");
  });

  it("marks malformed TeX instead of throwing", () => {
    expect(renderTeX(String.raw`\frac{1}`, false)).toContain("katex-error");
  });
});
