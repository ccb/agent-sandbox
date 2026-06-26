import { useState } from "react";
import type { Replay } from "../types/replay";
import { AgentCard } from "./AgentCard";
import { MemoryRows } from "./MemoryList";
import { useReplayStep } from "../useReplay";
import "./AgentPanel.css";

export function AgentPanel({ replay }: { replay: Replay }) {
  const { personas, sec_per_step, steps } = replay.meta;
  const [selected, setSelected] = useState(personas[0].name);
  const step = useReplayStep(steps);

  const persona = personas.find((p) => p.name === selected) ?? personas[0];
  const frame = replay.frames[Math.min(step, replay.frames.length - 1)]?.[persona.name];

  // The full memory stream accrued so far (everything formed by the current
  // step), newest-first — the expanded view, distinct from the card's compact
  // "Memories retrieved". Filtering here means it grows as the replay plays.
  const stream = replay.memory_streams?.[persona.name] ?? [];
  const history = stream.filter((m) => m.created_turn <= step).slice().reverse();

  return (
    <aside className="agent-panel">
      <div className="agent-tabs" role="tablist">
        {personas.map((p) => (
          <button
            key={p.name}
            type="button"
            role="tab"
            aria-selected={p.name === persona.name}
            className={`agent-tab${p.name === persona.name ? " is-active" : ""}`}
            onClick={() => setSelected(p.name)}
          >
            <span className="agent-tab-emoji" aria-hidden="true">
              {p.emoji}
            </span>
            {p.name}
          </button>
        ))}
      </div>

      <AgentCard
        name={persona.name}
        emoji={persona.emoji}
        frame={frame}
        secPerStep={sec_per_step}
      />

      {/* The expanded view: every memory the agent has formed so far, beyond the
          handful the card surfaced. Collapsible so the card stays the focus. */}
      <details className="agent-history" open>
        <summary className="agent-history-summary">
          Full memory history
          <span className="agent-history-count">{history.length}</span>
        </summary>
        {history.length ? (
          <MemoryRows records={history} secPerStep={sec_per_step} flashTurn={step} />
        ) : (
          <p className="mem-empty">No memories yet.</p>
        )}
      </details>
    </aside>
  );
}
