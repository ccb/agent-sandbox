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
}

// One retained record from GET /events. `kind` is the discriminator:
// - "frame": `step` + `agents` (persona name → AgentFrame, the live
//   counterpart of `replay.frames[step]`);
// - "status": the run-control state after a start/pause/resume/reset;
// - "engine": an engine event, payload in `event` (llm_call rows and friends).
export interface FeedRecord {
  cursor: number;
  kind: string;
  step?: number;
  agents?: Frame;
  reason?: string;
  running?: boolean;
  paused?: boolean;
  event?: { kind?: string } & Record<string, unknown>;
}

// The GET /events?since=N response envelope.
export interface EventsResponse {
  latest_cursor: number;
  oldest_cursor: number | null;
  events: FeedRecord[];
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

// GET /usage — the run ledger's summary (tokens and dollars, #264).
// `available: false` means no ledger is wired (same shape, zeroed); the budget
// fields appear only when the server was started with a cost ceiling.
export interface UsageSummary {
  kind: string;
  available: boolean;
  calls: number;
  total_cost_usd: number;
  by_actor: Record<string, number>;
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
  over_budget: boolean;
  max_cost_usd?: number;
  remaining_budget_usd?: number;
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
