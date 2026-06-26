// Shape of godot-generative-agents/maps/penn_replay.json, written by
// sim/generate_penn_replay.py and played by scripts/penn_replay.gd. The browser
// shell serves a copy at /replay/penn_replay.json (see web/public/replay/).
//
// The Godot canvas already consumes this file itself; these types are here so the
// upcoming agent-info companion panels can read the SAME data, type-safe.

export interface Persona {
  name: string;
  emoji: string;
}

export interface ReplayMeta {
  /** Pixels per tile (16 for the campus map). */
  tile_px: number;
  /** Map size in tiles. */
  width: number;
  height: number;
  /** Number of steps (== frames.length). */
  steps: number;
  /** In-game seconds represented by one step (for a wall-clock label). */
  sec_per_step: number;
  personas: Persona[];
}

/** One persona's state at a single step. */
export interface AgentFrame {
  /** Tile coordinates. */
  x: number;
  y: number;
  /** Activity description, e.g. "studying @ UPenn:Van Pelt Library:grounds". */
  act: string;
  /** Activity emoji ("pronunciatio"). */
  e: string;
  /**
   * The reasoning behind this step's action (issue #163). The mock brain leaves
   * a short templated line; a real-LLM run fills in genuine reasoning. Optional
   * so an older replay JSON (which omits it) still type-checks.
   */
  reasoning?: string | null;
  /**
   * The agent's current conversation as `[speaker, line]` pairs, or null when
   * not talking. Always null under the mock brain (conversation is gated on a
   * real model).
   */
  chat?: [string, string][] | null;
}

/** A step: persona name -> that persona's state. */
export type Frame = Record<string, AgentFrame>;

/**
 * One entry in a persona's memory stream (issue #163). Mirrors the UI-ready dict
 * the Smallville exporter / `memory_stream_for_persona` produce.
 */
export interface MemoryRecord {
  /** "observation" | "plan" | "reflection" | "chat" — the panel colour-codes it. */
  kind: string;
  /** The memory text itself. */
  text: string;
  /** The step at which the memory formed (its position on the replay's time axis). */
  created_turn: number;
  /** Poignancy / importance (kept quiet beside the text). */
  importance: number;
}

export interface Replay {
  meta: ReplayMeta;
  frames: Frame[];
  /**
   * Per-persona full memory stream, written by sim/generate_penn_replay.py. The
   * companion panel filters each agent's records to `created_turn <= step` to show
   * the history accrued so far. Optional: a replay generated before this field
   * existed simply has no memory history to show.
   */
  memory_streams?: Record<string, MemoryRecord[]>;
}
