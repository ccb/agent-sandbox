import { describe, expect, it } from "vitest";
import { bufferSize, tameFocus } from "./GodotCanvas";

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
