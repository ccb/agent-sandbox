// The GET /config surface (#732) and the setup form's state. Every option the
// form offers comes from this surface — the client hard-codes no cast, brain,
// plan, effort, or model list (mirrors godot/scripts/simulation_setup.gd).

// The config view's resolved status. "configurable"/"locked" mirror the
// server's GET /config `status`; the rest are client-side outcomes.
export type ConfigStatus =
  | "loading"
  | "configurable"
  | "locked"
  | "unavailable" // 404 — this server has no config surface
  | "error"; // transport or non-404 HTTP error

// The catalog comes from the server's library_personas (build_world.py), which
// emits {id, name, blurb, in_default_cast} — no emoji, no description.
export interface PersonaEntry {
  id: string;
  name: string;
  blurb?: string;
  in_default_cast?: boolean;
}

// GET /config's `run` block: what is currently set.
export interface ConfigRun {
  brain: string;
  plan: string;
  plan_request: string; // the RAW ask ("auto" until opted out) — the dropdown default
  effort: string;
  model: string;
  steps: number;
  stop_time?: string | null;
  max_cost: number | null;
  tick_seconds: number;
}

export interface ConfigSurface {
  status: "configurable" | "locked";
  personas: PersonaEntry[]; // the library catalog
  cast: string[]; // persona ids currently active
  knobs: { defaults: Record<string, unknown>; current: Record<string, unknown> };
  brains: string[];
  plans: string[];
  efforts: string[];
  models: string[];
  run: ConfigRun;
}

// A snapshot of the form, in the shape buildPostBody consumes. `initial*` are
// the server's current values (from ConfigSurface.run) so we can send only what
// changed. `knobEdits` is a nested dict of CHANGED knobs only.
export interface SetupFormState {
  cast: string[];
  brain: string;
  initialBrain: string;
  steps: number;
  initialSteps: number;
  tick: number;
  initialTick: number;
  maxCost: number; // 0 = unset
  plan: string;
  initialPlan: string;
  effort: string; // "" = no effort row; "default" = send no thinking config
  initialEffort: string;
  model: string;
  initialModel: string;
  knobsCurrent: Record<string, unknown>;
  knobEdits: Record<string, unknown>;
}

// POST /config body — every field optional except cast (the "omit = keep
// current" contract).
export interface PostConfigBody {
  cast: string[];
  brain?: string;
  steps?: number;
  tick_seconds?: number;
  max_cost?: number;
  plan?: string;
  effort?: string;
  model?: string;
  sim_config?: Record<string, unknown>;
}
