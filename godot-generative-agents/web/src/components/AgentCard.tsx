import type { ReactNode } from "react";
import type { AgentFrame } from "../types/replay";

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
  frame,
}: {
  name: string;
  emoji: string;
  frame: AgentFrame | undefined;
}) {
  const { action, location } = frame ? splitAct(frame.act) : { action: "", location: "" };
  const chat = frame?.chat ?? null;

  return (
    <div className="agent-card">
      <div className="agent-card-head">
        <div className="agent-portrait" aria-hidden="true">
          {emoji}
        </div>
        <h2 className="agent-name">{name}</h2>
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
    </div>
  );
}
