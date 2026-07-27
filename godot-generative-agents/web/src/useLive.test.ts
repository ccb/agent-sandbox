import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FeedRecord } from "./types/live";
import {
  applyFeedRecords,
  capPerAgent,
  followLive,
  isThinking,
  type LiveState,
  type ReceivedLlmCall,
  THINKING_STALL_MS,
} from "./useLive";

// capPerAgent only inspects `.actor`; `call_no` tags each row so we can assert
// which survived. Build minimal records — the full LlmCallRecord shape is noise
// for this logic.
function row(actor: string | null, call_no: number): ReceivedLlmCall {
  return { actor, call_no } as unknown as ReceivedLlmCall;
}
const ids = (rows: ReceivedLlmCall[]) => rows.map((r) => r.call_no);

describe("capPerAgent", () => {
  it("caps each actor independently, so a chatty agent can't evict a quiet one", () => {
    // "a" is over the cap of 2; "b"'s single row must survive regardless (#519).
    const kept = capPerAgent([row("a", 1), row("a", 2), row("b", 3), row("a", 4)], 2);
    // "a" keeps its two newest (2, 4) and drops the oldest (1); "b" is untouched.
    expect(ids(kept)).toEqual([2, 3, 4]);
  });

  it("gives the null actor (a call with no character) its own bucket", () => {
    const kept = capPerAgent([row(null, 1), row("a", 2), row(null, 3), row(null, 4)], 2);
    expect(ids(kept)).toEqual([2, 3, 4]);
  });

  it("preserves oldest→newest order among the survivors", () => {
    expect(ids(capPerAgent([row("a", 10), row("a", 20), row("a", 30)], 2))).toEqual([20, 30]);
  });

  it("returns the same array reference when nothing is over the cap (skips a re-render)", () => {
    const rows = [row("a", 1), row("b", 2)];
    expect(capPerAgent(rows, 5)).toBe(rows);
  });
});

// ---------------------------------------------------------------------------
// The shared feed reducer and the WS-first driver (#524). The driver is
// React-free by design so these tests can run it against a fake fetch, a fake
// WebSocket class, and vitest's fake timers — no DOM environment needed.
// ---------------------------------------------------------------------------

const idle = (): LiveState => ({
  base: "http://b",
  enabled: true,
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
  deciding: {},
  lastFrameAt: null,
});

const call = (call_no: number, cursor: number): FeedRecord => ({
  cursor,
  kind: "engine",
  event: { kind: "llm_call", actor: "a", call_no },
});

// A game_event engine record (#467) and a top-level wish record (#622), in
// their wire shapes — the rows #644 makes visible in the web feed.
const gameEvent = (cursor: number, summary: string): FeedRecord => ({
  cursor,
  kind: "engine",
  step: 1,
  event: { kind: "game_event", turn: 3, actor: "Maya", action: "drink", summary, payload: {} },
});

const wish = (cursor: number, desired: string): FeedRecord =>
  ({
    cursor,
    kind: "wish",
    actor: "Maya",
    turn: 4,
    location: null,
    desired,
    reason: "mine keeps getting stolen",
    trigger: "proposed",
    goals: [],
    scope: [],
    raw_command: "",
    meta: {},
  }) as unknown as FeedRecord;

