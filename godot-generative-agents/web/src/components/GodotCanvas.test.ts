import { describe, expect, it } from "vitest";
import { bufferSize, tameFocus, unsupportedFeatures } from "./GodotCanvas";
// Read as text, the way replayGate.test.ts reads HomeView: the preflight's whole
// point is WHERE it sits in the boot sequence, and there's no DOM here to boot into.
import source from "./GodotCanvas.tsx?raw";

// No jsdom here (see the other tests in this package), so stand in a bare object
// with the one method the helper wraps — what we care about is whether the
// engine's own `focus()` calls go through, and with which options.
function stub() {
  const calls: (FocusOptions | undefined)[] = [];
  const el = { focus: (options?: FocusOptions) => calls.push(options) };
  return { el, calls };
}

describe("tameFocus", () => {
  it("lets a focus call through, without the scroll", () => {
    const { el, calls } = stub();
    tameFocus(el, () => false);
    el.focus();
    expect(calls).toEqual([{ preventScroll: true }]);
  });

  it("wins over a caller that asks to scroll", () => {
    const { el, calls } = stub();
    tameFocus(el, () => false);
    el.focus({ preventScroll: false });
    expect(calls).toEqual([{ preventScroll: true }]);
  });

  it("drops the call entirely while the reader is elsewhere", () => {
    const { el, calls } = stub();
    let elsewhere = true;
    tameFocus(el, () => elsewhere);
    el.focus();
    expect(calls).toEqual([]);
    // …and takes it again once they're back in the demo — the guard is read per
    // call, so a stale snapshot of it would leave the canvas permanently deaf.
    elsewhere = false;
    el.focus();
    expect(calls).toEqual([{ preventScroll: true }]);
  });
});

describe("bufferSize", () => {
  it("scales the box's CSS size by the device pixel ratio, floored", () => {
    expect(bufferSize(1280.6, 719.4, 2)).toEqual([2561, 1438]);
  });

  it("is the identity at DPR 1 on integer boxes at or above the design base", () => {
    expect(bufferSize(1920, 1080, 1)).toEqual([1920, 1080]);
  });

  it("never emits a zero-sized buffer — a hidden box must not kill the GL context", () => {
    expect(bufferSize(0, 0, 2)).toEqual([1, 1]);
  });

  // #952: below the 1920×1080 design base, Godot's canvas_items stretch would
  // downscale nearest-filtered pixel art — floor the buffer at base instead and
  // let the browser do the (linear, smooth) downscale into the box.
  it("floors the buffer at the design base when the box is smaller", () => {
    expect(bufferSize(960, 540, 1)).toEqual([1920, 1080]);
  });

  it("floors fractional sub-base sizes too, not just integer divisors", () => {
    expect(bufferSize(1280, 720, 1)).toEqual([1920, 1080]);
  });

  it("keeps the box's shape when flooring — aspect decides the letterbox, not us", () => {
    // k = max(1, 1920/800, 1080/800) = 2.4 — one uniform scale, no distortion.
    expect(bufferSize(800, 800, 1)).toEqual([1920, 1920]);
  });

  it("does not floor a box the device pixel ratio already carries past base", () => {
    expect(bufferSize(1280, 720, 2)).toEqual([2560, 1440]);
  });
});

// #957. On a page that isn't cross-origin isolated, startGame() neither returns nor
// rejects: it pulls all ~53 MB of index.wasm + index.pck, can't spawn its worker
// pool, and sits on "Starting…" forever. Nothing to catch — so the check has to
// happen first, and be able to say something useful when it fails.
const ADVICE = " - Check that the web server configuration sends the correct headers.";

describe("unsupportedFeatures", () => {
  // null, not [] — this is the go/no-go the effect branches on, so "nothing missing"
  // has to be falsy or every browser gets the fallback.
  it("is null when the engine reports nothing missing", () => {
    expect(unsupportedFeatures([], true)).toBeNull();
  });

  it("keeps the feature name and drops the engine's server-config advice", () => {
    expect(unsupportedFeatures([`SharedArrayBuffer${ADVICE}`], true)).toEqual([
      "SharedArrayBuffer",
    ]);
  });

  it("names every gap, in the engine's order", () => {
    expect(
      unsupportedFeatures([`Cross-Origin Isolation${ADVICE}`, `SharedArrayBuffer${ADVICE}`], true),
    ).toEqual(["Cross-Origin Isolation", "SharedArrayBuffer"]);
  });

  // The engine's list assumes WebAssembly rather than checking for it, and a browser
  // with no WASM at all is the plainest case for this fallback.
  it("leads with WebAssembly when the browser has none", () => {
    expect(unsupportedFeatures([], false)).toEqual(["WebAssembly"]);
    expect(unsupportedFeatures(["WebGL2 - Check web browser configuration"], false)).toEqual([
      "WebAssembly",
      "WebGL2",
    ]);
  });

  it("leaves a name with no advice tail alone", () => {
    expect(unsupportedFeatures(["WebGL2"], true)).toEqual(["WebGL2"]);
  });

  it("blocks a WASM-less browser even when the engine found nothing else", () => {
    expect(unsupportedFeatures([], false)).not.toBeNull();
  });
});

describe("the preflight's place in the boot sequence", () => {
  // A check that runs after the engine is built has already cost the reader the
  // download it exists to avoid, so pin the order, not just the call.
  it("asks the engine what's missing before constructing it", () => {
    const asked = source.indexOf("getMissingFeatures({ threads: true })");
    const built = source.indexOf("new window.Engine(");
    expect(asked).toBeGreaterThan(-1);
    expect(built).toBeGreaterThan(-1);
    expect(asked).toBeLessThan(built);
  });

  it("bails out of the effect instead of starting the game", () => {
    const bail = source.indexOf("setBlocked(missing)");
    expect(bail).toBeGreaterThan(-1);
    expect(bail).toBeLessThan(source.indexOf("engine.startGame()"));
    // `return` on the line after setBlocked — without it the engine starts anyway.
    expect(source.slice(bail, bail + 60)).toContain("return;");
  });

  it("offers the reader the local route rather than a raw engine error", () => {
    expect(source).toContain("can’t run the replay demo");
    expect(source).toContain("“Run locally” below");
  });
});
