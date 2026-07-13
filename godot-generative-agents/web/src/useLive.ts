import { useEffect, useState } from "react";
import type {
  EventsResponse,
  LiveStatusResponse,
  LiveMeta,
  LlmCallRecord,
  MemoryStreamResponse,
  UsageSummary,
} from "./types/live";
import type { Frame, MemoryRecord } from "./types/replay";

// Live mode is opt-in: the companion stays a static page unless you point it at
// a running backend with `?api=http://127.0.0.1:8080` (or a VITE_SIM_API_URL
// env var for `pnpm dev`). The backend's CORS already allows any localhost
// origin, so the Vite dev server can poll it directly — no proxy needed.
function apiBase(): string | null {
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
function capPerAgent(rows: ReceivedLlmCall[]): ReceivedLlmCall[] {
  const seen = new Map<string | null, number>();
  const keep = new Array<boolean>(rows.length);
  for (let i = rows.length - 1; i >= 0; i--) {
    const n = seen.get(rows[i].actor) ?? 0;
    keep[i] = n < MAX_ROWS_PER_AGENT;
    seen.set(rows[i].actor, n + 1);
  }
  return keep.every(Boolean) ? rows : rows.filter((_, i) => keep[i]);
}

export interface LiveState {
  enabled: boolean; // an ?api= target was given
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
 */
export function useLive(): LiveState {
  const [state, setState] = useState<LiveState>(IDLE);

  useEffect(() => {
    const base = apiBase();
    if (!base) return;
    setState((s) => ({ ...s, enabled: true }));

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
        cursor = Math.max(cursor, data.latest_cursor);
        const receivedAt = Date.now();
        const fresh = data.events
          .filter((r) => r.kind === "engine" && r.event?.kind === "llm_call")
          .map((r) => ({ ...(r.event as unknown as LlmCallRecord), receivedAt }));
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
                calls: fresh.length ? capPerAgent([...s.calls, ...fresh]) : s.calls,
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
  }, []);

  return state;
}

const NO_MEMORIES: MemoryRecord[] = [];

/**
 * The selected persona's live memory stream (`GET /agents/{name}/memory`,
 * #298): refetched when the persona changes or the live step advances (i.e. at
 * the feed poll's ~1s cadence). Entries are byte-identical to the baked
 * `memory_streams[name]`, so MemoryRows renders them unchanged. Returns []
 * while inactive, and while a just-switched persona's fetch is in flight (so
 * one agent's memories never show under another's name).
 */
export function useLiveMemories(
  active: boolean,
  persona: string,
  step: number,
): MemoryRecord[] {
  const [got, setGot] = useState<{ persona: string; memories: MemoryRecord[] }>({
    persona: "",
    memories: NO_MEMORIES,
  });

  useEffect(() => {
    const base = apiBase();
    if (!active || !base || !persona) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${base}/agents/${encodeURIComponent(persona)}/memory`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as MemoryStreamResponse;
        if (!cancelled) setGot({ persona, memories: data.memories });
      } catch {
        // Keep the last good list; the feed poll's `connected` flag reports outages.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [active, persona, step]);

  return got.persona === persona ? got.memories : NO_MEMORIES;
}
