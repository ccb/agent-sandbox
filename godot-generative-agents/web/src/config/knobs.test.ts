import { describe, expect, it } from "vitest";
import { knobAt, nest } from "./knobs";

describe("knobAt", () => {
  it("reads a nested numeric value by path", () => {
    const knobs = { game: { agent: { temperature: 0.7 } } };
    expect(knobAt(knobs, ["game", "agent", "temperature"])).toBe(0.7);
  });

  it("returns 0 when the path is absent", () => {
    const knobs = { game: { agent: { temperature: 0.7 } } };
    expect(knobAt(knobs, ["game", "agent", "missing"])).toBe(0);
    expect(knobAt(knobs, ["nope"])).toBe(0);
  });

  it("returns 0 when the value is non-numeric", () => {
    const knobs = { game: { agent: { temperature: "hot" } } };
    expect(knobAt(knobs, ["game", "agent", "temperature"])).toBe(0);
  });
});

describe("nest", () => {
  it("builds a deep nested-dict edit from a multi-segment path", () => {
    expect(nest(["a", "b", "c"], 5)).toEqual({ a: { b: { c: 5 } } });
  });

  it("builds a single-segment edit", () => {
    expect(nest(["x"], 2)).toEqual({ x: 2 });
  });
});
