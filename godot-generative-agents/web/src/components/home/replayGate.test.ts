// The replay demo is desktop-only (#958), and the whole gate is one CSS media
// block: the figure hides, .nrf-replay-note takes its place. Drop the block and
// nothing fails — a phone just silently starts pulling ~10 MB of WebAssembly it
// can't be relied on to run. So pin both halves, the way CodeRef.test.ts pins
// its own hide/show pair. No DOM needed: the stylesheet is read as source.
// (Vitest stubs CSS out unless `test.css` is on — see vite.config.ts.)
import { describe, expect, it } from "vitest";
import source from "./HomeView.tsx?raw";
import css from "./home.css?raw";

const GATE = "@media (pointer: coarse), (max-width: 768px)";
/** The gate's block, or "" if it isn't there. */
const handheld = css.slice(css.indexOf(GATE));

describe("handheld replay gate", () => {
  it("keeps the note out of the way on a desktop", () => {
    expect(css).toContain(".nrf-replay-note {\n  display: none;");
  });

  it("hides the replay figure and shows the note under the gate", () => {
    expect(css).toContain(GATE);
    expect(handheld).toContain(".nrf-figure--replay {\n    display: none;");
    expect(handheld).toContain(".nrf-replay-note {\n    display: block;");
  });

  // Width alone would still serve the demo to a tablet in landscape, which is
  // the touch path nobody has tested — so the coarse-pointer arm is the point.
  it("gates on touch as well as width", () => {
    expect(GATE).toContain("(pointer: coarse)");
  });

  it("renders the note that replaces the figure", () => {
    expect(source).toContain('className="nrf-replay-note"');
    expect(source).toContain("desktop browser to watch the replay");
  });
});
