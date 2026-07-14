import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FeedRecord } from "./types/live";
import {
  applyFeedRecords,
  capPerAgent,
  followLive,
  type LiveState,
  type ReceivedLlmCall,
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
});

const call = (call_no: number, cursor: number): FeedRecord => ({
  cursor,
  kind: "engine",
  event: { kind: "llm_call", actor: "a", call_no },
});

describe("applyFeedRecords", () => {
  it("keeps llm_call rows and tracks the newest frame/status", () => {
    const s = applyFeedRecords(
      idle(),
      [
        call(1, 1),
        { cursor: 2, kind: "frame", step: 7, agents: {} },
        { cursor: 3, kind: "status", reason: "paused", running: true, paused: true, step: 7 },
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
  let stop: () => void = () => {};
  const setState = (up: (s: LiveState) => LiveState) => {
    state = up(state);
  };
  const urls = (path: string) => fetched.filter((u) => u.includes(path));

  beforeEach(() => {
    vi.useFakeTimers();
    state = idle();
    fetched = [];
    FakeWS.all = [];
    vi.stubGlobal("WebSocket", FakeWS);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        fetched.push(url);
        const body = url.endsWith("/live")
          ? { enabled: true, running: true, paused: false, step: 3, cursor: 0, meta: null }
          : url.endsWith("/usage")
            ? { available: false }
            : { latest_cursor: 9, oldest_cursor: null, events: [call(9, 9)] };
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
    sock.drop();
    await vi.advanceTimersByTimeAsync(1000);
    const resumed = FakeWS.last;
    resumed.open();
    expect(urls("/live")).toHaveLength(2);
    resumed.push(call(2, 9)); // 9 > 5 + 1: rows were evicted while we were away
    await vi.advanceTimersByTimeAsync(0);
    expect(urls("/live")).toHaveLength(3); // background resync of meta/step/usage
    expect(state.calls.map((c) => c.call_no)).toEqual([1, 2]); // the socket stays good
  });
});
