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
}

/** A step: persona name -> that persona's state. */
export type Frame = Record<string, AgentFrame>;

export interface Replay {
  meta: ReplayMeta;
  frames: Frame[];
}
