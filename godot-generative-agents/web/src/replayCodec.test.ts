// Mirrors the Python round-trip cases in tests/test_replay_codec.py — the
// #941 slim encoding: absent = carry forward, present (incl. null) = new.
import { describe, expect, it } from "vitest";
import { fattenFrames } from "./replayCodec";
import type { Frame } from "./types/replay";

const lines: [string, string][] = [
  ["Ada", "hello"],
  ["Bob", "hi"],
];
const mems = [{ kind: "event", importance: 1.0, text: "saw Bob", created_turn: 0 }];

function entry(x: number, extra: Record<string, unknown> = {}) {
  return { x, y: 2, act: "reading", e: "📖", ...extra };
}

describe("fattenFrames", () => {
  it("carries absent fields forward and treats explicit null as a new value", () => {
    const slim = [
      { Ada: entry(1, { reasoning: null, chat: null, memories: mems, trace: [] }) },
      { Ada: entry(2, { chat: lines }) }, // chat starts; the rest carried
      { Ada: entry(3) }, // everything carried
      { Ada: entry(4, { chat: null }) }, // chat explicitly cleared
    ] as unknown as Frame[];
    // Positive control: the carried frame really lacks the key before fattening.
    expect("chat" in slim[2].Ada).toBe(false);

    const fat = fattenFrames(slim);
    expect(fat[1].Ada.memories).toEqual(mems);
    expect(fat[2].Ada.chat).toEqual(lines);
    expect(fat[2].Ada.reasoning).toBeNull();
    expect(fat[2].Ada.trace).toEqual([]);
    expect(fat[3].Ada.chat).toBeNull();
    expect(fat[3].Ada.memories).toEqual(mems);
    expect(fat[3].Ada.x).toBe(4);
  });

  it("is the identity on an already-fat (1.0) file", () => {
    const fat = [
      { Ada: entry(1, { reasoning: null, chat: lines, memories: mems, trace: [] }) },
      { Ada: entry(2, { reasoning: null, chat: null, memories: mems, trace: [] }) },
    ] as unknown as Frame[];
    const before = JSON.stringify(fat);
    expect(JSON.stringify(fattenFrames(fat))).toBe(before);
  });

  it("never invents a key the agent has not carried (pre-#359 files lack trace)", () => {
    const slim = [{ Ada: entry(1, { chat: null }) }, { Ada: entry(2) }] as unknown as Frame[];
    const fat = fattenFrames(slim);
    expect("trace" in fat[1].Ada).toBe(false);
    expect("chat" in fat[1].Ada).toBe(true);
  });

  it("tracks each agent independently, including late arrivals", () => {
    const slim = [
      { Ada: entry(1, { chat: null }) },
      { Ada: entry(2), Bob: entry(9, { chat: lines }) },
      { Ada: entry(3), Bob: entry(9) },
    ] as unknown as Frame[];
    const fat = fattenFrames(slim);
    expect(fat[2].Ada.chat).toBeNull();
    expect(fat[2].Bob.chat).toEqual(lines);
  });
});
