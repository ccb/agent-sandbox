import { useState } from "react";
import type { Replay } from "../types/replay";
import { AgentCard } from "./AgentCard";
import { MemoryRows } from "./MemoryList";
import { useReplayStep } from "../useReplay";
import "./AgentPanel.css";

export function AgentPanel({ replay }: { replay: Replay }) {
  const { personas, sec_per_step, steps } = replay.meta;
  // Which agent's card you're looking at. Arrows step through the personas
  // (wrapping at the ends), like Smallville's agent navigator — switching only
  // changes WHO you see; the replay keeps playing underneath.
  const [index, setIndex] = useState(0);
  const step = useReplayStep(steps);

  const count = personas.length;
  const persona = personas[index] ?? personas[0];
  const go = (delta: number) => setIndex((i) => (i + delta + count) % count);
  const frame = replay.frames[Math.min(step, replay.frames.length - 1)]?.[persona.name];

  // The full memory stream accrued so far (everything formed by the current
  // step), newest-first — the expanded view, distinct from the card's compact
  // "Memories retrieved". Filtering here means it grows as the replay plays.
  const stream = replay.memory_streams?.[persona.name] ?? [];
  const history = stream.filter((m) => m.created_turn <= step).slice().reverse();

  return (
    <aside className="agent-panel">
      {/* One cohesive panel: a navigator header over a two-column body (the agent's
          details on the left, its full memory history on the right), so the arrows,
          the card, and the memory list read as one piece instead of stacked boxes. */}
      <div className="agent-board">
        <header className="agent-nav">
          <button
            type="button"
            className="agent-nav-btn"
            onClick={() => go(-1)}
            disabled={count < 2}
            aria-label="Previous agent"
            title="Previous agent"
          >
            ‹
          </button>
          <span className="agent-indicator">
            <span className="agent-indicator-emoji" aria-hidden="true">
              {persona.emoji}
            </span>
            {persona.name}
            <span className="agent-indicator-count">
              {index + 1} / {count}
            </span>
          </span>
          <button
            type="button"
            className="agent-nav-btn"
            onClick={() => go(1)}
            disabled={count < 2}
            aria-label="Next agent"
            title="Next agent"
          >
            ›
          </button>
        </header>

        <div className="agent-board-cols">
          <div className="agent-board-main">
            <AgentCard
              name={persona.name}
              emoji={persona.emoji}
              index={index}
              frame={frame}
              secPerStep={sec_per_step}
            />
          </div>

          {/* The expanded view: every memory the agent has formed so far, beyond the
              handful the card surfaced. Its own column so the card stays compact. */}
          <section className="agent-board-side">
            <div className="agent-history-head">
              Full memory history
              <span className="agent-history-count">{history.length}</span>
            </div>
            {history.length ? (
              <MemoryRows records={history} secPerStep={sec_per_step} flashTurn={step} />
            ) : (
              <p className="mem-empty">No memories yet.</p>
            )}
          </section>
        </div>
      </div>
    </aside>
  );
}
