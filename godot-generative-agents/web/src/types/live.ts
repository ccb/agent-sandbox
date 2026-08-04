// Types for the live backend's HTTP surface (backend/README.md "The feed: one
// log, two doors"): the GET /live handshake, the GET /events change feed
// (llm_call + frame + status records), and GET /agents/{name}/memory. The
// companion's agents view follows all of these when opened with ?api=; only
// the Godot canvas stays replay-driven — it plays the baked file.

import type { Frame, MemoryRecord, ReplayMeta } from "./replay";

// The per-LLM-request record the backend's terminal monitor keeps
// (backend/llm_monitor.py: a flattened CallRecord plus the monitor's extras),
// published as an `engine` feed record whose payload is stamped
// `kind: "llm_call"`. `turn` / `actor` / `latency_ms` may be null.
// Mirrored field-for-field against the emitter (CallRecord.to_primitive() +
// the monitor's extras) by test_replay_contract.py's live.ts mirror (#644).
export interface LlmCallRecord {
  kind: "llm_call";
  call_no: number;
  time: string; // wall clock "HH:MM:SS", stamped when the call returned
  role: string; // decide | converse | reflect | plan
  actor: string | null;
  turn: number | null;
  attempt: number | null; // retry index (CallRecord's replay seam)
  prompt_sha256: string | null; // hash of the messages (replay seam)
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
  cost_usd: number;
  cum_cost_usd: number;
  latency_ms: number | null;
  // A FAILED call (#745): the provider exception the adapter degraded to
  // None ("ExcClass: message"), or null for a call that answered. Failed
  // calls bill nothing but stay countable — a mid-run auth/quota/network
  // outage shows up here instead of freezing the cast silently.
  error: string | null;
  // Per-call tool metadata (#359): which tools were offered / chosen, the
  // choice mode, a truncated args digest, and the tool-loop round. All null
  // outside a tool-driven call.
  tool_offered: string[] | null;
  tool_chosen: string | null;
  tool_choice: string | null; // "auto" | "any" | "forced"
  args_digest: string | null;
  round: number | null;
}

// One retained record from GET /events. `kind` is the discriminator:
// - "frame": `step` + `agents` (persona name → AgentFrame, the live
//   counterpart of `replay.frames[step]`);
// - "status": the run-control state after a start/pause/resume/reset;
// - "engine": an engine event, payload in `event` (`llm_call` rows,
//   `game_event` rows — the #305 EventState shape — and `llm_error` rows,
//   #745's failed-call records, told apart by the payload's own `kind`);
// - "wish": an ActionWish demand record (#622), the WishState fields spread
//   at the top level beside `cursor`/`kind`;
// - "deciding": a per-agent decision-lifecycle marker (#551) — `agent`,
//   `state: "begin" | "end"`, `step`, and `elapsed_ms` on the end record.
export interface FeedRecord {
  cursor: number;
  kind: string;
  step?: number;
  agents?: Frame;
  reason?: string;
  running?: boolean;
  paused?: boolean;
  event?: { kind?: string } & Record<string, unknown>;
  // `deciding` records (#551): which agent, "begin" | "end", and (on end)
  // how long the decision took.
  agent?: string;
  state?: string;
  elapsed_ms?: number;
  // Run-scoped usage + social (#819): a `frame` record (and the `reset` status
  // record) carries the stepper's run_usage() so the run counters and the #795
  // social card ride the one feed — no separate /usage poll. A subset of
  // UsageSummary (the run_* fields + `social`); absent on steppers/records that
  // don't report it.
  run_usage?: Partial<UsageSummary>;
}

// The GET /events?since=N response envelope.
export interface EventsResponse {
  latest_cursor: number;
  oldest_cursor: number | null;
  events: FeedRecord[];
  // Per-process boot nonce (#578), the same one GET /live carries: lets the
  // poll fallback detect a restart whose new feed already climbed past our
  // cursor (no eviction gap, no rewind). Absent on a server predating the field.
  boot_id?: string | null;
}

