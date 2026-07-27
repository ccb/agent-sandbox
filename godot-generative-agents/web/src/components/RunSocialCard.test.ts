import { describe, expect, it } from "vitest";
import type { RunSocial } from "../types/live";
import { socialView } from "./RunSocialCard";

const social = (over: Partial<RunSocial> = {}): RunSocial => ({
  co_settled_pair_steps: 0,
  by_pair: {},
  conversations: 0,
  ...over,
});

describe("socialView", () => {
  it("is null when the backend serves no social block (pre-#806) — the card hides", () => {
    expect(socialView(undefined, 100)).toBeNull();
  });

  it("ranks pairs busiest-first and keeps only the top 5", () => {
    const v = socialView(
      social({
        co_settled_pair_steps: 21,
        by_pair: { "a + b": 1, "c + d": 6, "e + f": 5, "g + h": 4, "i + j": 3, "k + l": 2 },
      }),
      100,
    );
    expect(v?.pairs.map(([label]) => label)).toEqual(["c + d", "e + f", "g + h", "i + j", "k + l"]);
    expect(v?.pairs.map(([, n]) => n)).toEqual([6, 5, 4, 3, 2]);
  });

  it("is quiet only when a run that has stepped shows zero on BOTH counters", () => {
    expect(socialView(social(), 100)?.quiet).toBe(true);
    expect(socialView(social(), 0)?.quiet).toBe(false); // hasn't stepped yet
    expect(socialView(social({ conversations: 1 }), 100)?.quiet).toBe(false);
    expect(socialView(social({ co_settled_pair_steps: 3 }), 100)?.quiet).toBe(false);
  });
});
