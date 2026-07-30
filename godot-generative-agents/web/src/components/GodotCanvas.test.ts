import { describe, expect, it } from "vitest";
import { focusWithoutScroll } from "./GodotCanvas";

// No jsdom here (see the other tests in this package), so stand in a bare object
// with the one method the helper wraps — what we care about is the options the
// engine's own `focus()` calls end up carrying.
function stub() {
  const calls: (FocusOptions | undefined)[] = [];
  const el = { focus: (options?: FocusOptions) => calls.push(options) };
  return { el, calls };
}

describe("focusWithoutScroll", () => {
  it("adds preventScroll to a bare focus() call", () => {
    const { el, calls } = stub();
    focusWithoutScroll(el);
    el.focus();
    expect(calls).toEqual([{ preventScroll: true }]);
  });

  it("wins over a caller that asks to scroll", () => {
    const { el, calls } = stub();
    focusWithoutScroll(el);
    el.focus({ preventScroll: false });
    expect(calls).toEqual([{ preventScroll: true }]);
  });
});
