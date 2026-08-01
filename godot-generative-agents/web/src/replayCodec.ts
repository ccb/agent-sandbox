// The read side of the #941 carry-forward frame encoding (the write side is
// backend/replay_codec.py; the Godot mirror is godot/scripts/replay_codec.gd).
//
// A schema-1.1 replay FILE omits an agent's sticky fields (reasoning / chat /
// memories / trace) on frames where the value is unchanged from that agent's
// previous frame: absent = carry forward, present (including an explicit
// null) = a new value. Fattening at load hands every component the exact fat
// rows a pre-#941 file carried, so nothing downstream changes. Conservative:
// a key an agent has never carried stays absent (pre-#359 replays have no
// `trace` anywhere). Fattening an already-fat 1.0 file is the identity.

import type { AgentFrame, Frame } from "./types/replay";

const CARRY_FIELDS = ["reasoning", "chat", "memories", "trace"] as const;

/** Rehydrate slim frames in place (the caller owns the freshly parsed JSON)
 * and return the array for call-site convenience. Carried values are shared
 * by reference — cheap, and safe because nothing downstream mutates them. */
export function fattenFrames(frames: Frame[]): Frame[] {
  const carried = new Map<string, Partial<AgentFrame>>();
  for (const frame of frames) {
    if (typeof frame !== "object" || frame === null) continue;
    for (const [name, entry] of Object.entries(frame)) {
      if (typeof entry !== "object" || entry === null) continue;
      let agentCarry = carried.get(name);
      if (!agentCarry) {
        agentCarry = {};
        carried.set(name, agentCarry);
      }
      for (const k of CARRY_FIELDS) {
        if (k in entry) {
          agentCarry[k] = entry[k] as never;
        } else if (k in agentCarry) {
          (entry as unknown as Record<string, unknown>)[k] = agentCarry[k];
        }
      }
    }
  }
  return frames;
}
