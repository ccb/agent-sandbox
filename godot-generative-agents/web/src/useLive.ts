import { useEffect, useRef, useState } from "react";
import type {
  EventsResponse,
  LiveMeta,
  LiveStatusResponse,
  LlmCallRecord,
  MemoryStreamResponse,
  UsageSummary,
} from "./types/live";
import type { Frame, MemoryRecord } from "./types/replay";

// Live mode is opt-in: the companion stays a static page until it's pointed at
// a running backend — by a `?api=http://127.0.0.1:8080` query param, a
// VITE_SIM_API_URL env var (a `pnpm dev` default), or the LLM dashboard's
// connect form at runtime (#519). This resolves the first two; App owns the
// resulting value as state so the form can supply one later. The backend's
// CORS already allows any localhost origin, so no proxy is needed.
export function initialApiBase(): string | null {
  const param = new URLSearchParams(window.location.search).get("api");
  const env = import.meta.env.VITE_SIM_API_URL as string | undefined;
  const base = param || env || null;
  return base ? base.replace(/\/+$/, "") : null;
}

const POLL_MS = 1000; // ~the loop's pace; a missed tick just arrives next poll
const MAX_ROWS_PER_AGENT = 200; // plenty for a day (~55-60 calls); keeps re-renders cheap

/** A stream record plus the client wall-clock ms it reached the page — the LLM
 * dashboard's recency signal (the wire record carries only a "HH:MM:SS" time). */
export type ReceivedLlmCall = LlmCallRecord & { receivedAt: number };

// Retention is capped per actor (actor: null is its own bucket), not globally,
// so one chatty agent can't evict everyone else's rows off the dashboard (#519).
// `cap` is a parameter (defaulting to the production value) only so the unit test
// can exercise the eviction with a small, readable bound — callers pass nothing.
export function capPerAgent(rows: ReceivedLlmCall[], cap = MAX_ROWS_PER_AGENT): ReceivedLlmCall[] {
  const seen = new Map<string | null, number>();
  const keep = new Array<boolean>(rows.length);
  for (let i = rows.length - 1; i >= 0; i--) {
    const n = seen.get(rows[i].actor) ?? 0;
    keep[i] = n < cap;
    seen.set(rows[i].actor, n + 1);
  }
  return keep.every(Boolean) ? rows : rows.filter((_, i) => keep[i]);
}

export interface LiveState {
  base: string | null; // the backend URL being followed (null = idle)
  enabled: boolean; // a backend target was given (?api=, env var, or the form)
  connected: boolean; // the last poll succeeded
  live: boolean; // the handshake reported a live loop (GET /live enabled: true)
  meta: LiveMeta | null; // the world's replay-meta shape, from the handshake
  usage: UsageSummary | null; // one GET /usage read at handshake (budget ceiling)
  running: boolean;
  paused: boolean;
  step: number; // latest completed sim step seen on the feed
  frame: Frame | null; // the latest frame record's agents (same shape as replay.frames[i])
  calls: ReceivedLlmCall[]; // oldest → newest, capped per agent
}

const IDLE: LiveState = {
  base: null,
  enabled: false,
  connected: false,
  live: false,
  meta: null,
  usage: null,
  running: false,
  paused: false,
  step: 0,
  frame: null,
  calls: [],
};

/**
 * Follow the live backend (#262/#398): one `GET /live` handshake for the
 * world's meta, then poll `GET /events` (the change feed's stateless catch-up
 * door — see backend/README.md) and keep three things:
 *
 * - `engine` records whose payload is `kind: "llm_call"` — the same rows the
 *   backend's terminal monitor prints and the Godot HUD's request log shows;
 * - the latest `frame` record (step + per-agent state, the live counterpart of
 *   `replay.frames[step]`);
 * - the latest `status` record (running / paused, from the run controls).
 *
 * Polling resumes from the last cursor seen, so each call row arrives exactly
 * once; the first poll (`since=0`) backfills whatever the capped log retains.
 *
 * `base` is the backend URL (App state, seeded by initialApiBase()); changing
 * it drops everything and follows the new target from scratch.
 */
