import { describe, expect, it } from "vitest";
import { tameFocus } from "./GodotCanvas";

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
