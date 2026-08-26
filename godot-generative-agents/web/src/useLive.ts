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
import type { EventState, Frame, MemoryRecord, WishState } from "./types/replay";

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
const MAX_EVENT_ROWS = 200; // world-level rows are rarer than calls; one shared cap
// Wishes also keep their own retention (#873): they ride the shared events feed
// for the interleaved EventFeed panel, but a busy day's game_events would evict
// early wishes out of that 200-row cap — and WishFeed presents itself as the
// run's whole demand log, so its count must never shrink. Wishes are rare
// (~10 on a busy live day), so a small cap outlasts any healthy run.
const MAX_WISH_ROWS = 30;

/** A stream record plus the client wall-clock ms it reached the page — the LLM
 * dashboard's recency signal (the wire record carries only a "HH:MM:SS" time). */
export type ReceivedLlmCall = LlmCallRecord & { receivedAt: number };

/** One run-event row kept for the feed panel (#644): a `game_event` payload
 * (the #305 EventState shape, off an `engine` record) or a top-level `wish`
 * record (#622). `cursor` is the feed cursor — a stable render key — and
 * `receivedAt` mirrors ReceivedLlmCall's recency stamp. */
export type ReceivedFeedEvent = { cursor: number; receivedAt: number } & (
  | ({ kind: "game_event" } & EventState)
  | ({ kind: "wish" } & WishState)
);

/** A wish row alone (#873): WishFeed's dedicated retention, so game_event
 * eviction in the shared feed can't shrink the run's demand log. */
export type ReceivedWish = { cursor: number; receivedAt: number; kind: "wish" } & WishState;

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
  usage: UsageSummary | null; // GET /usage seeds it; run counters + social ride the feed (#819)
  running: boolean;
  paused: boolean;
  step: number; // latest completed sim step seen on the feed
  frame: Frame | null; // the latest frame record's agents (same shape as replay.frames[i])
  calls: ReceivedLlmCall[]; // oldest → newest, capped per agent
  events: ReceivedFeedEvent[]; // game_event + wish rows, oldest → newest, capped
  wishes: ReceivedWish[]; // the wish rows again, own cap (#873) — event eviction can't touch them
  // Agents mid-decision right now (#525): name → the wall-clock ms their
  // `deciding: begin` record arrived, deleted again on the matching `end`
  // (#551's lifecycle). Cleared on reset/restart, mirroring the Godot
  // viewer's DecidingState.clear(), so a dropped `end` can't wedge a bubble.
  deciding: Record<string, number>;
  // When the newest frame reached the page (the handshake seeds it) — the
  // stall clock behind the #372-style global "thinking" inference.
  lastFrameAt: number | null;
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
  events: [],
  wishes: [],
  deciding: {},
  lastFrameAt: null,
};

/**
 * Fold a batch of change-feed records into the live state — the one reducer
 * both feed doors share (the WS push path and the poll fallback), so reset
 * clearing and frame/status tracking can't drift between them:
 *
 * - `engine` records whose payload is `kind: "llm_call"` — the same rows the
 *   backend's terminal monitor prints and the Godot HUD's request log shows;
 * - `engine` records whose payload is `kind: "game_event"` plus top-level
 *   `wish` records (#644) — the run-event rows the Godot HUD log shows, so the
 *   two instruments agree about what happened;
 * - `deciding` begin/end records (#551 → #525): the per-agent "thinking"
 *   lifecycle. Folded in batch order, so a decide that begins AND ends inside
 *   one tick (today's within-tick pairs, #605) nets out to no bubble — no
 *   flicker at mock speeds — while a tick-spanning decide leaves its agent lit;
 * - the latest `frame` record (step + per-agent state, the live counterpart of
 *   `replay.frames[step]`);
 * - the latest `status` record (running / paused, from the run controls);
 * - the run-scoped usage + social block (#819), which rides the `frame` record
 *   (and the `reset` status record) as `run_usage`: merged over the handshake's
 *   `/usage` snapshot so the run counters and the #795 social card refresh off
 *   this one feed — no separate poll to drift out of lifecycle sync (a reset
 *   clears them for free, the same walk that drops the dead run's rows).
 */
