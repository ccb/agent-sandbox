import { describe, expect, it } from "vitest";
import type { RunSocial } from "../types/live";
import { socialView } from "./RunSocialCard";

// A counting, non-resumed run by default — the case where a zero is a real
// #795 signal. Individual tests override `counted`/`resumed` to exercise the
// non-signal states.
const social = (over: Partial<RunSocial> = {}): RunSocial => ({
  co_settled_pair_steps: 0,
  by_pair: {},
  conversations: 0,
  counted: true,
  resumed: false,
  ...over,
});

describe("socialView", () => {
  it("is null when the backend serves no social block (pre-#806) — the card hides", () => {
    expect(socialView(undefined, 100)).toBeNull();
  });

  it("ranks pairs busiest-first, keeps only the top 5, and counts the rest", () => {
    const v = socialView(
      social({
        co_settled_pair_steps: 21,
        by_pair: { "a + b": 1, "c + d": 6, "e + f": 5, "g + h": 4, "i + j": 3, "k + l": 2 },
      }),
      100,
    );
    expect(v?.pairs.map(([label]) => label)).toEqual(["c + d", "e + f", "g + h", "i + j", "k + l"]);
    expect(v?.pairs.map(([, n]) => n)).toEqual([6, 5, 4, 3, 2]);
    expect(v?.truncated).toBe(1); // "a + b" fell off the top-5 — not silently
  });

  it("breaks equal counts by label, so the order is stable not dict-dependent", () => {
    const v = socialView(
      social({ co_settled_pair_steps: 9, by_pair: { "z + z": 3, "a + a": 3, "m + m": 3 } }),
      100,
    );
    expect(v?.pairs.map(([label]) => label)).toEqual(["a + a", "m + m", "z + z"]);
  });

  it("flags a real drought only for a counting, non-resumed run that stepped and stayed at 0", () => {
    expect(socialView(social(), 100)?.note).toBe("drought");
    expect(socialView(social(), 0)?.note).toBeNull(); // hasn't stepped yet
    expect(socialView(social({ co_settled_pair_steps: 3 }), 100)?.note).toBeNull();
  });

  it("names the counter mismatch when a conversation completed but co-settle read 0 (#823)", () => {
    // The old both-zero gate hid exactly this — the one case the counter is
    // provably wrong rather than merely idle.
    expect(socialView(social({ conversations: 1 }), 100)?.note).toBe("mismatch");
  });

  it("says uncounted when the backend reports counted:false (pre-#825), at any step", () => {
    expect(socialView(social({ counted: false }), 100)?.note).toBe("uncounted");
    expect(socialView(social({ counted: false }), 0)?.note).toBe("uncounted");
  });

  it("says resumed when the run restarted its counters mid-day — even with real activity", () => {
    expect(socialView(social({ resumed: true }), 100)?.note).toBe("resumed");
    expect(socialView(social({ resumed: true, conversations: 2 }), 100)?.note).toBe("resumed");
  });

  it("keeps the soft 'unknown' note when a backend too old to send `counted` shows a zero", () => {
    const bare: RunSocial = { co_settled_pair_steps: 0, by_pair: {}, conversations: 0 };
    expect(socialView(bare, 100)?.note).toBe("unknown");
  });
});
