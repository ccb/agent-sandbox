// CodeRef hides its reference behind a marker and hands the two presentations —
// desktop popup, mobile inline — to CSS. That split is the part worth pinning:
// if the small-screen override is ever dropped while the default `display: none`
// stays, every reference on the page vanishes on a phone and NOTHING fails. No
// DOM needed to catch it, so the stylesheet is read as source, the way
// toc.test.ts reads the page. (Vitest stubs CSS out unless `test.css` is on —
// see vite.config.ts.)
import { describe, expect, it } from "vitest";
import caseStudy from "./CaseStudySection.tsx?raw";
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

  it("keeps the link visibly a link in both presentations", () => {
    // The bubble is an <a>: on the dark fill the underline is the only affordance
    // (the browser's blue is unreadable there and is overridden), and inline on a
    // phone there is no bubble and no marker either, so the underline is all that
    // is left. Lose it in either place and the reference silently stops looking
    // clickable.
    expect(css).toContain(
      ".nrf-ref-pop:hover,\n.nrf-ref-pop:focus-visible {\n  text-decoration: underline;",
    );
    expect(smallScreen).toContain("text-decoration: underline;");
  });

  it("names a source file in every reference on the page, and links it", () => {
    const refs = [...source.matchAll(/<CodeRef[\s\S]*?<\/CodeRef>/g)].map((m) => m[0]);
    const caseRefs = [...caseStudy.matchAll(/<CodeRef[\s\S]*?<\/CodeRef>/g)].map((m) => m[0]);
    expect(refs.length).toBeGreaterThan(0);
    expect(caseRefs.length).toBeGreaterThan(0);
    for (const ref of [...refs, ...caseRefs]) {
      expect(ref).toMatch(/\.py<\/code>/);
      // `at` is what carries the file and line (codeRefs.ts). A reference without
      // one wouldn't compile, but the regex above is also how a new reference gets
      // counted, so assert it here rather than trusting the type alone.
      expect(ref).toMatch(/<CodeRef at="\w+">/);
    }
  });
});