export function applyFeedRecords(
  s: LiveState,
  records: FeedRecord[],
  receivedAt: number,
): LiveState {
  // Walk the batch in feed order: a status record with reason "reset"
  // (the documented new-run signal) drops every call/event/bubble before it —
  // the retained log and this batch's earlier rows describe the dead run.
  let wasReset = false;
  const fresh: ReceivedLlmCall[] = [];
  const freshEvents: ReceivedFeedEvent[] = [];
  const freshWishes: ReceivedWish[] = [];
  let deciding: Record<string, number> | null = null; // null = untouched this batch
  for (const r of records) {
    if (r.kind === "status" && r.reason === "reset") {
      wasReset = true;
      fresh.length = 0;
      freshEvents.length = 0;
      freshWishes.length = 0;
      deciding = {};
    } else if (r.kind === "engine" && r.event?.kind === "llm_call") {
      fresh.push({ ...(r.event as unknown as LlmCallRecord), receivedAt });
    } else if (r.kind === "engine" && r.event?.kind === "game_event") {
      freshEvents.push({
        ...(r.event as unknown as EventState),
        kind: "game_event",
        cursor: r.cursor,
        receivedAt,
      });
    } else if (r.kind === "wish") {
      // A wish rides its own top-level kind — its WishState fields sit beside
      // cursor/kind on the record itself, not inside an `event` payload. It
      // lands in both logs: `events` for the interleaved feed, `wishes` for
      // the demand log with its own retention (#873).
      const row: ReceivedWish = {
        ...(r as unknown as WishState),
        kind: "wish",
        cursor: r.cursor,
        receivedAt,
      };
      freshEvents.push(row);
      freshWishes.push(row);
    } else if (r.kind === "deciding" && typeof r.agent === "string") {
      deciding = deciding ?? { ...s.deciding };
      if (r.state === "begin") deciding[r.agent] = receivedAt;
      else delete deciding[r.agent]; // "end" — an orphan end is a no-op
    }
  }
  // Only the newest frame/status matter — the panel shows "now", not history.
  const frames = records.filter((r) => r.kind === "frame");
  const lastFrame = frames[frames.length - 1];
  const statuses = records.filter((r) => r.kind === "status");
  const lastStatus = statuses[statuses.length - 1];
  // Run-scoped usage + social (#819): the newest frame carries it every tick,
  // and a `reset` status carries a freshly-zeroed one so the counters drop the
  // instant the reset lands (not a tick later). Merged over the handshake's
  // /usage snapshot below, so the lifetime totals + budget it seeded survive.
  const runUsage = lastFrame?.run_usage ?? lastStatus?.run_usage;
  // Skip the state update when nothing changed, so an idle (or paused)
  // backend doesn't re-render the panel once a second.
  if (
    s.connected &&
    fresh.length === 0 &&
    freshEvents.length === 0 &&
    deciding === null &&
    !lastFrame &&
    !lastStatus
  )
    return s;
  const heldEvents = wasReset ? [] : s.events;
  const heldWishes = wasReset ? [] : s.wishes;
  return {
    ...s,
    connected: true,
    calls: wasReset ? fresh : fresh.length ? capPerAgent([...s.calls, ...fresh]) : s.calls,
    events: freshEvents.length
      ? [...heldEvents, ...freshEvents].slice(-MAX_EVENT_ROWS)
      : heldEvents,
    wishes: freshWishes.length ? [...heldWishes, ...freshWishes].slice(-MAX_WISH_ROWS) : heldWishes,
    deciding: deciding ?? s.deciding,
    lastFrameAt: lastFrame ? receivedAt : s.lastFrameAt,
    // frame is deliberately NOT dropped on reset: calls/events are append-only
    // logs (stale rows would linger beside new ones), but frame is wholesale-
    // replaced by the new run's first frame within one tick — keeping the
    // last-known agents until then beats flashing an empty campus.
    frame: lastFrame?.agents ?? s.frame,
    step: lastFrame?.step ?? lastStatus?.step ?? s.step,
    running: lastStatus?.running ?? s.running,
    paused: lastStatus?.paused ?? s.paused,
    // Merge the run-scoped subset over the handshake snapshot (keeping the
    // lifetime totals + budget); if none rode this batch, leave usage as-is.
    usage: runUsage && s.usage ? { ...s.usage, ...runUsage } : s.usage,
  };
}

// How long the feed head may sit still on a RUNNING backend before the global
// indicator infers "thinking" (#372's heuristic, web edition). The Godot
// viewer uses 1500 ms against its pushed frame stream; the web's poll
// fallback quantizes arrivals at POLL_MS, so the threshold covers a full
// missed poll on top of a tick (2 × POLL_MS + margin) — otherwise a healthy
// 0.6 s-tick mock run would strobe the badge once per poll beat.
export const THINKING_STALL_MS = 2500;

/**
 * The global "thinking" cue (#525), mirroring the Godot viewer's #598
 * semantics: the explicit per-agent `deciding` signal OR the #372 stall
 * heuristic. The OR keeps the heuristic live for decides that begin AND end
 * within one tick (their begin/end fold to nothing in `applyFeedRecords` —
 * the #605 boundary), while `deciding` adds the cases that DO span ticks
 * (a parked #366 straggler) even though frames keep flowing.
 *
 * Gated on connected: a dead poll renders the existing "reconnecting" badge —
 * thinking must stay visually distinct from disconnected. Mock runs without
 * `deciding` records fall back to pure stall inference, exactly like the
 * Godot badge.
 */
export function isThinking(s: LiveState, now: number, stallMs = THINKING_STALL_MS): boolean {
  if (!s.connected || !s.live) return false;
  if (Object.keys(s.deciding).length > 0) return true;
  return s.running && !s.paused && s.lastFrameAt !== null && now - s.lastFrameAt > stallMs;
}

