import { describe, expect, it } from "vitest";
// No jsdom in this package — test the exported data and pure helpers, and pin
// the section's claims to their sources so prose and data can't drift.
import { HIGHLIGHTS, RUN, stepClock } from "./CaseStudySection";
import { BASELINE_REPLICATES } from "./CostSection";

describe("stepClock", () => {
  it("starts the day at 08:00", () => {
    expect(stepClock(0)).toBe("08:00");
  });

  it("matches the run log's clock for a mid-day step", () => {
    // Batch 12's write-up places Mateo's AV report at 09:29 (step 537).
    expect(stepClock(537)).toBe("09:29");
  });

  it("ends the 4,320-step day one step shy of 20:00", () => {
    expect(stepClock(4319)).toBe("19:59");
    expect(stepClock(4320)).toBe("20:00");
  });
});

describe("the showcase run's provenance", () => {
  it("is the frozen #878 pick", () => {
    expect(RUN.id).toBe("run-20260730-150317-7ed039");
    expect(RUN.agents).toBe(5);
    expect(RUN.steps).toBe(4320);
  });

  it("quotes the cost from the cost section's pinned replicates, not a copy", () => {
    expect(RUN.costUsd).toBe(BASELINE_REPLICATES[0]);
    // …and that replicate is batch 12's $5.37 day, per the #760 run log.
    expect(RUN.costUsd).toBeCloseTo(5.37, 2);
  });
});

describe("the highlight table", () => {
  it("lists moments in step order, within the day", () => {
    const steps = HIGHLIGHTS.map((h) => h.step);
    expect(steps).toEqual([...steps].sort((a, b) => a - b));
    expect(steps[0]).toBeGreaterThanOrEqual(0);
    expect(steps[steps.length - 1]).toBeLessThan(RUN.steps);
  });

  it("opens at the first frame and closes in the evening", () => {
    expect(stepClock(HIGHLIGHTS[0].step)).toBe("08:00");
    expect(stepClock(HIGHLIGHTS[HIGHLIGHTS.length - 1].step)).toBe("19:11");
  });
});
