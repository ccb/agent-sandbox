// CodeRef hides its reference behind a marker and hands the two presentations —
// desktop popup, mobile inline — to CSS. That split is the part worth pinning:
// if the small-screen override is ever dropped while the default `display: none`
// stays, every reference on the page vanishes on a phone and NOTHING fails. No
// DOM needed to catch it, so the stylesheet is read as source, the way
// toc.test.ts reads the page. (Vitest stubs CSS out unless `test.css` is on —
// see vite.config.ts.)
import { describe, expect, it } from "vitest";
import source from "./HomeView.tsx?raw";
import css from "./home.css?raw";

/** The `@media (max-width: 640px)` block, or "" if it isn't there. */
const smallScreen = css.slice(css.indexOf("@media (max-width: 640px)"));

describe("code references", () => {
  it("hides the popup by default", () => {
    expect(css).toContain(".nrf-ref-pop {\n  display: none;");
  });

  it("reveals it on hover and on focus, so tap and keyboard work too", () => {
    expect(css).toContain(".nrf-ref:hover .nrf-ref-pop,\n.nrf-ref:focus-within .nrf-ref-pop");
  });

  it("prints the reference inline on a small screen rather than dropping it", () => {
    expect(smallScreen).toContain(".nrf-ref-mark {\n    display: none;");
    expect(smallScreen).toContain(".nrf-ref-pop {\n    display: inline;");
  });

  it("names a source file in every reference on the page", () => {
    const refs = source.match(/<CodeRef>[\s\S]*?<\/CodeRef>/g) ?? [];
    expect(refs.length).toBeGreaterThan(0);
    for (const ref of refs) {
      expect(ref).toMatch(/\.py<\/code>/);
    }
  });
});
