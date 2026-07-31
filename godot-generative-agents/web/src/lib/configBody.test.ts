import { describe, expect, it } from "vitest";
import type { SetupFormState } from "../types/config";
import { buildPostBody, coercePlan, effectivePlan, mergeKnobs, planLocked } from "./configBody";

// A form snapshot where nothing has changed from the server's current values.
const unchanged = (over: Partial<SetupFormState> = {}): SetupFormState => ({
  cast: ["maya", "raj"],
  brain: "mock",
  initialBrain: "mock",
  steps: 1200,
  initialSteps: 1200,
  tick: 0.1,
  initialTick: 0.1,
  maxCost: 0,
  plan: "auto",
  initialPlan: "auto",
  effort: "default",
  initialEffort: "default",
  model: "claude-haiku-4-5-20251001",
  initialModel: "claude-haiku-4-5-20251001",
  knobsCurrent: { game: { agent: { temperature: 0.7 } }, retrieval: { alpha_recency: 1 } },
  knobEdits: {},
  ...over,
});

describe("buildPostBody", () => {
  it("sends only cast when nothing changed", () => {
    expect(buildPostBody(unchanged())).toEqual({ cast: ["maya", "raj"] });
  });

  it("sends brain/steps/tick/plan/effort/model only when they differ", () => {
    const body = buildPostBody(
      unchanged({
        brain: "llm",
        steps: 4320,
        tick: 0.2,
        plan: "schedule",
        effort: "high",
        model: "claude-sonnet-5",
      }),
    );
    expect(body).toMatchObject({
      cast: ["maya", "raj"],
      brain: "llm",
      steps: 4320,
      tick_seconds: 0.2,
      plan: "schedule",
      effort: "high",
      model: "claude-sonnet-5",
    });
  });

  it("sends max_cost only on the llm brain and only when > 0", () => {
    expect(buildPostBody(unchanged({ brain: "mock", maxCost: 5 }))).not.toHaveProperty("max_cost");
    expect(
      buildPostBody(unchanged({ brain: "llm", initialBrain: "llm", maxCost: 0 })),
    ).not.toHaveProperty("max_cost");
    expect(
      buildPostBody(unchanged({ brain: "llm", initialBrain: "llm", maxCost: 5 })),
    ).toMatchObject({
      max_cost: 5,
    });
  });

  it("never sends an empty plan/effort/model even against a mismatched initial", () => {
    const body = buildPostBody(unchanged({ plan: "", effort: "", model: "", initialPlan: "auto" }));
    expect(body).not.toHaveProperty("plan");
    expect(body).not.toHaveProperty("effort");
    expect(body).not.toHaveProperty("model");
  });

  it("sends sim_config as changed knobs merged over current, only when edited", () => {
    expect(buildPostBody(unchanged())).not.toHaveProperty("sim_config");
    const body = buildPostBody(unchanged({ knobEdits: { game: { agent: { temperature: 0.9 } } } }));
    expect(body.sim_config).toEqual({
      game: { agent: { temperature: 0.9 } },
      retrieval: { alpha_recency: 1 },
    });
  });
});

describe("mergeKnobs", () => {
  it("overlays a nested edit without clobbering siblings and never mutates inputs", () => {
    const current = {
      game: { agent: { temperature: 0.7, top_p: 1 } },
      retrieval: { alpha_recency: 1 },
    };
    const edits = { game: { agent: { temperature: 0.2 } } };
    const out = mergeKnobs(current, edits);
    expect(out).toEqual({
      game: { agent: { temperature: 0.2, top_p: 1 } },
      retrieval: { alpha_recency: 1 },
    });
    expect(current.game.agent.temperature).toBe(0.7); // input untouched
  });
});

describe("effectivePlan / planLocked / coercePlan", () => {
  it("resolves auto to schedule on a free brain and llm on the llm brain", () => {
    expect(effectivePlan("auto", "mock")).toBe("schedule");
    expect(effectivePlan("auto", "llm")).toBe("llm");
    expect(effectivePlan("schedule", "llm")).toBe("schedule"); // passthrough
  });

  it("locks the llm planner option off any free brain", () => {
    expect(planLocked("mock")).toBe(true);
    expect(planLocked("scripted")).toBe(true);
    expect(planLocked("llm")).toBe(false);
  });

  it("snaps an llm planner back to auto when the brain isn't llm", () => {
    expect(coercePlan("llm", "mock")).toBe("auto");
    expect(coercePlan("llm", "llm")).toBe("llm");
    expect(coercePlan("schedule", "mock")).toBe("schedule");
  });
});
