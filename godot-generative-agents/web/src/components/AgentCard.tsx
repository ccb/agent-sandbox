import type { ReactNode } from "react";
import type { AgentFrame, Persona, RelationshipEdge } from "../types/replay";
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
  persona,
  index,
  frame,
  secPerStep,
  relationships = [],
}: {
  persona: Persona;
  /** Persona index — selects the sprite tint so the portrait matches the map. */
  index: number;
  frame: AgentFrame | undefined;
  secPerStep: number;
  /** The t=0 seed social graph (meta.relationships, #450); the card shows a compact
   * "knows" line — the Godot G-key pop-up stays the rich view. */
  relationships?: RelationshipEdge[];
}) {
  const { action, location } = frame ? splitAct(frame.act) : { action: "", location: "" };
  const chat = frame?.chat ?? null;
  // The small set retrieval surfaced for this decision — the shorthand the card
  // shows, distinct from the full stream in "Full memory history" below it.
  const retrieved = frame?.memories ?? [];

  // The authored identity meta (#410 blurb/home/schedule, #450 relationships).
  // Each block below renders only when the meta carries it, so casts without it
  // (Smallville-style) show nothing rather than "n/a" noise (#523).
  const schedule = persona.schedule ?? [];
  const knows = relationships
    .filter((r) => r.a === persona.name || r.b === persona.name)
    .map((r) => ({ who: r.a === persona.name ? r.b : r.a, kind: r.kind }));

  return (
    <div className="agent-card">
      <div className="agent-card-head">
        {/* The agent's actual on-map sprite (tinted to match the canvas), like
            Smallville's per-character portrait. */}
        <SpritePreview index={index} className="agent-portrait" />
        <h2 className="agent-name">
          {persona.name}
          <span className="agent-name-emoji" aria-hidden="true">
            {persona.emoji}
          </span>
        </h2>
      </div>

      {persona.persona && <Field label="Persona">{persona.persona}</Field>}
      {persona.home && <Field label="Home">{persona.home}</Field>}
      {schedule.length > 0 && (
        <Field label="Daily schedule">
          {schedule.map((s, i) => (
            <div key={i} className="chat-line">
              <span aria-hidden="true">{s.emoji} </span>
              {s.activity} · {s.place}
            </div>
          ))}
        </Field>
      )}
      {knows.length > 0 && (
        <Field label="Knows">
          {knows.map((k, i) => (
            <span key={i}>
              {i > 0 && ", "}
              {k.who} <span className="muted">({k.kind})</span>
            </span>
          ))}
        </Field>
      )}

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
