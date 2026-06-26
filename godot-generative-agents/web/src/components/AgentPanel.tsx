import { useState } from "react";
import type { Replay } from "../types/replay";
import { AgentCard } from "./AgentCard";
import { MemoryList } from "./MemoryList";
import { useReplayStep } from "../useReplay";
import "./AgentPanel.css";

export function AgentPanel({ replay }: { replay: Replay }) {
  const { personas, sec_per_step, steps } = replay.meta;
  const [selected, setSelected] = useState(personas[0].name);
  const step = useReplayStep(steps);

  const persona = personas.find((p) => p.name === selected) ?? personas[0];
  const frame = replay.frames[Math.min(step, replay.frames.length - 1)]?.[persona.name];
  const memories = replay.memory_streams?.[persona.name] ?? [];

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

      <AgentCard name={persona.name} emoji={persona.emoji} frame={frame} />

      <div className="agent-field agent-memory">
        <span className="agent-field-label">Memory history</span>
        <MemoryList records={memories} currentStep={step} secPerStep={sec_per_step} />
      </div>
    </aside>
  );
}