export function useLive(base: string | null): LiveState {
  const [state, setState] = useState<LiveState>(IDLE);

  useEffect(() => {
    if (!base) return;
    setState({ ...IDLE, base, enabled: true });

    let cancelled = false;
    let timer = 0;
    let cursor = 0;
    let handshook = false; // GET /live done; retried until it succeeds

    const poll = async () => {
      try {
        if (!handshook) {
          const res = await fetch(`${base}/live`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const hs = (await res.json()) as LiveStatusResponse;
          // One /usage read alongside the handshake, for the dashboard's budget
          // line: max_cost_usd never changes, and every stream record carries
          // the running total (cum_cost_usd), so this needn't repeat.
          const usage = await fetch(`${base}/usage`)
            .then((r) => (r.ok ? (r.json() as Promise<UsageSummary>) : null))
            .catch(() => null);
          if (cancelled) return;
          handshook = true;
          setState((s) => ({
            ...s,
            enabled: true,
            connected: true,
            live: hs.enabled,
            meta: hs.meta,
            usage,
            running: hs.running,
            paused: hs.paused,
            step: hs.step ?? 0,
          }));
        }
        const res = await fetch(`${base}/events?since=${cursor}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as EventsResponse;
        if (cancelled) return;
        // The feed's eviction-gap signal (backend/README.md): the oldest record
        // returned skipping past our cursor means the capped log evicted rows
        // between polls. They're gone for good — re-handshake next poll so at
        // least meta/step/usage resync (also how a server restart re-anchors).
        if (cursor > 0 && data.events.length && data.events[0].cursor > cursor + 1) {
          handshook = false;
        }
        cursor = Math.max(cursor, data.latest_cursor);
        const receivedAt = Date.now();
        // Walk the batch in feed order: a status record with reason "reset"
        // (the documented new-run signal) drops every call before it — the
        // retained log and this batch's earlier rows describe the dead run.
        let wasReset = false;
        const fresh: ReceivedLlmCall[] = [];
        for (const r of data.events) {
          if (r.kind === "status" && r.reason === "reset") {
            wasReset = true;
            fresh.length = 0;
          } else if (r.kind === "engine" && r.event?.kind === "llm_call") {
            fresh.push({ ...(r.event as unknown as LlmCallRecord), receivedAt });
          }
        }
        // Only the newest frame/status matter — the panel shows "now", not history.
        const frames = data.events.filter((r) => r.kind === "frame");
        const lastFrame = frames[frames.length - 1];
        const statuses = data.events.filter((r) => r.kind === "status");
        const lastStatus = statuses[statuses.length - 1];
        // Skip the state update when nothing changed, so an idle (or paused)
        // backend doesn't re-render the panel once a second.
        setState((s) =>
          s.connected && fresh.length === 0 && !lastFrame && !lastStatus
            ? s
            : {
                ...s,
                connected: true,
                calls: wasReset
                  ? fresh
                  : fresh.length
                    ? capPerAgent([...s.calls, ...fresh])
                    : s.calls,
                frame: lastFrame?.agents ?? s.frame,
                step: lastFrame?.step ?? lastStatus?.step ?? s.step,
                running: lastStatus?.running ?? s.running,
                paused: lastStatus?.paused ?? s.paused,
              },
        );
      } catch {
        if (cancelled) return;
        setState((s) => (s.connected ? { ...s, connected: false } : s));
      }
      if (!cancelled) timer = window.setTimeout(poll, POLL_MS);
    };
    void poll();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [base]);

  return state;
}

const NO_MEMORIES: MemoryRecord[] = [];

/**
 * The selected persona's live memory stream (`GET /agents/{name}/memory`,
 * #298): read when the persona changes or the live step advances (i.e. at the
 * feed poll's ~1s cadence). Entries are byte-identical to the baked
 * `memory_streams[name]`, so MemoryRows renders them unchanged. Returns []
 * while inactive, and while a just-switched persona's fetch is in flight (so
 * one agent's memories never show under another's name).
 *
 * Reads are incremental (#345, per the #520 review): after the first full
 * fetch, only `?since_turn=<last snapshot turn - 1>` is asked for. The -1 is
 * because entries can still land at the snapshot turn after we read it, so the
 * boundary turn is re-read (the selector is strict `created_turn >`) and any
 * overlap deduped. A snapshot turn moving backwards means the run was reset —
 * start over with a full fetch.
 */
export function useLiveMemories(
  active: boolean,
  persona: string,
  step: number,
  base: string | null,
): MemoryRecord[] {
  const [got, setGot] = useState<{ persona: string; memories: MemoryRecord[] }>({
    persona: "",
    memories: NO_MEMORIES,
  });
  // The incremental cursor lives in a ref so the effect below never re-runs
  // (or closes over stale state) because of its own appends.
  const acc = useRef({ persona: "", upTo: -1, memories: NO_MEMORIES });

  useEffect(() => {
    if (!active || !base || !persona) return;
    let cancelled = false;
    (async () => {
      try {
        const read = async (since: number | null): Promise<MemoryStreamResponse> => {
          const q = since === null ? "" : `?since_turn=${since}`;
          const res = await fetch(`${base}/agents/${encodeURIComponent(persona)}/memory${q}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return (await res.json()) as MemoryStreamResponse;
        };
        let held = acc.current.persona === persona ? acc.current : null;
        let data = await read(held ? held.upTo : null);
        if (held && data.turn <= held.upTo) {
          // The run was reset under us — the held list describes a dead run.
          held = null;
          data = await read(null);
        }
        if (cancelled) return;
        const seen = new Set(
          (held?.memories ?? []).map((m) => `${m.created_turn}|${m.kind}|${m.text}`),
        );
        const fresh = data.memories.filter(
          (m) => !seen.has(`${m.created_turn}|${m.kind}|${m.text}`),
        );
        if (held && !fresh.length) return; // nothing new — skip the re-render
        const memories = [...(held?.memories ?? []), ...fresh];
        acc.current = { persona, upTo: data.turn - 1, memories };
        setGot({ persona, memories });
      } catch {
        // Keep the last good list; the feed poll's `connected` flag reports outages.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [active, persona, step, base]);

  return got.persona === persona ? got.memories : NO_MEMORIES;
}