describe("applyFeedRecords", () => {
  it("keeps llm_call rows and tracks the newest frame/status", () => {
    const s = applyFeedRecords(
      idle(),
      [
        call(1, 1),
        { cursor: 2, kind: "frame", step: 7, agents: {} },
        {
          cursor: 3,
          kind: "status",
          reason: "paused",
          running: true,
          paused: true,
          step: 7,
        },
      ],
      123,
    );
    expect(s.calls.map((c) => c.call_no)).toEqual([1]);
    expect(s.calls[0].receivedAt).toBe(123);
    expect(s.step).toBe(7);
    expect(s.paused).toBe(true);
    expect(s.connected).toBe(true);
  });

  it("a reset status drops the retained log and the batch's earlier rows", () => {
    const held = { ...idle(), connected: true, calls: [row("a", 1)] };
    const s = applyFeedRecords(
      held,
      [call(2, 5), { cursor: 6, kind: "status", reason: "reset", step: 0 }, call(3, 7)],
      0,
    );
    // Only the call after the reset survives — 1 (retained) and 2 died with the run.
    expect(s.calls.map((c) => c.call_no)).toEqual([3]);
  });

  it("returns the same state when a connected client sees an empty batch", () => {
    const s = { ...idle(), connected: true };
    expect(applyFeedRecords(s, [], 0)).toBe(s);
  });

  it("keeps game_event and wish rows in feed order (#644)", () => {
    // Before #644 these rows were invisible: only engine/llm_call was handled,
    // so the web HUD disagreed with the Godot HUD about what happened.
    const s = applyFeedRecords(idle(), [gameEvent(1, "felt ill"), wish(2, "a bike rack")], 55);
    expect(s.events.map((e) => e.kind)).toEqual(["game_event", "wish"]);
    expect(s.events[0]).toMatchObject({ actor: "Maya", summary: "felt ill", receivedAt: 55 });
    expect(s.events[1]).toMatchObject({ desired: "a bike rack", trigger: "proposed" });
    // ...without leaking into the llm_call log.
    expect(s.calls).toEqual([]);
  });

  it("a reset status drops retained events and the batch's earlier rows", () => {
    const held = applyFeedRecords(idle(), [gameEvent(1, "old run")], 0);
    const s = applyFeedRecords(
      held,
      [
        gameEvent(2, "also dead"),
        { cursor: 3, kind: "status", reason: "reset", step: 0 },
        wish(4, "fresh"),
      ],
      0,
    );
    expect(s.events.map((e) => (e.kind === "wish" ? e.desired : e.summary))).toEqual(["fresh"]);
  });

  it("caps the retained event rows so a chatty run can't grow without bound", () => {
    let s = idle();
    for (let i = 1; i <= 205; i++) s = applyFeedRecords(s, [gameEvent(i, `e${i}`)], 0);
    expect(s.events).toHaveLength(200);
    expect(s.events[0]).toMatchObject({ summary: "e6" }); // oldest 5 evicted
  });
});

// ---------------------------------------------------------------------------
// The thinking state (#525): the per-agent `deciding` fold and the isThinking
// selector — fake feed fixtures with #551's begin/end lifecycle records.
// ---------------------------------------------------------------------------

const deciding = (cursor: number, agent: string, state: "begin" | "end"): FeedRecord => ({
  cursor,
  kind: "deciding",
  agent,
  state,
  step: 1,
  ...(state === "end" ? { elapsed_ms: 12 } : {}),
});

describe("deciding state", () => {
  it("a begin lights the agent and the matching end clears it", () => {
    let s = applyFeedRecords(idle(), [deciding(1, "Maya", "begin")], 70);
    expect(s.deciding).toEqual({ Maya: 70 });
    s = applyFeedRecords(s, [deciding(2, "Maya", "end")], 71);
    expect(s.deciding).toEqual({});
  });

  it("tracks several agents' decides independently (#366 concurrency)", () => {
    let s = applyFeedRecords(
      idle(),
      [deciding(1, "Maya", "begin"), deciding(2, "Diego", "begin")],
      70,
    );
    s = applyFeedRecords(s, [deciding(3, "Maya", "end")], 71);
    expect(s.deciding).toEqual({ Diego: 70 });
  });

  it("a within-tick begin+end folds to no bubble — no flicker at mock speeds (#605)", () => {
    // Today the backend drains a within-tick decide's begin AND end at the same
    // tick boundary, so they arrive in one batch: the fold must net out to
    // nothing rather than strobing a bubble through a render.
    const s = applyFeedRecords(
      idle(),
      [deciding(1, "Maya", "begin"), deciding(2, "Maya", "end")],
      70,
    );
    expect(s.deciding).toEqual({});
  });

  it("an orphan end (pre-reset straggler) is a no-op", () => {
    const s = applyFeedRecords(idle(), [deciding(1, "Maya", "end")], 70);
    expect(s.deciding).toEqual({});
  });

  it("a reset clears in-flight bubbles with the rest of the dead run", () => {
    const lit = applyFeedRecords(idle(), [deciding(1, "Maya", "begin")], 70);
    const s = applyFeedRecords(lit, [{ cursor: 2, kind: "status", reason: "reset", step: 0 }], 71);
    expect(s.deciding).toEqual({});
  });

  it("a frame stamps the stall clock", () => {
    const s = applyFeedRecords(idle(), [{ cursor: 1, kind: "frame", step: 2, agents: {} }], 88);
    expect(s.lastFrameAt).toBe(88);
  });
});

