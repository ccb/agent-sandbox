import { describe, expect, it } from "vitest";
import { selectWishes } from "./WishFeed";

// The helper only reads `turn` (its Pick<WishState, ...> input) and passes
// rows through whole, so fixtures carry a tag to assert order by.
const wish = (turn: number, desired: string) => ({ turn, desired });

// A run's demand log, chronological like the store writes it: two wishes on
// one turn (a multi-gap decide), then two later ones.
const RUN = [
  wish(431, "arranging seating"),
  wish(431, "checking acoustics"),
  wish(1005, "taking excited notes"),
  wish(2714, "mentally replaying the lecture"),
];

describe("selectWishes", () => {
  it("returns newest first, whole rows preserved", () => {
    expect(selectWishes(RUN, null).map((w) => w.desired)).toEqual([
      "mentally replaying the lecture",
      "taking excited notes",
      "checking acoustics",
      "arranging seating",
    ]);
  });

  it("scopes to the cursor, so scrubbing back hides later wishes", () => {
    expect(selectWishes(RUN, 1005).map((w) => w.turn)).toEqual([1005, 431, 431]);
    expect(selectWishes(RUN, 430)).toEqual([]);
  });

  it("null cursor is the live path: no turn scoping", () => {
    expect(selectWishes(RUN, null)).toHaveLength(4);
  });

  it("caps at the newest N and returns [] for empty input", () => {
    expect(selectWishes(RUN, null, 2).map((w) => w.turn)).toEqual([2714, 1005]);
    expect(selectWishes([], null)).toEqual([]);
  });
});