/**
 * React seam over isThinking(): re-evaluated when the live state changes AND
 * on a 1 s clock (the stall half needs wall time to pass with no state change
 * to trigger it). Edge-triggered — setState with an unchanged boolean is a
 * React no-op — so the page re-renders only when the cue actually flips,
 * never once a second.
 */
export function useThinking(live: LiveState): boolean {
  const [thinking, setThinking] = useState(false);
  useEffect(() => {
    const update = () => setThinking(isThinking(live, Date.now()));
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, [live]);
  return thinking;
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
 * handshake so at least meta/step/usage resync. A backend *restart* is the
 * opposite signal — the feed cursor is in-memory and starts over with the new
 * process — so a handshake reporting a cursor *below* ours re-anchors there
 * and drops the dead run's call log, like a reset (#549).
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
  let bootId: string | null = null; // last-seen GET /live boot nonce (#578)
  let handshook = false; // GET /live done; retried until it succeeds
  let wsUsable = true; // cleared when a socket dies before opening

  const handshake = async () => {
    // Capture at fire time, not after the awaits below: the background
    // eviction-gap refresh runs with a socket up (`handshook` true), but a drop
    // during these fetches flips it false via `onclose` — reading it late would
    // mistake that refresh for a fresh reconnect and rewind a healthy follower.
    const wasHandshook = handshook;
    const res = await fetch(`${base}/live`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const hs = (await res.json()) as LiveStatusResponse;
    // One /usage read alongside the handshake seeds the budget line + lifetime
    // totals; the run-scoped counters and the #795 social block ride the feed's
    // `run_usage` from then on (#819). Degrades to null on any non-ok/error —
    // written below as `usage ?? s.usage` so a transient failure on a reconnect
    // keeps the last good snapshot instead of blanking the strip + card.
    const usage = await fetch(`${base}/usage`)
      .then((r) => (r.ok ? (r.json() as Promise<UsageSummary>) : null))
      .catch(() => null);
    if (cancelled) return;
    // A handshake cursor below ours can only mean the backend restarted —
    // within one server lifetime the cursor only climbs, even across resets
    // (#549). Re-anchor at the new head and clear the call log like a reset:
    // the retained rows describe a dead run. Fresh connects/reconnects only —
    // the background eviction-gap refresh races records still arriving on the
    // open socket, and must never rewind a healthy follower.
    const rewound = !wasHandshook && hs.cursor < cursor;
    // #578: a changed per-process boot nonce is the reliable restart signal —
    // it catches a new process whose feed has already climbed past our cursor,
    // which `rewound` misses. A first handshake (bootId null) or a server that
    // omits boot_id (older/mixed-version) falls back to the cursor rewind. Fresh
    // connects/reconnects only, like `rewound` — never the background refresh.
    const rebooted =
      !wasHandshook && bootId !== null && hs.boot_id != null && hs.boot_id !== bootId;
    // Record the nonce on a fresh connect/reconnect only, never on the background
    // eviction-gap refresh: a restart mid-refresh must leave `bootId` at the old
    // value so the next reconnect's comparison still catches it (#578 review).
    // The first handshake has `wasHandshook === false`, so it still records.
    if (!wasHandshook && hs.boot_id != null) bootId = hs.boot_id;
    const restarted = rewound || rebooted;
    if (restarted) cursor = hs.cursor;
    handshook = true;
    setState((s) => ({
      ...s,
      enabled: true,
      connected: true,
      live: hs.enabled,
      meta: hs.meta,
      usage: usage ?? s.usage,
      running: hs.running,
      paused: hs.paused,
      step: hs.step ?? 0,
      // The same "dead run's rows are gone" clearing as applyFeedRecords' reset
      // path — kept here (not routed through the reducer) because this applies a
      // /live *snapshot*, not a feed record: the reducer folds records, and a
      // synthetic one would have to carry the whole meta/usage/step snapshot too.
      calls: restarted ? [] : s.calls,
      events: restarted ? [] : s.events,
      wishes: restarted ? [] : s.wishes,
      // A restarted backend's in-flight decisions died with it — clear the
      // bubbles like the Godot viewer's DecidingState.clear() on #549 restart,
      // so a dropped `end` can't wedge one across runs.
      deciding: restarted ? {} : s.deciding,
      // Seed (or re-seed) the stall clock: "quiet since attach" is the stall
      // that matters when we join a run already mid-decision. A background
      // eviction-gap refresh keeps the genuine last-frame time.
      lastFrameAt: restarted || s.lastFrameAt === null ? Date.now() : s.lastFrameAt,
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
      if (data.latest_cursor < cursor) {
        handshook = false; // cursor rewind: a restart — the re-handshake re-anchors (#549)
      }
      if (data.boot_id != null && bootId !== null && data.boot_id !== bootId) {
        // A changed nonce is the restart signal the gap/rewind checks miss when
        // the new process's feed has already climbed past our cursor (#578): the
        // re-handshake next tick re-anchors + clears via the `rebooted` path.
        handshook = false;
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
