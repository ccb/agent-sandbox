import { describe, expect, it } from "vitest";
import { capPerAgent, type ReceivedLlmCall } from "./useLive";

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
