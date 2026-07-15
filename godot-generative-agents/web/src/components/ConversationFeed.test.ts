import { describe, expect, it } from "vitest";
import type { Frame } from "../types/replay";
import { collectConversations } from "./ConversationFeed";

// The helper only reads `.chat`; build minimal frames and cast (other AgentFrame
// fields are irrelevant to dedup/order).
const frame = (chats: Record<string, [string, string][] | null>): Frame =>
  Object.fromEntries(Object.entries(chats).map(([n, chat]) => [n, { chat }])) as unknown as Frame;

describe("collectConversations", () => {
  it("dedupes a two-party exchange both participants carry", () => {
    const convo: [string, string][] = [
      ["Diego", "hi"],
      ["Tanaka", "hello"],
    ];
    const out = collectConversations(frame({ Diego: convo, Tanaka: convo }));
    expect(out).toEqual([
      ["Tanaka", "hello"],
      ["Diego", "hi"],
    ]); // deduped + newest-first
  });

  it("returns [] for empty / missing / null chat", () => {
    expect(collectConversations(null)).toEqual([]);
    expect(collectConversations(undefined)).toEqual([]);
    expect(collectConversations(frame({ A: null, B: [] }))).toEqual([]);
  });

  it("is newest-first and capped", () => {
    const lines: [string, string][] = Array.from({ length: 5 }, (_, i) => ["A", `l${i}`]);
    const out = collectConversations(frame({ A: lines }), 3);
    expect(out).toEqual([
      ["A", "l4"],
      ["A", "l3"],
      ["A", "l2"],
    ]);
  });
});
