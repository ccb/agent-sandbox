import { describe, expect, it } from "vitest";
import {
  AGENT_POINTS,
  BASELINE,
  BASELINE_REPLICATES,
  COGNITION_BARS,
  DURATION_POINTS,
  niceMax,
} from "./CostSection";

// Every cost on the page is a measurement, pinned here to the values recorded
// in godot-generative-agents/runs/cost-scaling/cost_scaling.csv (issue #921;
// canonical cost = each run's usage.json total_cost_usd). If a chart constant
// drifts from the CSV, this is the test that says so.
const CSV = {
  A1: 0.518008,
  A3: 3.157274,
  A5: [5.37355, 5.381057, 6.818001], // batch-12, batch-10, batch-11 replicates
  A7: 8.574769,
  D1080: 1.377269,
  D2160: 2.957218,
  COFF: 7.070765,
};

describe("the cost data", () => {
  it("baseline replicates match the CSV", () => {
    expect(BASELINE_REPLICATES).toEqual(CSV.A5);
    expect(BASELINE.lo).toBe(Math.min(...CSV.A5));
    expect(BASELINE.hi).toBe(Math.max(...CSV.A5));
    expect(BASELINE.cost).toBeCloseTo(5.8575, 3);
  });

  it("agents axis matches the CSV, in cast-size order", () => {
    expect(AGENT_POINTS.map((p) => [p.x, p.cost])).toEqual([
      [1, CSV.A1],
      [3, CSV.A3],
      [5, BASELINE.cost],
      [7, CSV.A7],
    ]);
  });

  it("duration axis matches the CSV, in sim-hours order", () => {
    expect(DURATION_POINTS.map((p) => [p.x, p.cost])).toEqual([
      [3, CSV.D1080],
      [6, CSV.D2160],
      [12, BASELINE.cost],
    ]);
  });

  it("the cognition comparison matches the CSV", () => {
    expect(COGNITION_BARS[0].cost).toBe(BASELINE.cost);
    expect(COGNITION_BARS[1].cost).toBe(CSV.COFF);
  });
});

describe("niceMax", () => {
  it("rounds an axis up to a round number", () => {
    expect(niceMax(6.82)).toBe(8);
    expect(niceMax(5.86)).toBe(6);
    expect(niceMax(0.52)).toBeCloseTo(0.6); // 6 * 0.1 — floating point, hence closeTo
    expect(niceMax(10)).toBe(10);
  });
});
