// The replay demo is desktop-only (#958), and the whole gate is two CSS media
// blocks: the figure hides, and one of two notes takes its place — "widen the
// window" when it's only a matter of width, "open it on a desktop" when the
// pointer is touch-primary and widening would not help. Drop either block and
// nothing fails — a phone just silently starts pulling ~10 MB of WebAssembly it
// can't be relied on to run. So pin every half, the way CodeRef.test.ts pins its
// own hide/show pair. No DOM needed: the stylesheet is read as source. (Vitest
// stubs CSS out unless `test.css` is on — see vite.config.ts.)
import { describe, expect, it } from "vitest";
import source from "./HomeView.tsx?raw";
import css from "./home.css?raw";

const NARROW = "@media (max-width: 768px) {\n  .nrf-figure--replay";
const TOUCH = "@media (pointer: coarse) {";
const narrowBlock = css.slice(css.indexOf(NARROW), css.indexOf(TOUCH));
const touchBlock = css.slice(css.indexOf(TOUCH));

describe("handheld replay gate", () => {
  it("keeps both notes out of the way by default", () => {
    expect(css).toContain(".nrf-replay-note {\n  display: none;");
  });

  it("hides the figure and offers to be widened on a narrow window", () => {
    expect(css).toContain(NARROW);
    expect(narrowBlock).toContain(".nrf-figure--replay {\n    display: none;");
    expect(narrowBlock).toContain(".nrf-replay-note--narrow {\n    display: block;");
  });

  // Width alone would still serve the demo to a tablet in landscape, which is
  // the touch path nobody has tested — so the coarse-pointer arm is the point.
  it("hides the figure for a touch pointer at any width", () => {
    expect(css).toContain(TOUCH);
    expect(touchBlock).toContain(".nrf-figure--replay {\n    display: none;");
    expect(touchBlock).toContain(".nrf-replay-note--touch {\n    display: block;");
  });

  // A phone matches BOTH blocks. Same specificity, so the later one wins: the
  // touch block must come second AND take the width note back down, or a phone
  // reads "widen this window", which is not something it can do.
  it("shows only the touch note on a phone, which matches both blocks", () => {
    expect(css.indexOf(TOUCH)).toBeGreaterThan(css.indexOf(NARROW));
    expect(touchBlock).toContain(".nrf-replay-note--narrow {\n    display: none;");
  });

  it("renders both notes, each saying the thing its case can act on", () => {
    expect(source).toContain("nrf-replay-note--narrow");
    expect(source).toContain("nrf-replay-note--touch");
    expect(source).toContain("widen it and the demo appears here");
    expect(source).toContain("desktop browser to watch the replay");
  });
});