// The live meta blob GET /live passes through: the replay-meta shape minus
// `steps` (a running sim doesn't know its length up front).
export type LiveMeta = Omit<ReplayMeta, "steps"> & { steps?: number };

// GET /live — the handshake a live client reads once before following the
// feed. With no live loop injected: `enabled: false, meta: null`.
export interface LiveStatusResponse {
  enabled: boolean;
  running: boolean;
  paused: boolean;
  step: number | null;
  cursor: number;
  tick_seconds: number | null;
  meta: LiveMeta | null;
  // Per-process boot nonce (#578): changes on a backend restart. Absent on an
  // older server that predates the field.
  boot_id?: string | null;
}

// This run's social opportunity (#795): co-settled pair-steps (both agents
// settled within earshot of each other), broken down by pair ("A + B" keys,
// busiest first), plus the conversation count. Zero co_settled_pair_steps with a
// nonzero step count means conversation was structurally impossible this
// run — surfaced instead of silently reporting nothing.
export interface RunSocial {
  co_settled_pair_steps: number;
  by_pair: Record<string, number>;
  conversations: number;
  // #819/#825: whether a zero above is meaningful. `counted` is false only
  // from a pre-#825 backend, where the mock brain never counted co-settling —
  // there its permanent 0 is "not measured", not a drought. Current backends
  // count under every brain and always send true. `resumed` is true when this process adopted a
  // mid-day run, restarting the accumulators at 0 — its 0 is "not fully
  // observed". Both mirror the backend's #795 finish-warning gate, so the card
  // can tell a real drought from those two non-signals. Optional: a backend
  // predating the fields omits them and the card falls back to soft wording.
  counted?: boolean;
  resumed?: boolean;
}

// GET /usage — the run ledger's summary (tokens and dollars, #264).
// `available: false` means no ledger is wired (a zeroed summary with only the
// core fields); the budget fields appear only when the server was started with
// a cost ceiling. Mirrored field-for-field against the wire (UsageLedger
// .summary() + the route's extras + the stepper's run_usage()) by
// test_replay_contract.py's live.ts mirror (#644).
export interface UsageSummary {
  kind: string;
  available: boolean;
  calls: number; // LIFETIME count — ticks with the mock brain's $0 records
  total_cost_usd: number; // lifetime, like `calls`
  by_actor: Record<string, number>;
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
  over_budget: boolean;
  max_cost_usd?: number;
  remaining_budget_usd?: number;
  // Ledger detail present whenever a ledger is wired (absent from the zeroed
  // `available: false` shape): per-role cost, failed calls (#745 — API errors
  // the adapters degraded to None), and tool-schema health (#357/#359).
  by_role?: Record<string, number>;
  failed_calls?: number;
  validation_failures?: number;
  repairs?: number;
  repair_successes?: number;
  by_tool?: Record<string, Record<string, number>>;
  tool_choice_split?: Record<string, number>;
  // Cache-minimum dead zone (#822): names each model whose median prompt is
  // too small to ever cache, or null on a healthy (or unjudgeable) run.
  cache_warning?: string | null;
  // The run-scoped slice (#526/#569, served since #601): REAL model calls only
  // — the mock brain's $0 pacing records don't inflate these — so the dashboard
  // headline agrees with its per-run call log. Present only when the stepper
  // reports per-run usage. `run_failed_calls` (#745) counts the run's FAILED
  // real calls: climbing while `run_cost_usd` stands still is the
  // mid-run-outage fingerprint.
  run_calls?: number;
  run_failed_calls?: number;
  run_cost_usd?: number;
  run_by_actor?: Record<string, number>;
  // Present only alongside the other run-scoped fields above.
  social?: RunSocial;
}

// GET /agents/{name}/memory — the live counterpart of the baked
// `memory_streams[name]`: same MemoryRecord entries, byte-identical (#298).
// `total` appears only when a since_turn/kind/limit selector was applied.
export interface MemoryStreamResponse {
  persona: string;
  turn: number;
  count: number;
  total?: number;
  memories: MemoryRecord[];
}