describe("isThinking", () => {
  // A healthy, connected, running live follower — each case below perturbs it.
  const following = (over: Partial<LiveState>): LiveState => ({
    ...idle(),
    connected: true,
    live: true,
    running: true,
    lastFrameAt: 10_000,
    ...over,
  });

  it("lights on the explicit per-agent signal even while frames keep flowing", () => {
    // #598's OR semantics: a parked #366 straggler decides across ticks while
    // the head keeps growing — stall inference alone would stay dark.
    const s = following({ deciding: { Maya: 9_900 } });
    expect(isThinking(s, 10_100)).toBe(true);
  });

  it("falls back to stall inference when no deciding records exist (mock runs)", () => {
    const s = following({});
    expect(isThinking(s, 10_000 + THINKING_STALL_MS + 1)).toBe(true);
    expect(isThinking(s, 10_000 + THINKING_STALL_MS - 1)).toBe(false); // fresh frame → dark
  });

  it("stays dark while paused or before any frame has landed", () => {
    expect(isThinking(following({ paused: true }), 99_999)).toBe(false);
    expect(isThinking(following({ running: false }), 99_999)).toBe(false);
    expect(isThinking(following({ lastFrameAt: null }), 99_999)).toBe(false);
  });

  it("is distinct from disconnected: a dead poll never reads as thinking", () => {
    // The strip's red "reconnecting" badge owns that state — even a mid-decide
    // agent or an ancient frame must not flip the cue while disconnected.
    const stalled = following({ connected: false, deciding: { Maya: 9_900 } });
    expect(isThinking(stalled, 99_999)).toBe(false);
    expect(isThinking(following({ live: false }), 99_999)).toBe(false);
  });
});

// A hand-rolled WebSocket double: the test opens/pushes/drops it explicitly.
class FakeWS {
  static all: FakeWS[] = [];
  static get last(): FakeWS {
    return FakeWS.all[FakeWS.all.length - 1];
  }
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeWS.all.push(this);
  }
  close() {} // client-side close during cleanup; the driver is cancelled by then
  open() {
    this.onopen?.();
  }
  push(record: FeedRecord) {
    this.onmessage?.({ data: JSON.stringify(record) });
  }
  drop() {
    this.onclose?.();
  }
}

