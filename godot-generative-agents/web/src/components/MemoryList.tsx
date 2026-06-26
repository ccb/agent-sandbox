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

export function MemoryList({
  records,
  currentStep,
  secPerStep,
}: {
  records: MemoryRecord[];
  currentStep: number;
  secPerStep: number;
}) {
  // The history accrued so far: only memories formed by the current step.
  const shown = records.filter((m) => m.created_turn <= currentStep);
  if (!shown.length) {
    return <p className="mem-empty">No memories yet.</p>;
  }

  // Newest first, so a freshly-formed memory appears (and flashes) at the top.
  // Keyed by a stable identity (not array index) so prepending a new memory only
  // mounts that one row — existing rows are reused and don't re-flash or scroll-jump.
  const items: ReactElement[] = [];
  let lastClock: string | null = null;
  for (const m of shown.slice().reverse()) {
    const memKey = `${m.created_turn}|${m.kind}|${m.text}`;
    const clock = stepClock(m.created_turn, secPerStep);
    if (clock !== lastClock) {
      items.push(
        <li key={`h-${memKey}`} className="mem-group-head">
          {clock}
        </li>,
      );
      lastClock = clock;
    }
    // Flash the row the moment its memory forms (the step it's created), as it
    // first appears at the top of the list.
    const isNew = m.created_turn === currentStep;
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
