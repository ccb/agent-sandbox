import { useEffect, useRef, useState } from "react";
import type {
  EventsResponse,
  FeedRecord,
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
 * Fold a batch of change-feed records into the live state — the one reducer
 * both feed doors share (the WS push path and the poll fallback), so reset
 * clearing and frame/status tracking can't drift between them:
 *
 * - `engine` records whose payload is `kind: "llm_call"` — the same rows the
 *   backend's terminal monitor prints and the Godot HUD's request log shows;
 * - the latest `frame` record (step + per-agent state, the live counterpart of
 *   `replay.frames[step]`);
 * - the latest `status` record (running / paused, from the run controls).
 */
export function applyFeedRecords(
  s: LiveState,
  records: FeedRecord[],
  receivedAt: number,
): LiveState {
  // Walk the batch in feed order: a status record with reason "reset"
  // (the documented new-run signal) drops every call before it — the
  // retained log and this batch's earlier rows describe the dead run.
  let wasReset = false;
  const fresh: ReceivedLlmCall[] = [];
  for (const r of records) {
    if (r.kind === "status" && r.reason === "reset") {
      wasReset = true;
      fresh.length = 0;
    } else if (r.kind === "engine" && r.event?.kind === "llm_call") {
      fresh.push({ ...(r.event as unknown as LlmCallRecord), receivedAt });
    }
  }
  // Only the newest frame/status matter — the panel shows "now", not history.
  const frames = records.filter((r) => r.kind === "frame");
  const lastFrame = frames[frames.length - 1];
  const statuses = records.filter((r) => r.kind === "status");
  const lastStatus = statuses[statuses.length - 1];
  // Skip the state update when nothing changed, so an idle (or paused)
  // backend doesn't re-render the panel once a second.
  if (s.connected && fresh.length === 0 && !lastFrame && !lastStatus) return s;
  return {
    ...s,
    connected: true,
    calls: wasReset ? fresh : fresh.length ? capPerAgent([...s.calls, ...fresh]) : s.calls,
    frame: lastFrame?.agents ?? s.frame,
    step: lastFrame?.step ?? lastStatus?.step ?? s.step,
    running: lastStatus?.running ?? s.running,
    paused: lastStatus?.paused ?? s.paused,
  };
}

/**
 * Follow one backend (#524): a `GET /live` handshake for the world's meta,
 * then the change feed — over `WS /ws` when the socket can be established,
 * else by polling `GET /events` once a second (the feed's two doors serve the
 * same records under the same cursor; see backend/README.md).
 *
 * The socket is tried once per target, after the first successful handshake
 * (so "backend down" retries the handshake rather than condemning WS): if it
 * never reaches open — a proxy that blocks Upgrade, a pre-#379 backend — the
 * poll takes over for good. A socket that opened and then dropped (including
 * the server's 1008/1009/1011 closes, per the live-seam tests) reconnects
 * with a fresh handshake and `?since=<last cursor>`, so no record is missed.
 *
 * Either way the feed resumes from the last cursor seen, so each call row
 * arrives exactly once; the first attach (`since=0`) backfills whatever the
 * capped log retains. A cursor gap at the head of a batch is the eviction
 * signal (backend/README.md): the skipped rows are gone for good — re-run the
 * handshake so at least meta/step/usage resync (also how a server restart
 * re-anchors).
 *
 * Exported (and React-free) so the test can drive it with fake fetch/WS/timers;
 * components use the `useLive` hook below. Returns a stop function.
 */
export function followLive(
  base: string,
  setState: (update: (s: LiveState) => LiveState) => void,
): () => void {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let ws: WebSocket | null = null;
  let cursor = 0;
  let handshook = false; // GET /live done; retried until it succeeds
  let wsUsable = true; // cleared when a socket dies before opening

  const handshake = async () => {
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
  };

  const poll = async () => {
    try {
      if (!handshook) await handshake();
      if (cancelled) return;
      const res = await fetch(`${base}/events?since=${cursor}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as EventsResponse;
      if (cancelled) return;
      if (cursor > 0 && data.events.length && data.events[0].cursor > cursor + 1) {
        handshook = false; // eviction gap — re-handshake next poll
      }
      cursor = Math.max(cursor, data.latest_cursor);
      setState((s) => applyFeedRecords(s, data.events, Date.now()));
    } catch {
      if (cancelled) return;
      setState((s) => (s.connected ? { ...s, connected: false } : s));
    }
    if (!cancelled) timer = setTimeout(poll, POLL_MS);
  };

  const openSocket = () => {
    // A browser WebSocket can't set headers, so no Authorization here — like
    // the poll, this rides the backend's loopback-unauthenticated default.
    let sock: WebSocket;
    try {
      sock = new WebSocket(`${base.replace(/^http/, "ws")}/ws?since=${cursor}`);
    } catch {
      // new WebSocket() throws synchronously on a malformed URL (fetch merely
      // rejects, so /live may have worked) — treat it like a blocked socket.
      wsUsable = false;
      void poll();
      return;
    }
    ws = sock;
    let opened = false;
    let firstRecord = cursor > 0; // an explicit ?since= makes the first gap ours to judge
    // Records are pushed one per message; a same-burst batch (a tick's frame +
    // its llm_calls, or the ?since= backfill) folds into one state update.
    let pending: FeedRecord[] = [];
    let flushTimer: ReturnType<typeof setTimeout> | undefined;
    const flush = () => {
      flushTimer = undefined;
      if (cancelled || !pending.length) return;
      const batch = pending;
      pending = [];
      setState((s) => applyFeedRecords(s, batch, Date.now()));
    };
    sock.onopen = () => {
      opened = true;
    };
    sock.onmessage = (ev) => {
      if (cancelled || ws !== sock) return;
      const record = JSON.parse(ev.data as string) as FeedRecord;
      if (firstRecord) {
        firstRecord = false;
        // Same eviction-gap contract as the poll (the server only 1011s gaps
        // *after* the ?since= replay): the rows are gone — refresh the
        // handshake in the background, the socket itself is still good.
        if (record.cursor > cursor + 1) handshake().catch(() => undefined);
      }
      cursor = Math.max(cursor, record.cursor);
      pending.push(record);
      if (flushTimer === undefined) flushTimer = setTimeout(flush, 0);
    };
    sock.onclose = () => {
      if (cancelled || ws !== sock) return;
      ws = null;
      flush();
      if (!opened) {
        // Never reached open (handshake had just succeeded, so the backend is
        // up): WS is blocked or unsupported — the poll takes over for good.
        wsUsable = false;
        void poll();
        return;
      }
      // Opened, then dropped — a plain disconnect or one of the server's
      // policed closes (1008 bad token / 1009 oversized / 1011 evicted): all
      // reconnect through a fresh handshake, resuming at the kept cursor.
      handshook = false;
      setState((s) => (s.connected ? { ...s, connected: false } : s));
      timer = setTimeout(connect, POLL_MS);
    };
  };

  const connect = async () => {
    if (!wsUsable) {
      void poll();
      return;
    }
    try {
      if (!handshook) await handshake();
    } catch {
      if (cancelled) return;
      setState((s) => (s.connected ? { ...s, connected: false } : s));
      timer = setTimeout(connect, POLL_MS);
      return;
    }
    if (!cancelled) openSocket();
  };
  void connect();

  return () => {
    cancelled = true;
    clearTimeout(timer);
    ws?.close();
  };
}

/**
 * The React seam over followLive(): `base` is the backend URL (App state,
 * seeded by initialApiBase()); changing it drops everything and follows the
 * new target from scratch.
 */
export function useLive(base: string | null): LiveState {
  const [state, setState] = useState<LiveState>(IDLE);

  useEffect(() => {
    if (!base) return;
    setState({ ...IDLE, base, enabled: true });
    return followLive(base, setState);
  }, [base]);

  return state;
}

const NO_MEMORIES: MemoryRecord[] = [];

/**
 * The selected persona's live memory stream (`GET /agents/{name}/memory`,
 * #298): read when the persona changes or the live step advances (i.e. at the
 * feed's tick cadence). Entries are byte-identical to the baked
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
