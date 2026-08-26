// MIRROR of the pinned replay data-contract (#305). The source of truth is
// backend/contract.py (schema prose + SCHEMA_VERSION + pinned field order) and
// backend/contract_models.py (the enforcing Pydantic models); a Python test
// (tests/test_replay_contract.py) asserts these interfaces stay field-for-field
// in lock-step, so edit the Python side first.
//
// Shape of penn_replay.json, written by backend/penn/generate_penn_replay.py
// and played by scripts/viewer.gd; the live handshake (GET /live) serves the
// same meta shape minus `steps`, plus a live-only `llm`. Fields marked ? are
// absent from replay files baked before the field existed.

export interface Persona {
  name: string;
  emoji: string;
  /** Persona blurb for the State Details inspector (issue #408). */
  persona?: string;
  /** Home address, e.g. "UPenn:Fisher-Hassenfeld". */
  home?: string;
  /** The authored day plan (normalized stops). */
  schedule?: ScheduleStop[];
}

/** One stop of a persona's authored day plan. */
export interface ScheduleStop {
  place: string;
  activity: string;
  emoji: string;
  /** Steps to stay; null = remains for the rest of the day. */
  steps: number | null;
}

/** One t=0 seed social-graph edge (viewer's social-graph pop-up, #252). */
export interface RelationshipEdge {
  a: string;
  b: string;
  kind: string;
  /** 1..5. */
  closeness: number;
  description: string;
}

/** What is driving the cast on a live run (null under the mock brain). */
export interface LlmInfo {
  provider: string;
  model: string;
  /** Thinking depth the run drove at (#960) — part of "which brain was
   * this?"; null/absent when the provider default applied. */
  effort?: string | null;
  /** The #368 per-role model-tiering map; null/absent when untiered. */
  models?: Record<string, string> | null;
}

export interface ReplayMeta {
  /** The contract version this file conforms to (backend/contract.py). */
  schema_version?: string;
  /** Pixels per tile (16 for the campus map). */
  tile_px: number;
  /** Map size in tiles. */
  width: number;
  height: number;
  /** Number of steps (== frames.length). Absent on the LIVE meta (a running
   * sim doesn't know its length up front). */
  steps: number;
  /** In-game seconds represented by one step (for a wall-clock label). */
  sec_per_step: number;
  /** Sim-start wall clock, "YYYY-MM-DD HH:MM:SS". */
  start?: string;
  /** Perception radius (tiles) -- the viewer's tracking-fog radius. */
  vision_r?: number;
  personas: Persona[];
  /** The t=0 seed social graph. */
  relationships?: RelationshipEdge[];
  /** LIVE meta only: the model driving the cast (never in a baked file). */
  llm?: LlmInfo | null;
  /** The world's real place names, sorted. Absent in replays baked before #780. */
  locations?: string[];

  // A live run's manifest is a superset of the bake's meta (#960): the #715
  // re-run provenance below rides along into an exported replay. All absent
  // in a baked file.
  /** The run's RNG seed. */
  seed?: number | null;
  /** Git SHA the server ran at; null outside a repo. */
  engine_sha?: string | null;
  /** Which SCENARIOS entry built the world (#747). */
  scenario?: string | null;
  /** Resolved cognition-tools value (post-coupling), not the CLI flag. */
  cognition_tools?: boolean | null;
  react?: boolean | null;
  /** The requested plan mode; planner_sources is the per-agent outcome. */
  plan_mode?: string | null;
  /** Per-persona plan provenance: {name: "llm" | "static" | "mock"} (#787). */
  planner_sources?: Record<string, string> | null;
  /** What each agent actually planned: {name: DailyPlan.to_primitive()} (#824). */
  daily_plans?: Record<string, Record<string, unknown>> | null;
  /** The launched step BUDGET — `steps` above is how many it actually took. */
  num_steps?: number | null;
  /** The #564 --config dump, key-carrying sections stripped. */
  sim_config?: Record<string, unknown> | null;
  /** The applied pre-run POST /config block (#732); only on configured runs. */
  config?: Record<string, unknown> | null;
}

/** One persona's state at a single step. Key order is pinned by
 * backend/contract.py AGENT_FRAME_FIELDS (byte-identity, #297).
 *
 * In a written FILE (schema 1.1, #941) the optional carry-forward fields
 * (reasoning/chat/memories/trace) may be absent when unchanged from the same
 * agent's previous frame; useReplay rehydrates them via replayCodec's
 * fattenFrames, so components always read full rows. */
export interface AgentFrame {
  /** Tile coordinates. */
  x: number;
  y: number;
  /** Activity description, e.g. "studying @ UPenn:Van Pelt Library:grounds". */
  act: string;
  /** Activity emoji ("pronunciatio"). */
  e: string;
  /** The reasoning behind this step's action (issue #163); templated under the
   * mock brain, genuine under a real LLM. */
  reasoning?: string | null;
  /** Current conversation as [speaker, line] pairs, or null when not talking. */
  chat?: [string, string][] | null;
  /** The memories retrieval surfaced for THIS decision (issue #163) -- a
   * subset of memory_streams; carries forward unchanged between decisions. */
  memories?: MemoryRecord[] | null;
  /** Per-decision cognition trace (#359): consults + terminal action, digests
   *  only. [] under the mock; the #163 card renders it. */
  trace?: Array<Record<string, unknown>> | null;
}

/** A step: persona name -> that persona's state. */
export type Frame = Record<string, AgentFrame>;

/** One entry in a persona's memory stream (issue #163). */
export interface MemoryRecord {
  /** "observation" | "plan" | "reflection" | "chat" -- the panel colour-codes it. */
  kind: string;
  /** Poignancy / importance (kept quiet beside the text). */
  importance: number;
  /** The memory text itself. */
  text: string;
  /** The step at which the memory formed. */
  created_turn: number;
}

/** One GameEvent log entry — the #467 run record (verbatim
 * GameEvent.to_primitive()). `payload` is event-specific structured detail. */
export interface EventState {
  turn: number;
  /** null for world-level stimuli with no single actor — ambient sound,
   * POST /world/event, the boil arc's `boiled` event (#631). */
  actor: string | null;
  action: string;
  summary: string;
  payload: Record<string, unknown>;
}

/** One ActionWish log entry — the #622 demand record (verbatim
 * ActionWish.to_primitive()). Recorded deliberately (the `propose` verb) or
 * automatically (a command that matched no verb at all, #621). */
export interface WishState {
  /** null if no actor resolved (mirrors EventState's null actor). */
  actor: string | null;
  turn: number;
  location: string | null;
  desired: string;
  /** The because-clause; "" for parse-gap wishes. */
  reason: string;
  /** "proposed" | "parse_gap". */
  trigger: string;
  /** Incomplete goals, described, at wish time. */
  goals: string[];
  /** Item/character names in scope at wish time. */
  scope: string[];
  raw_command: string;
  /** Extension point (#41 nouns, ...). */
  meta: Record<string, unknown>;
}

export interface Replay {
  meta: ReplayMeta;
  frames: Frame[];
  /** Per-persona full memory stream; the companion panel filters each agent's
   * records to created_turn <= step. Absent from very old replays. */
  memory_streams?: Record<string, MemoryRecord[]>;
  /** The GameEvent run record (#467). Absent from replays baked before it. */
  events?: EventState[];
  /** The ActionWish demand record (#622). Absent from replays baked before it. */
  wishes?: WishState[];
}