describe("followLive", () => {
  let state: LiveState;
  let fetched: string[];
  // Mutable server bodies, so a test can change what /live and /events report
  // mid-run (the restart tests rewind the cursor this way).
  let live: Record<string, unknown>;
  let events: Record<string, unknown>;
  let usage: Record<string, unknown>;
  let stop: () => void = () => {};
  const setState = (up: (s: LiveState) => LiveState) => {
    state = up(state);
  };
  const urls = (path: string) => fetched.filter((u) => u.includes(path));

  beforeEach(() => {
    vi.useFakeTimers();
    state = idle();
    fetched = [];
    live = {
      enabled: true,
      running: true,
      paused: false,
      step: 3,
      cursor: 0,
      meta: null,
    };
    events = { latest_cursor: 9, oldest_cursor: null, events: [call(9, 9)] };
    usage = { available: false };
    FakeWS.all = [];
    vi.stubGlobal("WebSocket", FakeWS);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        fetched.push(url);
        const body = url.endsWith("/live") ? live : url.endsWith("/usage") ? usage : events;
        return { ok: true, json: async () => body };
      }),
    );
  });

  afterEach(() => {
    stop();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  // Run the driver up to its first socket (handshake microtasks + 0-timers).
  const start = async (): Promise<FakeWS> => {
    stop = followLive("http://b", setState);
    await vi.advanceTimersByTimeAsync(0);
    return FakeWS.last;
  };

  it("handshakes, then follows the feed over the socket (no /events polling)", async () => {
    const sock = await start();
    expect(sock.url).toBe("ws://b/ws?since=0");
    expect(state.connected).toBe(true);
    expect(state.live).toBe(true);
    expect(state.step).toBe(3); // from the handshake
    sock.open();
    sock.push(call(1, 1));
    sock.push({ cursor: 2, kind: "frame", step: 4, agents: {} });
    await vi.advanceTimersByTimeAsync(0); // one coalesced flush for the burst
    expect(state.calls.map((c) => c.call_no)).toEqual([1]);
    expect(state.step).toBe(4);
    expect(urls("/events")).toEqual([]);
  });

  it("a reset record over the socket clears the per-run call log", async () => {
    const sock = await start();
    sock.open();
    sock.push(call(1, 1));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls).toHaveLength(1);
    sock.push({ cursor: 2, kind: "status", reason: "reset", step: 0 });
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls).toEqual([]);
  });

  it("falls back to polling for good when the socket never opens", async () => {
    const sock = await start();
    sock.drop(); // refused before open: proxy block or a pre-WS backend
    await vi.advanceTimersByTimeAsync(0);
    expect(urls("/events")).toEqual(["http://b/events?since=0"]);
    expect(state.calls.map((c) => c.call_no)).toEqual([9]); // poll delivers the feed
    await vi.advanceTimersByTimeAsync(1000);
    expect(urls("/events")).toHaveLength(2); // steady 1s cadence...
    expect(FakeWS.all).toHaveLength(1); // ...and no further socket attempts
  });

  it("reconnects with a fresh handshake (kept cursor) when an open socket drops", async () => {
    const sock = await start();
    sock.open();
    sock.push(call(1, 5));
    await vi.advanceTimersByTimeAsync(0);
    live.cursor = 5; // the server's head has advanced with the feed (no restart)
    sock.drop(); // e.g. the server's 1011 "events evicted" close
    expect(state.connected).toBe(false); // push-based outage signal
    await vi.advanceTimersByTimeAsync(1000);
    expect(urls("/live")).toHaveLength(2); // re-handshake, then...
    expect(FakeWS.all).toHaveLength(2); // ...a new socket resuming at the cursor
    expect(FakeWS.last.url).toBe("ws://b/ws?since=5");
    expect(state.connected).toBe(true);
    FakeWS.last.open();
    FakeWS.last.push(call(2, 6));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([1, 2]); // log survives a drop
  });

  it("re-runs the handshake when a resumed socket's first record skips the cursor", async () => {
    const sock = await start();
    sock.open();
    sock.push(call(1, 5));
    await vi.advanceTimersByTimeAsync(0);
    live.cursor = 5;
    sock.drop();
    await vi.advanceTimersByTimeAsync(1000);
    const resumed = FakeWS.last;
    resumed.open();
    expect(urls("/live")).toHaveLength(2);
    resumed.push(call(2, 9)); // 9 > 5 + 1: rows were evicted while we were away
    await vi.advanceTimersByTimeAsync(0);
    expect(urls("/live")).toHaveLength(3); // background resync of meta/step/usage
    // The background refresh read a cursor (5) below the client's (9) — a stale
    // read racing the open socket, not a restart. It must NOT rewind or clear
    // the log (#549's guard): only a fresh connect/reconnect may re-anchor.
    expect(state.calls.map((c) => c.call_no)).toEqual([1, 2]); // the socket stays good
  });

  it("keeps the log when a drop races a background refresh (the guard is read at fire time)", async () => {
    const sock = await start();
    sock.open();
    sock.push(call(1, 5));
    await vi.advanceTimersByTimeAsync(0);
    live.cursor = 5; // the backend head is genuinely at 5 (below our cursor after the gap)
    sock.drop();
    await vi.advanceTimersByTimeAsync(1000); // reconnect handshake → socket at since=5
    const resumed = FakeWS.last;
    resumed.open();
    resumed.push(call(2, 9)); // gap (9 > 5+1) fires the background eviction refresh...
    resumed.drop(); // ...then the socket drops *during* it, flipping `handshook` false
    await vi.advanceTimersByTimeAsync(0); // the refresh resolves and reads the flag
    // Captured at fire time it's still "background", so no rewind: a late read of
    // the flipped flag would have wrongly cleared a healthy follower's log (#549).
    expect(state.calls.map((c) => c.call_no)).toEqual([1, 2]);
  });

  it("re-anchors at the handshake's cursor when a reconnect finds it rewound (restart)", async () => {
    const sock = await start();
    sock.open();
    sock.push(call(1, 5));
    await vi.advanceTimersByTimeAsync(0);
    sock.drop(); // the restarting backend takes every socket down with it
    // The new process: its in-memory feed restarted near zero.
    live = { ...live, step: 1, cursor: 2 };
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeWS.last.url).toBe("ws://b/ws?since=2"); // re-anchored, not since=5
    expect(state.calls).toEqual([]); // the dead run's log is cleared, like a reset
    FakeWS.last.open();
    FakeWS.last.push(call(2, 3));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([2]); // the new run's rows flow
  });

  it("re-anchors on a changed boot_id even when the new feed's cursor is past ours (#578)", async () => {
    live.boot_id = "boot-A";
    const sock = await start();
    sock.open();
    sock.push(call(1, 5));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([1]);
    sock.drop(); // the restarting backend takes every socket down with it
    // New process: its feed has ALREADY climbed past our cursor (5), so the
    // cursor-rewind check can't see the restart — only the changed boot_id can.
    live = { ...live, step: 1, cursor: 20, boot_id: "boot-B" };
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeWS.last.url).toBe("ws://b/ws?since=20"); // re-anchored at the new head
    expect(state.calls).toEqual([]); // the dead run's log is cleared, like a reset
    FakeWS.last.open();
    FakeWS.last.push(call(2, 21));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([2]); // the new run's rows flow
  });

  it("keeps the old nonce through a background refresh so the next reconnect still sees the restart (#578)", async () => {
    live.boot_id = "boot-A";
    const sock = await start();
    sock.open();
    sock.push(call(1, 5));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([1]);
    live.cursor = 5;
    sock.drop(); // a plain reconnect — no restart yet, nonce still boot-A
    await vi.advanceTimersByTimeAsync(1000);
    const resumed = FakeWS.last;
    resumed.open();
    // The backend restarts now; its feed has ALREADY climbed past our cursor, so
    // only the changed nonce can reveal it. A background eviction-gap refresh
    // reads the new nonce first — but it must NOT consume it: recording boot-B
    // here would blind the next reconnect's comparison (it would see no change).
    live = { ...live, step: 1, cursor: 20, boot_id: "boot-B" };
    resumed.push(call(2, 9)); // 9 > 5 + 1: fires the background refresh
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([1, 2]); // background: log untouched
    // Now the socket drops and we reconnect for real: the handshake compares the
    // still-old nonce (boot-A) to boot-B and detects the restart it would
    // otherwise have missed — re-anchoring at the new head and clearing the log.
    resumed.drop();
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeWS.last.url).toBe("ws://b/ws?since=20"); // re-anchored, not stitched at 9
    expect(state.calls).toEqual([]); // the dead run's log is cleared, like a reset
  });

  it("re-handshakes under the poll fallback when /events reports a changed boot_id (#578)", async () => {
    live.boot_id = "boot-A";
    events = { latest_cursor: 10, oldest_cursor: null, boot_id: "boot-A", events: [call(9, 10)] };
    const sock = await start();
    sock.drop(); // never opened: this target polls for good
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([9]); // old run, cursor at 10
    // Restart: the new process's feed has ALREADY climbed past our cursor, and it
    // hands back a contiguous record (cursor+1) — so neither the eviction-gap nor
    // the rewind check fires. Only the changed nonce on /events reveals the restart.
    live = { ...live, step: 1, cursor: 150, boot_id: "boot-B" };
    events = {
      latest_cursor: 150,
      oldest_cursor: null,
      boot_id: "boot-B",
      events: [call(10, 11)],
    };
    await vi.advanceTimersByTimeAsync(1000); // poll sees boot-B != boot-A → re-handshake queued
    events = {
      latest_cursor: 151,
      oldest_cursor: null,
      boot_id: "boot-B",
      events: [call(11, 151)],
    };
    await vi.advanceTimersByTimeAsync(1000);
    expect(urls("/live")).toHaveLength(2); // re-handshake happened
    expect(state.calls.map((c) => c.call_no)).toEqual([11]); // old log cleared, new run flows
  });

  it("re-anchors under the poll fallback when /events reports a rewound cursor", async () => {
    const sock = await start();
    sock.drop(); // never opened: this target polls for good
    await vi.advanceTimersByTimeAsync(0);
    expect(state.calls.map((c) => c.call_no)).toEqual([9]); // old run, cursor at 9
    // Restart: the new process's feed is behind the client's cursor.
    live = { ...live, step: 1, cursor: 4 };
    events = { latest_cursor: 4, oldest_cursor: null, events: [] };
    await vi.advanceTimersByTimeAsync(1000); // rewind detected — re-handshake queued
    events = { latest_cursor: 5, oldest_cursor: null, events: [call(2, 5)] };
    await vi.advanceTimersByTimeAsync(1000);
    expect(urls("/events?since=4")).toHaveLength(1); // re-anchored at the handshake's cursor
    expect(state.calls.map((c) => c.call_no)).toEqual([2]); // old log cleared, new rows flow
  });

  it("re-polls /usage on the slow cadence so the run counters and social block move (#819)", async () => {
    const sock = await start();
    sock.open();
    expect(state.usage).toEqual({ available: false }); // the handshake's read
    usage = {
      available: true,
      social: { co_settled_pair_steps: 12, by_pair: { "a + b": 12 }, conversations: 1 },
    };
    await vi.advanceTimersByTimeAsync(10_000);
    expect(urls("/usage").length).toBeGreaterThanOrEqual(2); // handshake + re-poll
    expect((state.usage as unknown as Record<string, unknown>).social).toEqual({
      co_settled_pair_steps: 12,
      by_pair: { "a + b": 12 },
      conversations: 1,
    });
  });

  it("keeps the same state object when /usage hasn't changed (skips a re-render)", async () => {
    const sock = await start();
    sock.open();
    const before = state;
    await vi.advanceTimersByTimeAsync(10_000); // re-poll returns an identical body
    expect(urls("/usage").length).toBeGreaterThanOrEqual(2); // it DID re-read...
    expect(state).toBe(before); // ...but an unchanged body must not re-render
  });
});
