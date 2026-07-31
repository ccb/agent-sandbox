// Pure builder for the POST /config body from the setup form — the TS mirror of
// godot/scripts/config_body.gd. No React, no fetch: unit-testable in plain Node,
// the same way config_body.gd is testable without a Godot scene.
//
// Only fields the user CHANGED from the server's current values are sent (POST
// /config's "omit = keep current" contract), except `cast`, which is always
// sent. `max_cost` rides only with the llm brain — the backend 400s it otherwise.

import type { PostConfigBody, SetupFormState } from "../types/config";

const approxEqual = (a: number, b: number): boolean => Math.abs(a - b) < 1e-9;

export function buildPostBody(s: SetupFormState): PostConfigBody {
  const body: PostConfigBody = { cast: s.cast };
  if (s.brain !== s.initialBrain) body.brain = s.brain;
  if (s.steps !== s.initialSteps) body.steps = s.steps;
  if (!approxEqual(s.tick, s.initialTick)) body.tick_seconds = s.tick;
  if (s.brain === "llm" && s.maxCost > 0) body.max_cost = s.maxCost;
  // Empty-guarded: an empty plan/effort/model would 400 server-side, so it is
  // never sent even against a mismatched initial. "default" effort is a real
  // value, not an absence.
  if (s.plan !== "" && s.plan !== s.initialPlan) body.plan = s.plan;
  if (s.effort !== "" && s.effort !== s.initialEffort) body.effort = s.effort;
  if (s.model !== "" && s.model !== s.initialModel) body.model = s.model;
  if (Object.keys(s.knobEdits).length > 0) {
    body.sim_config = mergeKnobs(s.knobsCurrent, s.knobEdits);
  }
  return body;
}

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

// Overlay CHANGED knobs onto a deep copy of the server's current knobs, so
// untouched keys round-trip unchanged. Recursive so a nested edit (e.g.
// game.agent.temperature) doesn't clobber siblings; inputs are never mutated.
export function mergeKnobs(
  current: Record<string, unknown>,
  edits: Record<string, unknown>,
): Record<string, unknown> {
  const out = structuredClone(current);
  deepMerge(out, edits);
  return out;
}

function deepMerge(into: Record<string, unknown>, edits: Record<string, unknown>): void {
  for (const k of Object.keys(edits)) {
    const v = edits[k];
    if (isPlainObject(v) && isPlainObject(into[k])) {
      deepMerge(into[k] as Record<string, unknown>, v);
    } else {
      into[k] = isPlainObject(v) ? structuredClone(v) : v;
    }
  }
}

// The planner a selection will actually run — the client-side mirror of
// serve_penn._resolve_plan_mode. KEEP IN STEP with that function. Cosmetic (the
// hint label only); the server stays the authority.
export function effectivePlan(plan: string, brain: string): string {
  if (plan !== "auto") return plan;
  return brain === "llm" ? "llm" : "schedule";
}

// The llm planner can't run on a free brain, so its option is disabled there.
export function planLocked(brain: string): boolean {
  return brain !== "llm";
}

// When the brain moves to a free one, an llm planner selection snaps back to
// auto (#791) — an untouched auto still means "keep the session's request".
export function coercePlan(plan: string, brain: string): string {
  return plan === "llm" && brain !== "llm" ? "auto" : plan;
}
