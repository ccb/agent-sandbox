import { describe, expect, it } from "vitest";
import { tallyActions } from "./MostTakenActions";

// The helper only reads `action` + `turn` (its Pick<EventState, ...> input),
// so fixtures are bare pairs.
const ev = (action: string, turn: number) => ({ action, turn });

// A small run: go×3, eat×2, craft×1 spread over turns 0..4, with the two
// engine-internal kinds (#699's EXCLUDED_KINDS) interleaved.
const RUN = [
  ev("go", 0),
  ev("trigger", 0),
  ev("eat", 1),
  ev("go", 1),
  ev("sound", 2),
  ev("craft", 2),
  ev("eat", 3),
  ev("go", 4),
];

describe("tallyActions", () => {
  it("ranks verbs by count and drops trigger/sound (the #699 filter)", () => {
    expect(tallyActions(RUN, null)).toEqual([
      ["go", 3],
      ["eat", 2],
      ["craft", 1],
    ]);
  });

  it("scopes to the cursor, so scrubbing back lowers the counts", () => {
    expect(tallyActions(RUN, 2)).toEqual([
      ["go", 2],
      ["craft", 1],
      ["eat", 1],
    ]);
    expect(tallyActions(RUN, 0)).toEqual([["go", 1]]);
  });

  it("breaks count ties by the verb ascending (deterministic order)", () => {
    const tied = [ev("read", 0), ev("eat", 1), ev("go", 2)];
    expect(tallyActions(tied, null)).toEqual([
      ["eat", 1],
      ["go", 1],
      ["read", 1],
    ]);
  });

  it("caps at top-N and returns [] for empty or all-internal input", () => {
    expect(tallyActions(RUN, null, 2)).toEqual([
      ["go", 3],
      ["eat", 2],
    ]);
    expect(tallyActions([], null)).toEqual([]);
    expect(tallyActions([ev("trigger", 0), ev("sound", 1)], null)).toEqual([]);
  });
});
