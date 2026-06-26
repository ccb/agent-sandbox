import type { ReactNode } from "react";
import type { AgentFrame } from "../types/replay";
import { MemoryRows } from "./MemoryList";
import { SpritePreview } from "./SpritePreview";

// The activity string is "<activity> @ UPenn:Building:grounds"; split it into the
// action (before @) and location (after @), like the Smallville card does.
function splitAct(act: string): { action: string; location: string } {
  const at = act.indexOf("@");
  if (at === -1) return { action: act.trim(), location: "" };
  return { action: act.slice(0, at).trim(), location: act.slice(at + 1).trim() };
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="agent-field">
      <span className="agent-field-label">{label}</span>
      <span className="agent-field-value">{children}</span>
    </div>
  );
}

const dash = <span className="muted">—</span>;

export function AgentCard({
  name,
  emoji,
  index,
  frame,
  secPerStep,
}: {
  name: string;
  emoji: string;
  /** Persona index — selects the sprite tint so the portrait matches the map. */
  index: number;
  frame: AgentFrame | undefined;
  secPerStep: number;
}) {
  const { action, location } = frame ? splitAct(frame.act) : { action: "", location: "" };
  const chat = frame?.chat ?? null;
  // The small set retrieval surfaced for this decision — the shorthand the card
  // shows, distinct from the full stream in "Full memory history" below it.
  const retrieved = frame?.memories ?? [];

  return (
    <div className="agent-card">
      <div className="agent-card-head">
        {/* The agent's actual on-map sprite (tinted to match the canvas), like
            Smallville's per-character portrait. */}
        <SpritePreview index={index} className="agent-portrait" />
        <h2 className="agent-name">
          {name}
          <span className="agent-name-emoji" aria-hidden="true">
            {emoji}
          </span>
        </h2>
      </div>

      <Field label="Current Action">{action || dash}</Field>
      <Field label="Location">{location || dash}</Field>
      <Field label="Reasoning">{frame?.reasoning ? frame.reasoning : dash}</Field>
      <Field label="Current Conversation">
        {chat && chat.length ? (
          chat.map(([speaker, line], i) => (
            <div key={i} className="chat-line">
              <span className="chat-speaker">{speaker}:</span> {line}
            </div>
          ))
        ) : (
          <span className="muted">None at the moment</span>
        )}
      </Field>

      {/* The cognition shorthand: just the memories retrieval surfaced for the
          current action (a subset of the full history shown below the card). */}
      <div className="agent-field">
        <span className="agent-field-label">Memories retrieved</span>
        {retrieved.length ? (
          <MemoryRows records={retrieved} secPerStep={secPerStep} showTime={false} />
        ) : (
          <span className="agent-field-value muted">None retrieved</span>
        )}
      </div>
    </div>
  );
}
