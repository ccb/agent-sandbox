// Types for the live backend's change feed (backend/README.md "The feed: one
// log, two doors"). The companion only unpacks the LLM-request stream (#398);
// frames and statuses exist on the wire but the Godot canvas doesn't need them
// here — it plays the baked replay.

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

// One retained record from GET /events. `kind` is the discriminator; only
// `engine` records carry an `event` payload.
export interface FeedRecord {
  cursor: number;
  kind: string;
  step?: number;
  event?: { kind?: string } & Record<string, unknown>;
}

// The GET /events?since=N response envelope.
export interface EventsResponse {
  latest_cursor: number;
  oldest_cursor: number | null;
  events: FeedRecord[];
}
