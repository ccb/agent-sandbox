import type { ReactElement } from "react";
import type { MemoryRecord } from "../types/replay";

// There's no wall clock in the Penn sim, so render `created_turn` as an elapsed
// mm:ss label (step x sec_per_step). Memories formed at the same time cluster
// under one heading, mirroring the Smallville card's HH:MM grouping.
function stepClock(turn: number, secPerStep: number): string {
  const total = turn * secPerStep;
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// kind is a fixed enum; keep only word chars for the CSS modifier that colours it.
function kindClass(kind: string): string {
  return "mem-" + kind.replace(/[^a-z]/gi, "").toLowerCase();
}

/**
 * A colour-coded list of memory records — the shared renderer for both the
 * card's compact "Memories retrieved" shorthand and the expanded "Full memory
 * history". Records are rendered in the order given (callers sort first).
 *
 * - `showTime` adds mm:ss group headers (on for the time-ordered full history;
 *   off for the card's small ranked retrieved set, which isn't time-ordered).
 * - a row whose memory formed exactly at `flashTurn` gets the "new memory"
 *   flash (pass -1 to disable — the retrieved shorthand doesn't flash).
 *
 * Rows are keyed by a stable identity (not array index) so prepending a new
 * memory only mounts that one row — existing rows are reused and don't re-flash.
 */
export function MemoryRows({
  records,
  secPerStep,
  showTime = true,
  flashTurn = -1,
}: {
  records: MemoryRecord[];
  secPerStep: number;
  showTime?: boolean;
  flashTurn?: number;
}) {
  const items: ReactElement[] = [];
  let lastClock: string | null = null;
  for (const m of records) {
    const memKey = `${m.created_turn}|${m.kind}|${m.text}`;
    if (showTime) {
      const clock = stepClock(m.created_turn, secPerStep);
      if (clock !== lastClock) {
        items.push(
          <li key={`h-${memKey}`} className="mem-group-head">
            {clock}
          </li>,
        );
        lastClock = clock;
      }
    }
    const isNew = m.created_turn === flashTurn;
    items.push(
      <li key={memKey} className={`mem-item ${kindClass(m.kind)}${isNew ? " is-new" : ""}`}>
        <div className="mem-meta">
          <span className="mem-kind">{m.kind}</span>
          <span className="mem-imp" title="importance">
            {m.importance}
          </span>
        </div>
        <div className="mem-text">{m.text}</div>
      </li>,
    );
  }

  return <ul className="mem-list">{items}</ul>;
}
